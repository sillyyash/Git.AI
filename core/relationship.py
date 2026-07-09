"""
relationship.py

Phase 1 Relationship Builder. Sits between the Dependency Graph and the
Repository Inspector:

    Repository Scanner -> Language Parsers -> Repository Index
        -> Dependency Graph -> Relationship Builder (this file)
        -> Repository Inspector -> AI Engine

Pure Python. No AI. Every relationship here is derived directly from
parser metadata that already exists in the Repository Index.

Phase 1 relation types:

    HTML -> CSS   USES_CLASS       element  -> .class
    HTML -> ID    USES_ID          element  -> #id
    HTML -> JS    CALLS_FUNCTION   element  -> function()   (inline handlers)
    CSS  -> HTML  STYLES           .class/#id -> element(s) that use it
    JS   -> JS    CALLS            function -> function
    JS   -> HTML  REFERENCES       function -> #id / .class (DOM lookups)
    JS   -> CSS   USES_CLASS       function -> .class        (classList ops)
    *    -> *     IMPORTS          file -> imported file

-----------------------------------------------------------------------
Per-file metadata -- verified against the real parsers
(css_parser.py / html_parser.py / javascript_parser.py / parser_utils.py)
-----------------------------------------------------------------------

CSS (core/parsers/css_parser.py -> parse_css):
    selectors, css_classes, ids, imports, variables, animations, media_queries

HTML (core/parsers/html_parser.py -> parse_html):
    {
        "elements": [{"tag": str, "id": str|None, "classes": [str, ...]}, ...],
        "imports": [...],     # <link rel=stylesheet href> + <script src>
        "ids": [...],         # flat, same ids as in elements -- not used
        "css_classes": [...], # here (elements is the structured source of truth)
        # note: elements has NO attrs/onclick data today -- see below
    }

JS (core/parsers/javascript_parser.py -> parse_javascript):
    {
        "imports": [...],
        "functions": [...],   # flat list of names, including class methods like User.login
        "classes": [...],     # ES6 class names (unrelated to CSS classes)
        "exports": [...],
        "calls": [...],       # static CALLS edges with line + metadata
    }

-----------------------------------------------------------------------
Known Phase 1 gaps (data, not logic -- flagging rather than faking it)
-----------------------------------------------------------------------

1. HTML -> JS (CALLS_FUNCTION, inline handlers): html_parser.py's
   `elements` only captures tag/id/classes -- it does not read onclick=
   or any other attribute off the tag. So this relation type has no data
   source yet. The extraction code below is written defensively
   (checks element.get("handlers") / element.get("attrs")) so it will
   start producing edges the moment html_parser is extended to capture
   those attrs, with zero changes needed here.

2. JS -> JS (CALLS): javascript_parser.py now emits static call
   metadata from Tree-sitter AST traversal. DOM references and classList
   operations are consumed through the same metadata shape when analyzers
   emit them; CALLS remains the generic function-call relationship.

Everything else below (HTML<->CSS classes, HTML<->IDs, CSS->HTML STYLES,
Imports) is built from real, verified parser output.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Union


# ---------------------------------------------------------------------------
# Relation type constants
# ---------------------------------------------------------------------------

class Relation(str, Enum):
    USES_CLASS = "USES_CLASS"
    USES_ID = "USES_ID"
    CALLS_FUNCTION = "CALLS_FUNCTION"
    CALLS_METHOD = "CALLS_METHOD"
    CALLS = "CALLS"
    REFERENCES = "REFERENCES"
    STYLES = "STYLES"
    IMPORTS = "IMPORTS"
    INHERITS = "INHERITS"
    EVENT_BINDS = "EVENT_BINDS"
    MODIFIES_CLASS = "MODIFIES_CLASS"
    READS_ATTRIBUTE = "READS_ATTRIBUTE"
    FORM_CONTAINS = "FORM_CONTAINS"
    USES_ASSET = "USES_ASSET"
    USES_VARIABLE = "USES_VARIABLE"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Relationship:
    source: str
    relation: Relation
    target: str
    source_file: str
    line: Optional[int] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = {
            "source": self.source,
            "relation": self.relation.value,
            "target": self.target,
            "source_file": self.source_file,
        }
        if self.line is not None:
            data["line"] = self.line
        if self.metadata:
            data["metadata"] = self.metadata
        return data

    def __repr__(self) -> str:
        return f"<Relationship {self.source} {self.relation.value} {self.target}>"


class RelationshipGraph:
    """
    Flat list of Relationship records plus source/target indexes, mirroring
    the existing DependencyGraph shape.
    """

    def __init__(self) -> None:
        self.relationships: List[Relationship] = []
        self.lookup: Dict[str, List[Relationship]] = defaultdict(list)
        self.reverse_lookup: Dict[str, List[Relationship]] = defaultdict(list)
        self.relation_lookup: Dict[Relation, List[Relationship]] = defaultdict(list)
        self.file_lookup: Dict[str, List[Relationship]] = defaultdict(list)
        self._seen: Set[Tuple[str, Relation, str, str, Optional[int], Tuple[Tuple[str, str], ...]]] = set()

    def add(
        self,
        source: str,
        relation: Union[Relation, str],
        target: str,
        source_file: str,
        line: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[Relationship]:
        relation = self._normalize_relation(relation)
        metadata = metadata or {}
        metadata_key = tuple(sorted((k, repr(v)) for k, v in metadata.items()))
        key = (source, relation, target, source_file, line, metadata_key)

        if key in self._seen:
            return None

        self._seen.add(key)
        rel = Relationship(
            source=source,
            relation=relation,
            target=target,
            source_file=source_file,
            line=line,
            metadata=metadata,
        )
        self.relationships.append(rel)
        self.lookup[source].append(rel)
        self.reverse_lookup[target].append(rel)
        self.relation_lookup[relation].append(rel)
        self.file_lookup[source_file].append(rel)
        return rel

    def by_source(self, source: str) -> List[Relationship]:
        return self.lookup.get(source, [])

    def by_target(self, target: str) -> List[Relationship]:
        return self.reverse_lookup.get(target, [])

    def by_relation(self, relation: Union[Relation, str]) -> List[Relationship]:
        return self.relation_lookup.get(self._normalize_relation(relation), [])

    def by_file(self, source_file: str) -> List[Relationship]:
        return self.file_lookup.get(source_file, [])

    def __len__(self) -> int:
        return len(self.relationships)

    def __iter__(self):
        return iter(self.relationships)

    def to_list(self) -> List[dict]:
        return [r.to_dict() for r in self.relationships]

    def summary(self) -> Dict[str, int]:
        return {
            relation.value: len(self.relation_lookup.get(relation, []))
            for relation in Relation
        }

    @staticmethod
    def _normalize_relation(relation: Union[Relation, str]) -> Relation:
        if isinstance(relation, Relation):
            return relation
        return Relation(relation)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

_EVENT_ATTR_RE = re.compile(r"^on[a-z]+$", re.IGNORECASE)
_FUNC_CALL_RE = re.compile(r"([A-Za-z_$][A-Za-z0-9_$]*)\s*\(")


class RelationshipBuilder:
    """
    Usage:
        builder = RelationshipBuilder(repository_index)
        graph = builder.build()

    `repository_index` is a mapping of:
        file_path -> {"type": "html" | "css" | "js", "metadata": {...}}
    or, more simply:
        file_path -> metadata_dict   (file type inferred from extension)
    Both shapes are accepted -- see _iter_files.
    """

    def __init__(self, repository_index: dict) -> None:
        self.index = repository_index
        self.graph = RelationshipGraph()

        # Populated during pass 1 (HTML), consumed during pass 2 (CSS),
        # since a selector defined in one file may style elements declared
        # in a different file.
        self._html_classes: Dict[str, List[str]] = defaultdict(list)  # class -> [html files]
        self._html_ids: Dict[str, List[str]] = defaultdict(list)      # id -> [html files]

    # -- public --------------------------------------------------------

    def build(self) -> RelationshipGraph:
        # pass 1: per-file relationships that don't need cross-file context
        for file_path, file_type, metadata in self._iter_files():
            if file_type == "html":
                self._process_html(file_path, metadata)

            if file_type in {"js", "python"} or self._has_code_metadata(metadata):
                self._process_code(file_path, metadata)

            # event listeners (DOM) -> EVENT_BINDS
            if metadata.get("event_listeners"):
                self._process_event_listeners(file_path, metadata.get("event_listeners") or [])

            # class inheritance metadata -> INHERITS
            if metadata.get("class_inheritance"):
                self._process_inheritance(file_path, metadata.get("class_inheritance") or [])

            # HTML forms: form structures or elements with form attribute
            if metadata.get("forms") or any(
                (el.get("tag") == "form") for el in (metadata.get("elements") or [])
            ):
                self._process_forms(file_path, metadata)

            # assets (images/icons/fonts/videos)
            if any(metadata.get(k) for k in ("assets", "images", "icons", "fonts", "videos")):
                self._process_assets(file_path, metadata)

            self._process_imports(file_path, metadata)

        # pass 2: CSS -> HTML STYLES, needs the HTML usage collected above.
        # CSS metadata can come from .css files or from <style> blocks that
        # html_parser.py merged into an HTML file's metadata.
        for file_path, file_type, metadata in self._iter_files():
            if file_type == "css" or self._has_css_metadata(metadata):
                self._process_css_styles(file_path, metadata)

        return self.graph

    # -- iteration / type detection -------------------------------------

    def _iter_files(self):
        if hasattr(self.index, "files"):
            for file in self.index.files:
                yield file.path, self._language_type(file.language), self._file_metadata(file)
            return

        for file_path, entry in self.index.items():
            if isinstance(entry, dict) and "metadata" in entry:
                metadata = entry.get("metadata") or {}
                file_type = entry.get("type") or self._infer_type(file_path)
            else:
                metadata = entry or {}
                file_type = self._infer_type(file_path)
            yield file_path, file_type, metadata

    @staticmethod
    def _language_type(language: str) -> Optional[str]:
        normalized = language.strip().lower()
        if normalized == "html":
            return "html"
        if normalized in {"css", "scss"}:
            return "css"
        if normalized in {"javascript", "typescript", "react jsx", "react tsx"}:
            return "js"
        if normalized == "python":
            return "python"
        return None

    @staticmethod
    def _file_metadata(file) -> dict:
        return {
            "imports": file.imports,
            "functions": file.functions,
            "classes": file.classes,
            "exports": file.exports,
            "selectors": file.selectors,
            "ids": file.ids,
            "css_classes": file.css_classes,
            "variables": file.variables,
            "animations": file.animations,
            "media_queries": file.media_queries,
            "elements": file.elements,
            "calls": getattr(file, "calls", []),
            "dom_references": getattr(file, "dom_references", []),
            "class_ops": getattr(file, "class_ops", []),
        }

    @staticmethod
    def _has_code_metadata(metadata: dict) -> bool:
        return bool(
            metadata.get("calls")
            or metadata.get("dom_references")
            or metadata.get("class_ops")
        )

    @staticmethod
    def _has_css_metadata(metadata: dict) -> bool:
        return bool(
            metadata.get("selectors")
            or metadata.get("variables")
            or metadata.get("animations")
            or metadata.get("media_queries")
        )

    @staticmethod
    def _infer_type(file_path: str) -> Optional[str]:
        lower = file_path.lower()
        if lower.endswith((".html", ".htm")):
            return "html"
        if lower.endswith(".css"):
            return "css"
        if lower.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs")):
            return "js"
        if lower.endswith(".py"):
            return "python"
        return None

    # -- HTML -------------------------------------------------------------

    def _process_html(self, file_path: str, metadata: dict) -> None:
        # html_parser.py always emits "elements" (possibly []) as the
        # structured source of truth -- no flat-list fallback needed.
        self._process_html_elements(file_path, metadata.get("elements") or [])

    def _process_html_elements(self, file_path: str, elements: list) -> None:
        for index, element in enumerate(elements):
            identifier = self._element_identifier(element, index)
            elem_id = element.get("id")
            classes = element.get("classes") or []

            if elem_id:
                self._html_ids[elem_id].append(file_path)
                self._add_id_relation(elem_id, elem_id, file_path)

            for class_name in classes:
                self._html_classes[class_name].append(file_path)
                self._add_class_relation(identifier, class_name, file_path)

            for function_name in self._element_handler_functions(element):
                self._add_function_relation(identifier, function_name, file_path)

            # semantic attributes (aria-*, role, data-*) -> READS_ATTRIBUTE
            for attr_name, attr_value in (element.get("attrs") or {}).items():
                if not attr_name:
                    continue
                lower = attr_name.lower()
                if lower.startswith("aria-") or lower == "role" or lower.startswith("data-"):
                    self._add_reads_attribute(identifier, attr_name, file_path)

            # form membership via 'form' attr -> FORM_CONTAINS
            if (element.get("tag") or "").lower() in {"input", "button", "select", "textarea"}:
                form_ref = (element.get("attrs") or {}).get("form")
                if form_ref:
                    self._add_form_contains(form_ref, identifier, file_path)

    @staticmethod
    def _element_identifier(element: dict, index: int) -> str:
        if element.get("id"):
            return element["id"]
        classes = element.get("classes") or []
        if classes:
            return classes[0]
        tag = element.get("tag", "element")
        return f"{tag}#{index}"

    def _element_handler_functions(self, element: dict) -> List[str]:
        names: List[str] = []

        for handler in element.get("handlers") or element.get("events") or []:
            raw = handler.get("function") or handler.get("handler") or handler.get("value")
            if raw:
                name = self._extract_function_name(raw)
                if name:
                    names.append(name)

        for attr_name, attr_value in (element.get("attrs") or {}).items():
            if attr_value and _EVENT_ATTR_RE.match(attr_name):
                name = self._extract_function_name(attr_value)
                if name:
                    names.append(name)

        return names

    @staticmethod
    def _extract_function_name(raw: str) -> Optional[str]:
        match = _FUNC_CALL_RE.search(raw)
        if match:
            return match.group(1)
        raw = raw.strip()
        return raw or None

    # -- CSS -> HTML (STYLES) ------------------------------------------------

    def _process_css_styles(self, file_path: str, metadata: dict) -> None:
        for class_name in metadata.get("css_classes", []) or []:
            if class_name in self._html_classes:
                self._add_style_relation(f".{class_name}", class_name, file_path)

        for id_name in metadata.get("ids", []) or []:
            if id_name in self._html_ids:
                self._add_style_relation(f"#{id_name}", id_name, file_path)

        # CSS variable usages: metadata may provide variable_uses like
        # [{'selector': '.btn', 'variable': '--color-primary'}]
        for use in metadata.get("variable_uses", []) or []:
            if isinstance(use, dict):
                selector = use.get("selector") or use.get("target")
                variable = use.get("variable") or use.get("name")
                if selector and variable:
                    self._add_uses_variable(selector, variable, file_path)
            else:
                # permissive fallback for tuples or strings
                try:
                    selector, variable = use
                    self._add_uses_variable(selector, variable, file_path)
                except Exception:
                    continue

    # -- Code relationships --------------------------------------------------

    def _process_code(self, file_path: str, metadata: dict) -> None:
        # Plain function-name entries are definitions only. Rich parser
        # metadata below supplies call, DOM reference, and classList edges.
        for func in metadata.get("functions", []) or []:
            if not isinstance(func, dict):
                continue
            caller = func.get("name")
            if not caller:
                continue
            self._process_code_calls(file_path, caller, func.get("calls", []) or [])
            self._process_dom_refs(file_path, caller, func.get("dom_refs", []) or [])
            self._process_class_ops(file_path, caller, func.get("class_ops", []) or [])

        # module-scope / flat fallbacks -- same story, only fire if a
        # future parser version populates them.
        for call in metadata.get("calls", []) or []:
            caller = call.get("caller", "module")
            callee = call.get("callee")
            if callee:
                self._add_call_function_or_method(caller, callee, file_path, call)

        for ref in metadata.get("dom_references", []) or []:
            caller = ref.get("caller", "module")
            self._process_dom_refs(file_path, caller, [ref])

        for op in metadata.get("class_ops", []) or []:
            caller = op.get("caller", "module")
            self._process_class_ops(file_path, caller, [op])

    def _process_code_calls(self, file_path: str, caller: str, calls: list) -> None:
        for callee in calls:
            call_meta = None
            if isinstance(callee, dict):
                call_meta = callee
                callee = callee.get("callee") or callee.get("name")
            if callee:
                self._add_call_function_or_method(caller, callee, file_path, call_meta)

    def _process_dom_refs(self, file_path: str, caller: str, refs: list) -> None:
        for ref in refs:
            selector = ref.get("selector") or ref.get("id") or ref.get("class_name")
            kind = ref.get("kind") or ("id" if ref.get("id") else "class")
            if selector:
                target = self._selector_target(selector, kind)
                self._add_reference_relation(caller, target, file_path)

    def _process_class_ops(self, file_path: str, caller: str, ops: list) -> None:
        for op in ops:
            class_name = op.get("class_name") or op.get("class")
            if class_name:
                # class_ops represent runtime classList modifications; map to MODIFIES_CLASS
                self._add_modifies_class(caller, class_name, file_path)

    def _process_event_listeners(self, file_path: str, listeners: list) -> None:
        """Process metadata['event_listeners'] entries.
        Expected shapes (intentionally permissive):
            {"target": "#id", "event": "click", "handler": "onClick"}
            {"selector": ".btn", "event": "submit", "handler": {...}}
        Creates: DOM Target -> EVENT_BINDS -> event
        Optionally: Handler -> REFERENCES -> DOM Target
        """
        for entry in listeners:
            if not isinstance(entry, dict):
                continue
            selector = entry.get("selector") or entry.get("target") or entry.get("id") or entry.get("class")
            event = entry.get("event") or entry.get("type")
            handler = entry.get("handler") or entry.get("function")
            if not selector or not event:
                continue
            target = self._selector_target(selector, "id" if selector.startswith("#") else None)
            self._add_event_bind(target, event, file_path)
            if handler and isinstance(handler, str):
                # link handler -> REFERENCES -> DOM target
                self._add_reference_relation(handler, target, file_path)

    def _process_inheritance(self, file_path: str, inheritance_data) -> None:
        """Process class inheritance metadata.
        Accepts list of dicts like {'child':'Sub','parent':'Base'} or mapping {child: parent}.
        """
        if isinstance(inheritance_data, dict):
            items = list(inheritance_data.items())
        else:
            items = []
            for entry in inheritance_data or []:
                if isinstance(entry, dict):
                    child = entry.get("child") or entry.get("subclass") or entry.get("class")
                    parent = entry.get("parent") or entry.get("superclass") or entry.get("extends")
                    if child and parent:
                        items.append((child, parent))
        for child, parent in items:
            self._add_inherits_relation(child, parent, file_path)

    def _process_forms(self, file_path: str, metadata: dict) -> None:
        # metadata['forms'] could be a structured list, otherwise try to link by element attrs
        forms = metadata.get("forms") or []
        for form in forms:
            if not isinstance(form, dict):
                continue
            form_id = form.get("id") or form.get("name") or form.get("identifier")
            if not form_id:
                continue
            for field in form.get("inputs", []) or form.get("fields", []) or []:
                if isinstance(field, dict):
                    fid = field.get("id") or field.get("name") or field.get("identifier") or (field.get("tag") and self._element_identifier(field, 0))
                else:
                    fid = field
                if fid:
                    self._add_form_contains(form_id, fid, file_path)

        # fallback: elements with form attribute point to a form id
        for element in metadata.get("elements") or []:
            tag = (element.get("tag") or "").lower()
            if tag in {"input", "button", "select", "textarea"}:
                form_attr = (element.get("attrs") or {}).get("form")
                if form_attr:
                    element_id = self._element_identifier(element, 0)
                    self._add_form_contains(form_attr, element_id, file_path)

    def _process_assets(self, file_path: str, metadata: dict) -> None:
        # HTML file -> USES_ASSET -> asset (image/font/video/icon)
        for key in ("assets", "images", "icons", "fonts", "videos"):
            for asset in metadata.get(key, []) or []:
                if isinstance(asset, dict):
                    # common shapes: {src:..., type:...}
                    src = asset.get("src") or asset.get("href") or asset.get("url")
                    if src:
                        self._add_uses_asset(file_path, src, file_path)
                else:
                    if asset:
                        self._add_uses_asset(file_path, asset, file_path)

    # -- Relationship helpers -------------------------------------------------

    def _add_class_relation(self, source: str, class_name: str, source_file: str) -> None:
        self.graph.add(
            source=source,
            relation=Relation.USES_CLASS,
            target=self._class_target(class_name),
            source_file=source_file,
        )

    def _add_id_relation(self, source: str, id_name: str, source_file: str) -> None:
        self.graph.add(
            source=source,
            relation=Relation.USES_ID,
            target=self._id_target(id_name),
            source_file=source_file,
        )

    def _add_function_relation(self, source: str, function_name: str, source_file: str) -> None:
        self.graph.add(
            source=source,
            relation=Relation.CALLS_FUNCTION,
            target=function_name,
            source_file=source_file,
        )

    def _add_style_relation(self, source: str, target: str, source_file: str) -> None:
        self.graph.add(
            source=source,
            relation=Relation.STYLES,
            target=target,
            source_file=source_file,
        )

    def _add_call_relation(self, caller: str, callee: str, source_file: str, call: Optional[dict] = None) -> None:
        call = call or {}
        metadata = {
            key: value
            for key, value in call.items()
            if key not in {"caller", "callee", "line"} and value is not None
        }
        self.graph.add(
            source=caller,
            relation=Relation.CALLS,
            target=callee,
            source_file=source_file,
            line=call.get("line"),
            metadata=metadata,
        )

    def _add_call_function_or_method(self, caller: str, callee: str, source_file: str, call: Optional[dict] = None) -> None:
        """Add either CALLS_FUNCTION or CALLS_METHOD where possible.
        Heuristics:
          - If call metadata contains 'kind'/'type' indicating 'method' use CALLS_METHOD
          - If callee contains a dot (obj.method or Class.method) treat as method
          - Else fallback to CALLS_FUNCTION
        Falls back to generic CALLS if relation should remain generic.
        """
        call = call or {}
        kind = (call.get("kind") or call.get("type") or "").lower()
        is_method = False
        if kind in {"method", "member", "instance_method", "static_method"}:
            is_method = True
        if not is_method and isinstance(callee, str) and ("." in callee or "#" in callee or "::" in callee):
            is_method = True

        metadata = {
            key: value
            for key, value in call.items()
            if key not in {"caller", "callee", "line"} and value is not None
        }

        if is_method:
            self.graph.add(
                source=caller,
                relation=Relation.CALLS_METHOD,
                target=callee,
                source_file=source_file,
                line=call.get("line"),
                metadata=metadata,
            )
        else:
            # prefer explicit function edge for clearer queries
            self.graph.add(
                source=caller,
                relation=Relation.CALLS_FUNCTION,
                target=callee,
                source_file=source_file,
                line=call.get("line"),
                metadata=metadata,
            )

    def _add_reference_relation(self, caller: str, target: str, source_file: str) -> None:
        self.graph.add(
            source=caller,
            relation=Relation.REFERENCES,
            target=target,
            source_file=source_file,
        )

    def _add_import_relation(self, source_file: str, target: str) -> None:
        self.graph.add(
            source=source_file,
            relation=Relation.IMPORTS,
            target=target,
            source_file=source_file,
        )

    def _add_event_bind(self, target: str, event: str, source_file: str) -> None:
        self.graph.add(
            source=target,
            relation=Relation.EVENT_BINDS,
            target=event,
            source_file=source_file,
        )

    def _add_inherits_relation(self, child: str, parent: str, source_file: str) -> None:
        self.graph.add(
            source=child,
            relation=Relation.INHERITS,
            target=parent,
            source_file=source_file,
        )

    def _add_modifies_class(self, source: str, class_name: str, source_file: str) -> None:
        self.graph.add(
            source=source,
            relation=Relation.MODIFIES_CLASS,
            target=self._class_target(class_name),
            source_file=source_file,
        )

    def _add_reads_attribute(self, source: str, attribute: str, source_file: str) -> None:
        self.graph.add(
            source=source,
            relation=Relation.READS_ATTRIBUTE,
            target=attribute,
            source_file=source_file,
        )

    def _add_form_contains(self, form_identifier: str, element_identifier: str, source_file: str) -> None:
        self.graph.add(
            source=form_identifier,
            relation=Relation.FORM_CONTAINS,
            target=element_identifier,
            source_file=source_file,
        )

    def _add_uses_asset(self, source_file: str, asset: str, origin_file: str) -> None:
        self.graph.add(
            source=source_file,
            relation=Relation.USES_ASSET,
            target=asset,
            source_file=origin_file,
        )

    def _add_uses_variable(self, selector: str, variable: str, source_file: str) -> None:
        self.graph.add(
            source=selector,
            relation=Relation.USES_VARIABLE,
            target=variable,
            source_file=source_file,
        )

    @staticmethod
    def _selector_target(selector: str, kind: Optional[str] = None) -> str:
        selector = selector.strip()
        if selector.startswith(("#", ".")):
            return selector
        if kind == "id":
            return f"#{selector}"
        return f".{selector}"

    @staticmethod
    def _class_target(class_name: str) -> str:
        class_name = class_name.strip()
        return class_name if class_name.startswith(".") else f".{class_name}"

    @staticmethod
    def _id_target(id_name: str) -> str:
        id_name = id_name.strip()
        return id_name if id_name.startswith("#") else f"#{id_name}"

    # -- Imports (any file type) ----------------------------------------------

    def _process_imports(self, file_path: str, metadata: dict) -> None:
        for target in metadata.get("imports", []) or []:
            if not target:
                continue
            self._add_import_relation(file_path, target)
