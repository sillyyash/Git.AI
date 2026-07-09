"""Dead code and import/export analysis.

Functions:
- find_dead_code(graph, repository_index=None): returns unused functions, classes, unreachable modules
- find_unused_imports(graph, repository_index=None): returns imported symbols that appear unused
- find_unused_exports(graph, repository_index=None): returns exported symbols with no incoming references

All functions operate on the RelationshipGraph and optional repository_index
structure produced by the parsers. They do NOT read source files.
"""
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict, deque

from core.relationship import RelationshipGraph, Relation


def find_dead_code(graph: RelationshipGraph, repository_index: Optional[dict] = None) -> dict:
    """Detect dead code using the graph + optional repository_index.

    Returns a dictionary with keys:
      - unused_functions: list of function identifiers
      - unused_classes: list of class identifiers
      - unreachable_modules: list of file paths

    repository_index (optional) should be the same shape used by RelationshipBuilder
    (file_path -> metadata dict). When available, definitions for functions/classes
    are derived from that index for higher accuracy. When not available the algorithm
    falls back to simple graph heuristics.
    """
    # Gather defined functions and classes from repository_index if available
    defined_functions: Set[str] = set()
    defined_classes: Set[str] = set()
    all_files: Set[str] = set()

    if repository_index:
        for file_path, meta in repository_index.items():
            all_files.add(file_path)
            for f in (meta.get("functions") or []) or []:
                if isinstance(f, dict):
                    name = f.get("name")
                else:
                    name = f
                if name:
                    defined_functions.add(name)
            for c in (meta.get("classes") or []) or []:
                if isinstance(c, dict):
                    name = c.get("name") or c.get("class")
                else:
                    name = c
                if name:
                    defined_classes.add(name)
    else:
        # Fallback: infer functions and classes from relationship targets/sources
        for rel in graph:
            # function targets are commonly used as call targets; include them
            if rel.relation in {Relation.CALLS, Relation.CALLS_FUNCTION, Relation.CALLS_METHOD}:
                defined_functions.add(rel.target)
            if rel.relation == Relation.INHERITS:
                defined_classes.add(rel.source)
                defined_classes.add(rel.target)

    # Find used functions/classes via incoming call and reference edges
    used_functions: Set[str] = set()
    used_classes: Set[str] = set()

    # Consider CALLS, CALLS_FUNCTION, CALLS_METHOD, REFERENCES, INHERITS as usage indicators
    for rel in graph.by_relation(Relation.CALLS) + graph.by_relation(Relation.CALLS_FUNCTION) + graph.by_relation(Relation.CALLS_METHOD):
        if rel.target:
            used_functions.add(rel.target)
    for rel in graph.by_relation(Relation.REFERENCES) + graph.by_relation(Relation.INHERITS):
        if rel.target:
            # INHERITS target is a parent class -> mark used class
            used_classes.add(rel.target)
            used_classes.add(rel.source)

    # Unused functions / classes are definitions with no usage
    unused_functions = sorted(list(defined_functions - used_functions))
    unused_classes = sorted(list(defined_classes - used_classes))

    # Unreachable modules: derive import graph from IMPORTS relations
    imports_out: Dict[str, List[str]] = defaultdict(list)
    imports_in_degree: Dict[str, int] = defaultdict(int)
    known_files: Set[str] = set()
    for rel in graph.by_relation(Relation.IMPORTS):
        known_files.add(rel.source_file)
        target = rel.target
        if not target:
            continue
        imports_out[rel.source_file].append(target)
        imports_in_degree[target] += 1
        known_files.add(target)

    # Identify roots: files present in known_files with in_degree == 0
    roots = [f for f in known_files if imports_in_degree.get(f, 0) == 0]

    # BFS/DFS from roots to mark reachable
    reachable: Set[str] = set()
    dq = deque(roots)
    while dq:
        node = dq.popleft()
        if node in reachable:
            continue
        reachable.add(node)
        for child in imports_out.get(node, []):
            if child not in reachable:
                dq.append(child)

    # If repository_index provided, use that as authoritative file list
    files_to_check = set(repository_index.keys()) if repository_index else known_files
    unreachable_modules = sorted([f for f in files_to_check if f not in reachable])

    return {
        "unused_functions": unused_functions,
        "unused_classes": unused_classes,
        "unreachable_modules": unreachable_modules,
    }


def find_unused_imports(graph: RelationshipGraph, repository_index: Optional[dict] = None) -> Dict[str, List[str]]:
    """Detect imports which are never referenced in code.

    Returns mapping: file_path -> list of unused imports (string identifiers).

    repository_index may contain structured import data (list of dicts or strings).
    When structured imports include named imports, this function attempts to
    determine whether the imported symbols are referenced via graph edges
    (REFERENCES, CALLS, etc.).
    """
    unused_by_file: Dict[str, List[str]] = defaultdict(list)

    # Build a quick lookup of all referenced symbols (targets of REFERENCES, CALLS*)
    referenced: Set[str] = set()
    for rel in graph.by_relation(Relation.REFERENCES) + graph.by_relation(Relation.CALLS) + graph.by_relation(Relation.CALLS_FUNCTION) + graph.by_relation(Relation.CALLS_METHOD):
        if rel.target:
            referenced.add(rel.target)

    if not repository_index:
        # Best-effort: find file-level imports from graph and mark imported file if never referenced
        for rel in graph.by_relation(Relation.IMPORTS):
            # If imported file is never the target of a reference or call, consider the import unused
            if rel.target not in referenced:
                unused_by_file.setdefault(rel.source_file, []).append(rel.target)
        return unused_by_file

    # Inspect structured imports in repository_index
    for file_path, meta in repository_index.items():
        imports = meta.get("imports") or []
        # imports may be strings (module paths) or dicts with named imports
        for item in imports:
            if isinstance(item, dict):
                # shape: {module: 'mod', names: ['A','B']} or {from: 'mod', import: ['A','B']}
                names = []
                module = item.get("module") or item.get("from") or item.get("path") or item.get("target")
                for key in ("names", "import", "symbols", "specifiers"):
                    if item.get(key):
                        names = item.get(key)
                        break
                if not names:
                    # if no named symbols, fallback to module-level check
                    if module and module not in referenced:
                        unused_by_file[file_path].append(module)
                    continue
                for name in names:
                    # if symbol not referenced anywhere, mark unused
                    if name not in referenced:
                        unused_by_file[file_path].append(f"{module}:{name}" if module else name)
            else:
                # plain string import
                mod = item
                if mod and mod not in referenced:
                    unused_by_file[file_path].append(mod)

    return unused_by_file


def find_unused_exports(graph: RelationshipGraph, repository_index: Optional[dict] = None) -> Dict[str, List[str]]:
    """Detect exported symbols that have no incoming references.

    Returns mapping file_path -> list of unused exported symbols.
    """
    unused_by_file: Dict[str, List[str]] = defaultdict(list)

    # Build incoming reference target map
    incoming_targets: Set[str] = set()
    for rel in graph.by_relation(Relation.REFERENCES) + graph.by_relation(Relation.CALLS) + graph.by_relation(Relation.CALLS_FUNCTION) + graph.by_relation(Relation.CALLS_METHOD):
        if rel.target:
            incoming_targets.add(rel.target)

    if not repository_index:
        # Attempt to infer exports from graph: targets that appear as sources in CALLS but with no incoming refs
        # This is weaker; return empty mapping to indicate lack of index
        return {}

    for file_path, meta in repository_index.items():
        exports = meta.get("exports") or []
        for e in exports:
            name = e if isinstance(e, str) else (e.get("name") or e.get("symbol"))
            if not name:
                continue
            if name not in incoming_targets:
                unused_by_file[file_path].append(name)

    return unused_by_file
