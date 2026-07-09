import ast

from core.parsers.parser_utils import empty_metadata, clean_metadata


class _CallCollector(ast.NodeVisitor):
    def __init__(self):
        self.functions = []
        self.classes = []
        self.imports = []
        self.calls = []
        self._function_stack = []
        self._class_stack = []
        # import aliases: local_name -> (imported_name, imported_from)
        self.import_aliases = {}
        # module symbol usage tracking
        self._import_usage = {}
        # decorators
        self.decorators = []
        # class inheritance
        self.class_inheritance = []

    def visit_Import(self, node):
        for alias in node.names:
            local = alias.asname or alias.name
            imported_from = alias.name
            imported_name = alias.name
            self.imports.append(imported_from)
            self.import_aliases[local] = (imported_name, imported_from)
            self._import_usage[local] = {"symbol": imported_name, "local_name": local, "imported_from": imported_from, "used": False, "line": None}

    def visit_ImportFrom(self, node):
        module = node.module or ""
        for alias in node.names:
            local = alias.asname or alias.name
            imported_name = alias.name
            imported_from = module
            self.imports.append(f"{module}.{imported_name}")
            self.import_aliases[local] = (imported_name, imported_from)
            self._import_usage[local] = {"symbol": imported_name, "local_name": local, "imported_from": imported_from, "used": False, "line": None}

    def visit_FunctionDef(self, node):
        # Build full name including class if present
        if self._class_stack:
            full_name = f"{self._class_stack[-1]}.{node.name}"
        else:
            full_name = node.name
        self.functions.append(full_name)

        # decorators
        decs = []
        for d in node.decorator_list:
            name = self._expr_name(d)
            if name:
                decs.append(name)
        if decs:
            self.decorators.append({"function": full_name, "decorators": decs})

        self._function_stack.append(full_name)
        self.generic_visit(node)
        self._function_stack.pop()

    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node):
        self.classes.append(node.name)
        # gather base class names
        bases = []
        for b in node.bases:
            bn = self._expr_name(b)
            if bn:
                bases.append(bn)
        if bases:
            self.class_inheritance.append({"class": node.name, "bases": bases})

        self._class_stack.append(node.name)
        # visit body
        for child in node.body:
            self.visit(child)
        self._class_stack.pop()

    def visit_Call(self, node):
        caller = self._function_stack[-1] if self._function_stack else "module"
        callee = self._call_name(node.func)
        lineno = getattr(node, "lineno", None)

        if callee:
            self.calls.append({"caller": caller, "callee": callee, "line": lineno})

            # mark imported symbol usage if callee uses a local import name
            # callee may be dotted like utils.render
            parts = callee.split(".")
            if parts and parts[0] in self.import_aliases:
                info = self._import_usage.get(parts[0])
                if info and not info.get("used"):
                    info["used"] = True
                    info["line"] = lineno

            # if callee is direct local name that matches an import
            if callee in self.import_aliases:
                info = self._import_usage.get(callee)
                if info and not info.get("used"):
                    info["used"] = True
                    info["line"] = lineno

        self.generic_visit(node)

    def _expr_name(self, node):
        # Return dotted name for Name and Attribute nodes
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            value = self._expr_name(node.value)
            if value:
                return f"{value}.{node.attr}"
            return node.attr
        if isinstance(node, ast.Call):
            return self._expr_name(node.func)
        return None

    def _call_name(self, node):
        # Similar to _expr_name but specialized for call func nodes
        return self._expr_name(node)


def parse_python(content: str) -> dict:
    """
    Parse a Python source file and extract metadata, including a simple
    function call graph for Relationship Builder Phase 2.
    """

    metadata = empty_metadata()

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return metadata

    collector = _CallCollector()
    collector.visit(tree)

    metadata["imports"] = collector.imports
    metadata["functions"] = collector.functions
    metadata["classes"] = collector.classes
    metadata["decorators"] = collector.decorators
    metadata["class_inheritance"] = collector.class_inheritance

    # module symbol usage: populate entries from collector._import_usage
    metadata["module_symbol_usage"] = list(collector._import_usage.values())

    known_functions = set(collector.functions)
    # Build calls graph only for known functions/methods
    metadata["calls"] = [
        call
        for call in collector.calls
        if call["callee"] in known_functions and call["caller"] != call["callee"]
    ]

    return clean_metadata(metadata)
