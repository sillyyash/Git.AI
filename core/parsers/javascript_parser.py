from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from core.metadata import ImportAlias, RelationshipMetadata, StaticAlias
from core.parsers.parser_utils import clean_metadata, empty_metadata

_VENDOR_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "vendor"))
if os.path.isdir(_VENDOR_PATH) and _VENDOR_PATH not in sys.path:
    sys.path.insert(0, _VENDOR_PATH)

try:
    from tree_sitter import Language, Parser
    import tree_sitter_javascript
except ImportError:  # pragma: no cover - dependency is declared in requirements.txt
    Language = None
    Parser = None
    tree_sitter_javascript = None

_JS_BUILTINS = {
    "Array", "Boolean", "Date", "Error", "Function", "JSON", "Map", "Math",
    "Number", "Object", "Promise", "Reflect", "RegExp", "Set", "String",
    "Symbol", "WeakMap", "WeakSet", "console", "document", "window",
    "parseFloat", "parseInt", "require", "setInterval", "setTimeout",
}

_FUNCTION_NODES = {
    "function_declaration",
    "function",
    "function_expression",
    "arrow_function",
    "generator_function",
}

_DECLARATION_NODES = {"lexical_declaration", "variable_declaration"}


@dataclass
class CallTarget:
    callee: str
    original_callee: str
    kind: str
    object_name: Optional[str] = None
    method_name: Optional[str] = None
    local_name: Optional[str] = None
    imported_name: Optional[str] = None
    imported_from: Optional[str] = None
    resolved_from_alias: bool = False


class JavaScriptTreeSitterBackend:
    def __init__(self) -> None:
        if Parser is None or Language is None or tree_sitter_javascript is None:
            self.parser = None
            return
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_javascript.language())

    def parse(self, content: str):
        if self.parser is None:
            return None
        return self.parser.parse(content.encode("utf-8")).root_node


class ParserContext:
    def __init__(self, source: str) -> None:
        self.source = source.encode("utf-8")
        self.import_aliases: Dict[str, ImportAlias] = {}
        self.scope_aliases: List[Dict[str, StaticAlias]] = [{}]
        self.function_stack: List[str] = []
        self.class_stack: List[str] = []

    def text(self, node) -> str:
        return self.source[node.start_byte:node.end_byte].decode("utf-8", "ignore")

    def line(self, node) -> int:
        return node.start_point[0] + 1

    def push_scope(self) -> None:
        self.scope_aliases.append({})

    def pop_scope(self) -> None:
        if len(self.scope_aliases) > 1:
            self.scope_aliases.pop()

    def add_import_alias(self, local_name: str, imported_name: str, imported_from: str) -> None:
        self.import_aliases[local_name] = ImportAlias(local_name, imported_name, imported_from)

    def add_static_alias(self, local_name: str, target: str) -> None:
        self.scope_aliases[-1][local_name] = StaticAlias(local_name, target)

    def current_function(self) -> Optional[str]:
        return self.function_stack[-1] if self.function_stack else None

    def current_class(self) -> Optional[str]:
        return self.class_stack[-1] if self.class_stack else None

    def resolve_alias(self, name: str) -> Optional[StaticAlias]:
        for scope in reversed(self.scope_aliases):
            if name in scope:
                return scope[name]
        return None

    def resolve_target(self, raw_name: str, object_name: Optional[str], method_name: Optional[str]) -> CallTarget:
        original = raw_name

        if raw_name.startswith("this.") and self.current_class() and method_name:
            return CallTarget(
                callee=f"{self.current_class()}.{method_name}",
                original_callee=original,
                kind=RelationshipMetadata.OBJECT,
                object_name=object_name,
                method_name=method_name,
                resolved_from_alias=True,
            )

        if object_name and object_name in self.import_aliases:
            import_alias = self.import_aliases[object_name]
            return CallTarget(
                callee=raw_name,
                original_callee=original,
                kind=RelationshipMetadata.OBJECT,
                object_name=object_name,
                method_name=method_name,
                local_name=import_alias.local_name,
                imported_name=method_name or import_alias.imported_name,
                imported_from=import_alias.imported_from,
            )

        static_alias = self.resolve_alias(raw_name)
        if static_alias:
            return CallTarget(
                callee=static_alias.target,
                original_callee=original,
                kind=RelationshipMetadata.DIRECT,
                local_name=static_alias.local_name,
                resolved_from_alias=True,
            )

        import_alias = self.import_aliases.get(raw_name)
        if import_alias:
            return CallTarget(
                callee=import_alias.imported_name,
                original_callee=original,
                kind=RelationshipMetadata.DIRECT,
                local_name=import_alias.local_name,
                imported_name=import_alias.imported_name,
                imported_from=import_alias.imported_from,
                resolved_from_alias=import_alias.local_name != import_alias.imported_name,
            )

        return CallTarget(
            callee=raw_name,
            original_callee=original,
            kind=RelationshipMetadata.OBJECT if object_name else RelationshipMetadata.DIRECT,
            object_name=object_name,
            method_name=method_name,
        )


class JavaScriptAnalyzer:
    def process_call(self, node, context: ParserContext, call: dict, metadata: dict) -> None:
        pass


class FunctionCallAnalyzer(JavaScriptAnalyzer):
    def process_call(self, node, context: ParserContext, call: dict, metadata: dict) -> None:
        metadata["calls"].append(call)


class DomReferenceAnalyzer(JavaScriptAnalyzer):
    _DOM_APIS = {
        "document.getElementById": "id",
        "getElementById": "id",
        "document.querySelector": "selector",
        "querySelector": "selector",
        "document.querySelectorAll": "selector",
        "querySelectorAll": "selector",
        "document.getElementsByClassName": "class",
        "getElementsByClassName": "class",
        "document.getElementsByTagName": "tag",
        "getElementsByTagName": "tag",
    }

    def process_call(self, node, context: ParserContext, call: dict, metadata: dict) -> None:
        callee = call.get("callee", "")
        # Normalize callee to match keys in _DOM_APIS (caller's method_name may also be present)
        api_name = call.get(RelationshipMetadata.METHOD_NAME) or (callee.split(".")[-1] if callee else None)
        candidates = [callee, api_name]
        kind = None
        for c in candidates:
            if not c:
                continue
            if c in self._DOM_APIS:
                kind = self._DOM_APIS[c]
                break
        if not kind:
            return

        # Inspect arguments for a static string selector only
        args = field_children(node, "arguments")
        if not args:
            return

        # Only consider the first argument for selector APIs
        first = args[0]
        if first.type != "string":
            # ignore dynamic selectors (template literals, concatenation, identifiers, etc.)
            return

        raw = strip_quotes(context.text(first))
        if raw is None:
            return

        selector = None
        selector_type = None

        if kind == "id":
            # getElementById/getElementById-like: raw is id WITHOUT '#'
            if raw:
                selector = f"#{raw}"
                selector_type = "id"
        elif kind == "class":
            if raw:
                selector = f".{raw}"
                selector_type = "class"
        elif kind == "tag":
            if raw and raw.isalpha():
                selector = raw
                selector_type = "tag"
        elif kind == "selector":
            # querySelector-family: the argument is a full selector string
            if raw.startswith("#"):
                selector = raw
                selector_type = "id"
            elif raw.startswith("."):
                selector = raw
                selector_type = "class"
            elif raw.startswith("[") and raw.endswith("]"):
                selector = raw
                selector_type = "attribute"
            elif raw.isalpha():
                selector = raw
                selector_type = "tag"
            else:
                # complex selectors (combinators, attribute selectors with spaces, etc.) are ignored for now
                return

        if not selector or not selector_type:
            return

        api = api_name or (callee.split(".")[-1] if callee else None)

        entry = {
            "caller": call.get("caller"),
            RelationshipMetadata.DOM_SELECTOR: selector,
            RelationshipMetadata.DOM_SELECTOR_TYPE: selector_type,
            RelationshipMetadata.DOM_API: api,
            "line": call.get("line"),
            # keep legacy key 'kind' for downstream compatibility
            "kind": selector_type,
        }

        metadata["dom_references"].append(entry)


class EventListenerAnalyzer(JavaScriptAnalyzer):
    _EVENT_METHOD = "addEventListener"

    def process_call(self, node, context: ParserContext, call: dict, metadata: dict) -> None:
        # Only care about addEventListener calls
        method = call.get(RelationshipMetadata.METHOD_NAME) or (call.get("callee", "").split(".")[-1] if call.get("callee") else None)
        if method != self._EVENT_METHOD:
            return

        # Need arguments: event name (string) and handler (named identifier or member_expression)
        args = field_children(node, "arguments")
        if len(args) < 2:
            return

        event_node = args[0]
        handler_node = args[1]

        if event_node.type != "string":
            # ignore dynamic event names for Phase 1
            return

        event_name = strip_quotes(context.text(event_node))
        if not event_name:
            return

        # Resolve handler to a stable name (identifier or member expression)
        handler_target = None
        if handler_node.type == "identifier":
            raw = context.text(handler_node)
            # resolve aliases/imports/static where possible
            target = context.resolve_target(raw, None, None)
            handler_target = target.callee
        elif handler_node.type == "member_expression":
            obj = expression_name(handler_node.child_by_field_name("object"), context)
            prop = property_name(handler_node.child_by_field_name("property"), context)
            raw = f"{obj}.{prop}" if obj and prop else None
            target = context.resolve_target(raw or "", obj, prop)
            handler_target = target.callee
        else:
            # ignore anonymous functions, arrow functions, function expressions, etc.
            return

        if not handler_target:
            return

        # Resolve event target to a selector or well-known host (document/window)
        obj_name = call.get(RelationshipMetadata.OBJECT_NAME) or None
        call_line = call.get("line")
        resolved_target = None

        # Direct host targets
        if obj_name in {"document", "window"}:
            resolved_target = obj_name
        else:
            # obj_name may be a call expression (e.g., document.querySelector())
            if isinstance(obj_name, str) and obj_name.endswith("()"):
                # extract api name like 'querySelector' from 'document.querySelector()'
                callee_name = obj_name[:-2]
                api = callee_name.split(".")[-1]
                # find a matching dom_references entry in metadata by api and caller and preceding line
                candidates = [d for d in metadata.get("dom_references", []) or [] if d.get(RelationshipMetadata.DOM_API) == api and d.get("caller") == call.get("caller")]
                if candidates:
                    # pick the closest preceding dom reference by line
                    before = [d for d in candidates if (d.get("line") or 0) <= (call_line or 0)]
                    chosen = max(before, key=lambda d: d.get("line") or 0) if before else max(candidates, key=lambda d: d.get("line") or 0)
                    resolved_target = chosen.get(RelationshipMetadata.DOM_SELECTOR) or chosen.get("selector")
            else:
                # try resolving via static alias table (e.g., btn -> document.getElementById())
                if isinstance(obj_name, str):
                    alias = context.resolve_alias(obj_name)
                    if alias:
                        target_raw = alias.target or ""
                        api = None
                        if target_raw.endswith("()"):
                            api = target_raw[:-2].split(".")[-1]
                        else:
                            api = target_raw.split(".")[-1] if "." in target_raw else target_raw
                        if api:
                            candidates = [d for d in metadata.get("dom_references", []) or [] if d.get(RelationshipMetadata.DOM_API) == api and d.get("caller") == call.get("caller")]
                            if candidates:
                                before = [d for d in candidates if (d.get("line") or 0) <= (call_line or 0)]
                                chosen = max(before, key=lambda d: d.get("line") or 0) if before else max(candidates, key=lambda d: d.get("line") or 0)
                                resolved_target = chosen.get(RelationshipMetadata.DOM_SELECTOR) or chosen.get("selector")
                # fallback: use the raw object name if nothing matched
                if not resolved_target and obj_name:
                    resolved_target = obj_name

        if not resolved_target:
            return

        entry = {
            "caller": call.get("caller"),
            RelationshipMetadata.EVENT_HANDLER: handler_target,
            RelationshipMetadata.EVENT_NAME: event_name,
            RelationshipMetadata.EVENT_TARGET: resolved_target,
            "line": call_line,
        }

        metadata.setdefault("event_listeners", []).append(entry)


class ClassListAnalyzer(JavaScriptAnalyzer):
    _OPS = {"add", "remove", "toggle", "replace", "contains"}

    def process_call(self, node, context: ParserContext, call: dict, metadata: dict) -> None:
        operation = call.get(RelationshipMetadata.METHOD_NAME) or (call.get("callee", "").split(".")[-1] if call.get("callee") else None)
        if not operation or operation not in self._OPS:
            return

        # Determine the object that .classList was invoked on
        obj_name = call.get(RelationshipMetadata.OBJECT_NAME) or None
        if not obj_name:
            return

        # Strip trailing '.classList' if present
        base_obj = obj_name
        if isinstance(base_obj, str) and base_obj.endswith(".classList"):
            base_obj = base_obj[: -len(".classList")]

        call_line = call.get("line")

        resolved_target = None

        # Direct hosts
        if base_obj in {"document", "window"}:
            resolved_target = base_obj

        # Call-expression targets like document.querySelector(".card") -> 'document.querySelector()'
        if not resolved_target and isinstance(base_obj, str) and base_obj.endswith("()"):
            callee_name = base_obj[:-2]
            api = callee_name.split(".")[-1]
            candidates = [d for d in metadata.get("dom_references", []) or [] if d.get(RelationshipMetadata.DOM_API) == api and d.get("caller") == call.get("caller")]
            if candidates:
                before = [d for d in candidates if (d.get("line") or 0) <= (call_line or 0)]
                chosen = max(before, key=lambda d: d.get("line") or 0) if before else max(candidates, key=lambda d: d.get("line") or 0)
                resolved_target = chosen.get(RelationshipMetadata.DOM_SELECTOR) or chosen.get("selector")

        # Alias resolution: variable pointing to a DOM lookup
        if not resolved_target and isinstance(base_obj, str):
            alias = context.resolve_alias(base_obj)
            if alias:
                target_raw = alias.target or ""
                api = None
                if isinstance(target_raw, str):
                    if target_raw.endswith("()"):
                        api = target_raw[:-2].split(".")[-1]
                    elif "." in target_raw:
                        api = target_raw.split(".")[-1]
                    else:
                        api = target_raw
                if api:
                    candidates = [d for d in metadata.get("dom_references", []) or [] if d.get(RelationshipMetadata.DOM_API) == api and d.get("caller") == call.get("caller")]
                    if candidates:
                        before = [d for d in candidates if (d.get("line") or 0) <= (call_line or 0)]
                        chosen = max(before, key=lambda d: d.get("line") or 0) if before else max(candidates, key=lambda d: d.get("line") or 0)
                        resolved_target = chosen.get(RelationshipMetadata.DOM_SELECTOR) or chosen.get("selector")

        # Fallback to the raw base_obj name
        if not resolved_target and base_obj:
            resolved_target = base_obj

        if not resolved_target:
            return

        # Extract class name arguments (must be literal strings)
        args = field_children(node, "arguments")
        if not args:
            return

        # For replace(), expect two string args
        if operation == "replace":
            if len(args) < 2:
                return
            old_arg, new_arg = args[0], args[1]
            if old_arg.type != "string" or new_arg.type != "string":
                return
            old_cls = strip_quotes(context.text(old_arg))
            new_cls = strip_quotes(context.text(new_arg))
            entry = {
                "caller": call.get("caller"),
                "target": resolved_target,
                "operation": operation,
                "old_class": old_cls,
                "new_class": new_cls,
                "line": call_line,
            }
            metadata.setdefault("class_ops", []).append(entry)
            return

        # For other ops, take first string argument only
        first = args[0]
        if first.type != "string":
            return
        cls = strip_quotes(context.text(first))
        entry = {
            "caller": call.get("caller"),
            "target": resolved_target,
            "operation": operation,
            "class_name": cls,
            "line": call_line,
        }
        metadata.setdefault("class_ops", []).append(entry)


class ModuleSymbolUsageAnalyzer(JavaScriptAnalyzer):
    def _ensure_entries(self, context: ParserContext, metadata: dict) -> None:
        # Initialize entries for all import aliases if not already present
        metadata.setdefault("module_symbol_usage", [])
        existing = set((e.get("symbol"), e.get("local_name"), e.get("imported_from")) for e in metadata.get("module_symbol_usage", []) or [])
        for alias in context.import_aliases.values():
            symbol = alias.imported_name or alias.local_name
            local_name = alias.local_name
            imported_from = alias.imported_from
            key = (symbol, local_name, imported_from)
            if key in existing:
                continue
            entry = {
                "symbol": symbol,
                "local_name": local_name,
                "imported_from": imported_from,
                "used": False,
                "line": None,
            }
            metadata["module_symbol_usage"].append(entry)
            existing.add(key)

    def process_call(self, node, context: ParserContext, call: dict, metadata: dict) -> None:
        # Ensure baseline entries exist
        self._ensure_entries(context, metadata)

        if not metadata.get("module_symbol_usage"):
            return

        # Try to detect usage from call metadata
        imported_from = call.get(RelationshipMetadata.IMPORTED_FROM)
        imported_name = call.get(RelationshipMetadata.IMPORTED_NAME)
        local_name = call.get(RelationshipMetadata.LOCAL_NAME)
        line = call.get("line")

        def mark_used(symbol, local, source, ln):
            for entry in metadata.get("module_symbol_usage", []) or []:
                if entry.get("symbol") == symbol and entry.get("local_name") == local and entry.get("imported_from") == source:
                    entry["used"] = True
                    if not entry.get("line") and ln is not None:
                        entry["line"] = ln
                    return True
            return False

        # Direct imported symbol (named/default) detected via imported_name/imported_from
        if imported_from:
            if imported_name and imported_name != "*":
                # find exact imported symbol
                if mark_used(imported_name, local_name or imported_name, imported_from, line):
                    return
            # Namespace import or fallback: mark entry by local_name or namespace
            if local_name:
                # find entry where local_name matches and imported_from matches
                for entry in metadata.get("module_symbol_usage", []) or []:
                    if entry.get("local_name") == local_name and entry.get("imported_from") == imported_from:
                        entry["used"] = True
                        if not entry.get("line") and line is not None:
                            entry["line"] = line
                        return

        # Fallback: if the raw callee equals a local import name, mark it used
        callee = call.get("callee")
        if callee:
            for entry in metadata.get("module_symbol_usage", []) or []:
                if entry.get("local_name") == callee:
                    entry["used"] = True
                    if not entry.get("line") and line is not None:
                        entry["line"] = line
                    return


DEFAULT_ANALYZERS = [
    FunctionCallAnalyzer(),
    DomReferenceAnalyzer(),
    EventListenerAnalyzer(),
    ClassListAnalyzer(),
    ModuleSymbolUsageAnalyzer(),
]


class JavaScriptVisitor:
    def __init__(self, context: ParserContext, analyzers: Optional[List[JavaScriptAnalyzer]] = None) -> None:
        self.context = context
        self.analyzers = analyzers or DEFAULT_ANALYZERS
        self.metadata = empty_metadata()

    def visit(self, node, parent=None) -> None:
        if node.type == "program":
            for child in node.named_children:
                self.visit(child, node)
            return

        if node.type == "import_statement":
            self._record_import(node)
            return

        if node.type == "export_statement":
            self._record_export(node)

        if node.type == "class_declaration":
            self._visit_class(node)
            return

        if node.type == "method_definition":
            self._visit_method(node)
            return

        if node.type in _FUNCTION_NODES:
            self._visit_function(node, function_name(node, parent, self.context))
            return

        if node.type in _DECLARATION_NODES:
            self._record_aliases(node)

        if node.type == "call_expression":
            self._record_call(node)

        for child in node.named_children:
            self.visit(child, node)

    def _visit_class(self, node) -> None:
        name_node = node.child_by_field_name("name")
        class_name = identifier_text(name_node, self.context)
        if class_name:
            self.metadata["classes"].append(class_name)
            self.context.class_stack.append(class_name)
        for child in node.named_children:
            if child is not name_node:
                self.visit(child, node)
        if class_name:
            self.context.class_stack.pop()

    def _visit_method(self, node) -> None:
        method = method_name(node, self.context)
        if method and self.context.current_class():
            method = f"{self.context.current_class()}.{method}"
        self._visit_function(node, method)

    def _visit_function(self, node, name: Optional[str]) -> None:
        if name:
            self.metadata["functions"].append(name)
            self.context.function_stack.append(name)
        self.context.push_scope()
        for child in node.named_children:
            self.visit(child, node)
        self.context.pop_scope()
        if name:
            self.context.function_stack.pop()

    def _record_import(self, node) -> None:
        source = first_string(node, self.context)
        if not source:
            return
        self.metadata["imports"].append(source)

        namespace_imports = [child for child in walk(node) if child.type == "namespace_import"]
        for namespace_import in namespace_imports:
            names = identifier_names(namespace_import, self.context)
            if names:
                self.context.add_import_alias(names[-1], "*", source)
        if namespace_imports:
            return

        specifiers = [child for child in walk(node) if child.type == "import_specifier"]
        if specifiers:
            for specifier in specifiers:
                names = identifier_names(specifier, self.context)
                if not names:
                    continue
                imported_name = names[0]
                local_name = names[-1]
                self.context.add_import_alias(local_name, imported_name, source)
            return

        names = [name for name in identifier_names(node, self.context) if name not in {"from"}]
        for local_name in names:
            self.context.add_import_alias(local_name, "default", source)

    def _record_export(self, node) -> None:
        for child in node.named_children:
            if child.type == "function_declaration":
                name = function_name(child, node, self.context)
                if name:
                    self.metadata["exports"].append(name)
            elif child.type == "class_declaration":
                name = identifier_text(child.child_by_field_name("name"), self.context)
                if name:
                    self.metadata["exports"].append(name)
            elif child.type in _DECLARATION_NODES:
                self.metadata["exports"].extend(declaration_names(child, self.context))
            elif child.type == "export_clause":
                self.metadata["exports"].extend(identifier_names(child, self.context))

    def _record_aliases(self, node) -> None:
        for declarator in [child for child in walk(node) if child.type == "variable_declarator"]:
            name_node = declarator.child_by_field_name("name")
            value = declarator.child_by_field_name("value")
            target = expression_name(value, self.context)
            if name_node and name_node.type == "object_pattern" and target:
                for local_name, member_name in destructured_object_aliases(name_node, self.context):
                    self.context.add_static_alias(local_name, f"{target}.{member_name}")
                continue

            name = identifier_text(name_node, self.context)
            if name and target and target != name:
                self.context.add_static_alias(name, target)

    def _record_call(self, node) -> None:
        caller = self.context.current_function()
        if not caller:
            return

        callee_node = node.child_by_field_name("function")
        raw_name = expression_name(callee_node, self.context)
        if not raw_name or raw_name in _JS_BUILTINS:
            return

        object_name = None
        method = None
        if callee_node and callee_node.type == "member_expression":
            object_name = expression_name(callee_node.child_by_field_name("object"), self.context)
            method = property_name(callee_node.child_by_field_name("property"), self.context)

        target = self.context.resolve_target(raw_name, object_name, method)
        call = {
            "caller": caller,
            "callee": target.callee,
            "line": self.context.line(node),
            RelationshipMetadata.KIND: target.kind,
            RelationshipMetadata.IS_OBJECT_CALL: target.kind == RelationshipMetadata.OBJECT,
            RelationshipMetadata.IS_IMPORTED: bool(target.imported_from),
            RelationshipMetadata.ORIGINAL_CALLEE: target.original_callee,
            RelationshipMetadata.RESOLVED_FROM_ALIAS: target.resolved_from_alias,
        }
        optional = {
            RelationshipMetadata.OBJECT_NAME: target.object_name,
            RelationshipMetadata.METHOD_NAME: target.method_name,
            RelationshipMetadata.LOCAL_NAME: target.local_name,
            RelationshipMetadata.IMPORTED_NAME: target.imported_name,
            RelationshipMetadata.IMPORTED_FROM: target.imported_from,
        }
        call.update({key: value for key, value in optional.items() if value})

        for analyzer in self.analyzers:
            analyzer.process_call(node, self.context, call, self.metadata)


def walk(node) -> Iterable[Any]:
    yield node
    for child in node.named_children:
        yield from walk(child)


def field_children(node, field_name: str) -> Iterable[Any]:
    field = node.child_by_field_name(field_name)
    if not field:
        return []
    return field.named_children


def strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] in {"'", '"', "`"} and value[-1] == value[0]:
        return value[1:-1]
    return value


def identifier_text(node, context: ParserContext) -> Optional[str]:
    if not node:
        return None
    if node.type in {"identifier", "property_identifier", "private_property_identifier"}:
        return context.text(node)
    return None


def property_name(node, context: ParserContext) -> Optional[str]:
    if not node:
        return None
    if node.type == "string":
        return strip_quotes(context.text(node))
    return identifier_text(node, context)


def expression_name(node, context: ParserContext) -> Optional[str]:
    if not node:
        return None
    if node.type in {"identifier", "property_identifier", "private_property_identifier"}:
        return context.text(node)
    if node.type == "this":
        return "this"
    if node.type == "string":
        return strip_quotes(context.text(node))
    if node.type == "member_expression":
        object_name = expression_name(node.child_by_field_name("object"), context)
        prop_name = property_name(node.child_by_field_name("property"), context)
        if object_name and prop_name:
            return f"{object_name}.{prop_name}"
    if node.type == "call_expression":
        callee_name = expression_name(node.child_by_field_name("function"), context)
        if callee_name:
            return f"{callee_name}()"
    return None


def method_name(node, context: ParserContext) -> Optional[str]:
    name_node = node.child_by_field_name("name")
    return property_name(name_node, context)


def function_name(node, parent, context: ParserContext) -> Optional[str]:
    name = identifier_text(node.child_by_field_name("name"), context)
    if name:
        return name

    if parent and parent.type == "variable_declarator":
        return identifier_text(parent.child_by_field_name("name"), context)

    if parent and parent.type == "assignment_expression":
        return expression_name(parent.child_by_field_name("left"), context)

    if parent and parent.type == "pair":
        return property_name(parent.child_by_field_name("key"), context)

    return None


def declaration_names(node, context: ParserContext) -> List[str]:
    names: List[str] = []
    for declarator in [child for child in walk(node) if child.type == "variable_declarator"]:
        name = identifier_text(declarator.child_by_field_name("name"), context)
        if name:
            names.append(name)
    return names


def destructured_object_aliases(node, context: ParserContext) -> List[tuple[str, str]]:
    aliases: List[tuple[str, str]] = []
    for child in node.named_children:
        if child.type in {"shorthand_property_identifier_pattern", "identifier"}:
            name = context.text(child)
            aliases.append((name, name))
            continue

        if child.type == "pair_pattern":
            key = property_name(child.child_by_field_name("key"), context)
            value = child.child_by_field_name("value")
            local = identifier_text(value, context)
            if key and local:
                aliases.append((local, key))
    return aliases


def identifier_names(node, context: ParserContext) -> List[str]:
    return [context.text(child) for child in walk(node) if child.type in {"identifier", "property_identifier"}]


def direct_identifier_names(node, context: ParserContext) -> List[str]:
    return [context.text(child) for child in node.named_children if child.type == "identifier"]


def first_string(node, context: ParserContext) -> Optional[str]:
    for child in walk(node):
        if child.type == "string":
            return strip_quotes(context.text(child))
    return None


def parse_javascript(content: str) -> dict:
    """
    Extract JavaScript / TypeScript metadata using static Tree-sitter AST traversal.
    """

    metadata = empty_metadata()
    backend = JavaScriptTreeSitterBackend()
    root = backend.parse(content)
    if root is None:
        metadata["warnings"].append("JavaScript AST parse failed; no JavaScript intelligence extracted.")
        return clean_metadata(metadata)

    context = ParserContext(content)
    visitor = JavaScriptVisitor(context)
    visitor.visit(root)
    return clean_metadata(visitor.metadata)
