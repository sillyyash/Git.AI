"""
Public query API for AutoDevAI graph data.

Planner code should ask domain questions here instead of reaching into
DependencyGraph or RelationshipGraph internals directly.
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Set

from core.graph import DependencyGraph
from core.relationship import Relation, RelationshipGraph


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _unique(items: List[str]) -> List[str]:
    return list(dict.fromkeys(item for item in items if item))


def _class_selector(class_name: str) -> str:
    class_name = class_name.strip()
    return class_name if class_name.startswith(".") else f".{class_name}"


def _id_selector(html_id: str) -> str:
    html_id = html_id.strip()
    return html_id if html_id.startswith("#") else f"#{html_id}"


def _selector_targets(selector: str) -> List[str]:
    selector = selector.strip()

    if not selector:
        return []

    if selector.startswith((".", "#")):
        return [selector]

    return [f".{selector}", f"#{selector}"]


def _symbol_file(graph: DependencyGraph, symbol: str) -> Optional[str]:
    if symbol.startswith("."):
        return graph.css_classes.get(symbol[1:]) or graph.selectors.get(symbol)

    if symbol.startswith("#"):
        return graph.ids.get(symbol[1:]) or graph.selectors.get(symbol)

    return (
        graph.functions.get(symbol)
        or graph.classes.get(symbol)
        or graph.css_classes.get(symbol)
        or graph.ids.get(symbol)
        or graph.selectors.get(symbol)
    )


# ---------------------------------------------------------------------------
# HTML / CSS questions
# ---------------------------------------------------------------------------

def find_html_for_selector(
    graph: DependencyGraph,
    relationships: RelationshipGraph,
    selector: str,
) -> List[str]:
    """Return HTML files containing elements that use a class/id selector."""

    files: List[str] = []

    for target in _selector_targets(selector):
        for relationship in relationships.by_target(target):
            if relationship.relation in {Relation.USES_CLASS, Relation.USES_ID}:
                files.append(relationship.source_file)

    if not selector.startswith((".", "#")):
        files.extend(graph.elements.get(selector, []))

    return _unique(files)


def find_elements_using_selector(
    relationships: RelationshipGraph,
    selector: str,
) -> List[str]:
    """Return element identifiers that use the given class/id selector."""

    elements: List[str] = []

    for target in _selector_targets(selector):
        for relationship in relationships.by_target(target):
            if relationship.relation in {Relation.USES_CLASS, Relation.USES_ID}:
                elements.append(relationship.source)

    return _unique(elements)


def find_files_using_class(
    relationships: RelationshipGraph,
    class_name: str,
) -> List[str]:
    """Return files that reference a CSS class from HTML or code."""

    target = _class_selector(class_name)

    return _unique(
        [
            relationship.source_file
            for relationship in relationships.by_target(target)
            if relationship.relation == Relation.USES_CLASS
        ]
    )


def find_style_chain(
    relationships: RelationshipGraph,
    selector: str,
) -> Dict[str, List[str]]:
    """Return styling flow for a selector: CSS selector -> used elements/files."""

    targets = _selector_targets(selector)
    styled_symbols: List[str] = []
    style_files: List[str] = []

    for target in targets:
        for relationship in relationships.by_source(target):
            if relationship.relation == Relation.STYLES:
                styled_symbols.append(relationship.target)
                style_files.append(relationship.source_file)

    return {
        "selectors": targets,
        "styled_symbols": _unique(styled_symbols),
        "elements": find_elements_using_selector(relationships, selector),
        "files": _unique(style_files),
    }


# ---------------------------------------------------------------------------
# Function / call graph questions
# ---------------------------------------------------------------------------

def find_functions_called_by(
    relationships: RelationshipGraph,
    function_name: str,
) -> List[str]:
    """Return direct function calls made by function_name."""

    return _unique(
        [
            relationship.target
            for relationship in relationships.by_source(function_name)
            if relationship.relation == Relation.CALLS
        ]
    )


def find_call_chain(
    relationships: RelationshipGraph,
    function_name: str,
    max_depth: int = 10,
) -> List[str]:
    """Return functions reachable from function_name through CALLS edges."""

    visited: Set[str] = set()
    ordered: List[str] = []
    queue = deque([(function_name, 0)])

    while queue:
        current, depth = queue.popleft()

        if depth >= max_depth:
            continue

        for callee in find_functions_called_by(relationships, current):
            if callee in visited:
                continue

            visited.add(callee)
            ordered.append(callee)
            queue.append((callee, depth + 1))

    return ordered


# ---------------------------------------------------------------------------
# Import / dependency questions
# ---------------------------------------------------------------------------

def find_import_chain(
    graph: DependencyGraph,
    start_file: str,
    target_file: Optional[str] = None,
) -> List[str]:
    """Return an import path from start_file to target_file, or DFS order.

    If target_file is omitted, the returned list starts with start_file and
    then lists reachable imports in traversal order.
    """

    if target_file is None:
        chain = [start_file]
        chain.extend(find_all_dependencies(graph, start_file))
        return chain

    queue = deque([(start_file, [start_file])])
    visited = {start_file}

    while queue:
        current, path = queue.popleft()

        for dependency in graph.imports.get(current, []):
            if dependency == target_file:
                return path + [dependency]

            if dependency in visited:
                continue

            visited.add(dependency)
            queue.append((dependency, path + [dependency]))

    return []


def find_all_dependencies(graph: DependencyGraph, file_path: str) -> List[str]:
    """Return every transitive import reachable from file_path."""

    dependencies: List[str] = []
    visited: Set[str] = set()
    stack = list(reversed(graph.imports.get(file_path, [])))

    while stack:
        dependency = stack.pop()

        if dependency in visited:
            continue

        visited.add(dependency)
        dependencies.append(dependency)

        for child in reversed(graph.imports.get(dependency, [])):
            if child not in visited:
                stack.append(child)

    return dependencies


def find_related_files(
    graph: DependencyGraph,
    relationships: RelationshipGraph,
    file_path: str,
) -> List[str]:
    """Return files directly related through imports and relationship edges."""

    related: List[str] = []

    related.extend(graph.imports.get(file_path, []))
    related.extend(graph.reverse_imports.get(file_path, []))

    for relationship in relationships.by_file(file_path):
        target_file = _symbol_file(graph, relationship.target)
        if target_file:
            related.append(target_file)

        source_file = _symbol_file(graph, relationship.source)
        if source_file:
            related.append(source_file)

    for relationship in relationships.by_relation(Relation.IMPORTS):
        if relationship.target == file_path:
            related.append(relationship.source_file)

    return [item for item in _unique(related) if item != file_path]


# ---------------------------------------------------------------------------
# Repository Reasoning public API (thin wrappers over core.reasoning)
# ---------------------------------------------------------------------------

from core import reasoning


def find_dead_code(
    relationships: RelationshipGraph,
    repository_index: Optional[dict] = None,
):
    """Detect dead code: unused functions, classes, unreachable modules.

    Returns the same structure as core.reasoning.dead_code.find_dead_code.
    """
    return reasoning.find_dead_code(relationships, repository_index)


def find_unused_imports(
    relationships: RelationshipGraph,
    repository_index: Optional[dict] = None,
):
    """Return imported symbols that are not referenced.

    Mapping file_path -> list of unused imports.
    """
    return reasoning.find_unused_imports(relationships, repository_index)


def find_unused_exports(
    relationships: RelationshipGraph,
    repository_index: Optional[dict] = None,
):
    """Return exported symbols with no incoming references.

    Mapping file_path -> list of unused exports.
    """
    return reasoning.find_unused_exports(relationships, repository_index)


def find_cycles(relationships: RelationshipGraph):
    """Find dependency cycles between files (imports)."""
    return reasoning.find_cycles(relationships)


def dependency_tree(
    relationships: RelationshipGraph,
    start: str,
    max_depth: int = 50,
):
    """Return forward dependency chain (imports) from start."""
    return reasoning.dependency_tree_forward(relationships, start, max_depth=max_depth)


def reverse_dependency_tree(
    relationships: RelationshipGraph,
    start: str,
    max_depth: int = 50,
):
    """Return reverse dependency chain (who depends on start)."""
    return reasoning.dependency_tree_reverse(relationships, start, max_depth=max_depth)


def impact_analysis(
    relationships: RelationshipGraph,
    node: str,
    max_depth: int = 50,
):
    """Return nodes that may be affected if `node` changes."""
    return reasoning.impact_analysis(relationships, node, max_depth=max_depth)


def find_architecture_violations(
    relationships: RelationshipGraph,
    rules: dict,
):
    """Detect architecture rule violations using provided rules mapping."""
    return reasoning.detect_architecture_violations(relationships, rules)


def find_feature_owner(
    relationships: RelationshipGraph,
    min_cluster_size: int = 1,
):
    """Estimate feature ownership clusters; returns mapping feature_id -> files."""
    return reasoning.feature_ownership(relationships, min_cluster_size=min_cluster_size)


def find_duplicate_utilities(
    relationships: RelationshipGraph,
    threshold: float = 0.8,
):
    """Return pairs of utilities with similar dependency neighborhoods."""
    return reasoning.find_duplicate_utilities(relationships, threshold=threshold)


# ---------------------------------------------------------------------------
# Repository Intelligence wrappers (public API)
# ---------------------------------------------------------------------------

from core import intelligence
from core.indexer import RepositoryIndex


def detect_project_structure(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
):
    """Wrapper for intelligence.detect_project_structure.

    Note: `index` parameter should be the RepositoryIndex instance. Kept
    positional for API symmetry with other queries.
    """
    return intelligence.detect_project_structure(index, graph, relationships)


def detect_architecture(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
):
    """Detect the repository architecture."""
    return intelligence.detect_architecture(index, graph, relationships)


def detect_frameworks(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
):
    """Detect frameworks present in the repository."""
    return intelligence.detect_frameworks(index, graph, relationships)


def detect_routes(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
):
    """Detect web routes/endpoints in the repository."""
    return intelligence.detect_routes(index, graph, relationships)


def detect_components(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
):
    """Detect UI components in the repository."""
    return intelligence.detect_components(index, graph, relationships)


def detect_entry_points(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
):
    """Detect likely entry point files."""
    return intelligence.detect_entry_points(index, graph, relationships)


def detect_configuration(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
):
    """Detect configuration files and their purposes."""
    return intelligence.detect_configuration(index, graph, relationships)


def detect_build_system(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
):
    """Detect build system/tooling used by the repository."""
    return intelligence.detect_build_system(index, graph, relationships)


def detect_package_manager(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
):
    """Detect package manager used by the repository."""
    return intelligence.detect_package_manager(index, graph, relationships)


def detect_testing_framework(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
):
    """Detect testing frameworks used by the repository."""
    return intelligence.detect_testing_framework(index, graph, relationships)


def detect_deployment(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
):
    """Detect deployment platforms and primitives."""
    return intelligence.detect_deployment(index, graph, relationships)


def summarize_repository(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
):
    """Wrapper for intelligence.summarize_repository.

    Returns a compact summary dict suitable for LLM prompts.
    """
    return intelligence.summarize_repository(index, graph, relationships)


def build_repository_profile(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
):
    """Return a full repository profile from the intelligence module.

    This is the recommended single-call entrypoint that AI agents should use
    to get repository-level context.
    """
    return intelligence.build_repository_profile(index, graph, relationships)


# ---------------------------------------------------------------------------
# Phase 3: Higher-level query engine helpers (used by AI)
# ---------------------------------------------------------------------------

def search_symbol(
    graph: DependencyGraph,
    relationships: RelationshipGraph,
    query: str,
    limit: int = 50,
) -> List[Dict]:
    """Search for symbols (functions, classes, selectors, ids, variables).

    Returns a list of dicts: {"symbol": str, "kind": str, "file": Optional[str]}
    """
    q = query.strip()
    results: List[Dict] = []
    seen = set()

    # helper to append unique results
    def add(sym: str, kind: str, file: Optional[str]):
        if not sym:
            return
        key = (sym, kind, file)
        if key in seen:
            return
        seen.add(key)
        results.append({"symbol": sym, "kind": kind, "file": file})

    # exact and substring matches in dependency graph indexes
    query_lower = q.lower()
    query_tokens = set(query_lower.split())

    def matches_symbol(name: str) -> bool:
        name_lower = name.lower()
        if query_lower in name_lower or name_lower in query_lower:
            return True
        return any(token in name_lower for token in query_tokens if len(token) >= 3)

    for name, path in graph.functions.items():
        if matches_symbol(name):
            add(name, "function", path)
    for name, path in graph.classes.items():
        if matches_symbol(name):
            add(name, "class", path)
    for name, path in graph.selectors.items():
        if matches_symbol(name):
            add(name, "selector", path)
    for name, path in graph.css_classes.items():
        if matches_symbol(name):
            add(name, "css_class", path)
    for name, path in graph.ids.items():
        if matches_symbol(name):
            add(name, "id", path)
    for name, path in graph.variables.items():
        if matches_symbol(name):
            add(name, "css_variable", path)

    # search relationship graph sources/targets for matches (symbol references)
    for rel in relationships:
        for candidate, kind in ((rel.source, "source"), (rel.target, "target")):
            if not candidate:
                continue
            if q.lower() in candidate.lower():
                # attempt to map candidate to a file
                file = _symbol_file(graph, candidate) if isinstance(graph, DependencyGraph) else None
                add(candidate, f"ref_{kind}", file)

        if len(results) >= limit:
            break

    return results[:limit]


def find_references(
    graph: DependencyGraph,
    relationships: RelationshipGraph,
    symbol: str,
) -> List[Dict]:
    """Return structured references to `symbol`.

    Each entry: {"source": str, "source_file": str, "relation": str, "line": Optional[int], "metadata": dict}
    """
    refs = []
    for rel in relationships.by_target(symbol):
        refs.append({
            "source": rel.source,
            "source_file": rel.source_file,
            "relation": rel.relation.value if hasattr(rel.relation, "value") else str(rel.relation),
            "line": rel.line,
            "metadata": rel.metadata,
        })
    return refs


def find_definitions(
    graph: DependencyGraph,
    relationships: RelationshipGraph,
    symbol: str,
) -> List[Dict]:
    """Return definitions for a symbol: file locations and possible definition metadata.

    Result entries: {"symbol": str, "file": Optional[str], "kind": str}
    """
    defs: List[Dict] = []

    # check dependency graph indexes
    if graph.functions.get(symbol):
        defs.append({"symbol": symbol, "file": graph.functions.get(symbol), "kind": "function"})
    if graph.classes.get(symbol):
        defs.append({"symbol": symbol, "file": graph.classes.get(symbol), "kind": "class"})
    if graph.selectors.get(symbol):
        defs.append({"symbol": symbol, "file": graph.selectors.get(symbol), "kind": "selector"})
    if graph.css_classes.get(symbol):
        defs.append({"symbol": symbol, "file": graph.css_classes.get(symbol), "kind": "css_class"})
    if graph.ids.get(symbol):
        defs.append({"symbol": symbol, "file": graph.ids.get(symbol), "kind": "id"})
    if graph.variables.get(symbol):
        defs.append({"symbol": symbol, "file": graph.variables.get(symbol), "kind": "css_variable"})

    # fall back to relationship-based inference: if any relationship has source == symbol and source_file available
    for rel in relationships.by_source(symbol):
        if rel.source_file:
            defs.append({"symbol": symbol, "file": rel.source_file, "kind": "inferred"})

    # ensure uniqueness
    seen = set()
    unique_defs = []
    for d in defs:
        key = (d.get("symbol"), d.get("file"), d.get("kind"))
        if key in seen:
            continue
        seen.add(key)
        unique_defs.append(d)

    return unique_defs


def find_component(
    graph: DependencyGraph,
    relationships: RelationshipGraph,
    symbol_or_file: str,
) -> Dict:
    """Return the feature/component cluster that contains the symbol or file.

    Uses reasoning.feature_ownership under the hood.
    Returns {"feature_id": str, "members": [files...] } or {} if none found.
    """
    clusters = reasoning.feature_ownership(relationships)
    # build reverse mapping
    owner_map = {}
    for fid, members in clusters.items():
        for m in members:
            owner_map[m] = fid
    # try to resolve symbol_or_file to a file first
    owner_file = None
    if any(sep in symbol_or_file for sep in ("/", "\\")) or symbol_or_file.endswith(('.js', '.py', '.html', '.css')):
        owner_file = symbol_or_file
    else:
        # try dependency graph symbol maps
        owner_file = (
            graph.functions.get(symbol_or_file)
            or graph.classes.get(symbol_or_file)
            or graph.selectors.get(symbol_or_file)
            or graph.css_classes.get(symbol_or_file)
            or graph.ids.get(symbol_or_file)
            or graph.variables.get(symbol_or_file)
        )

    if not owner_file:
        # try relationships: find a source/target that maps to a file
        for rel in relationships.by_target(symbol_or_file) + relationships.by_source(symbol_or_file):
            candidate = _symbol_file(graph, rel.source) or _symbol_file(graph, rel.target)
            if candidate:
                owner_file = candidate
                break

    if not owner_file:
        return {}

    feature_id = owner_map.get(owner_file)
    if not feature_id:
        return {}

    return {"feature_id": feature_id, "members": clusters.get(feature_id, [])}


def find_owner(
    graph: DependencyGraph,
    relationships: RelationshipGraph,
    symbol: str,
) -> List[str]:
    """Return files that are owners/definitions of the given symbol.

    Returns a list of file paths.
    """
    owners = []
    # dependency graph maps are authoritative
    if graph.functions.get(symbol):
        owners.append(graph.functions.get(symbol))
    if graph.classes.get(symbol):
        owners.append(graph.classes.get(symbol))
    if graph.selectors.get(symbol):
        owners.append(graph.selectors.get(symbol))
    if graph.css_classes.get(symbol):
        owners.append(graph.css_classes.get(symbol))
    if graph.ids.get(symbol):
        owners.append(graph.ids.get(symbol))
    if graph.variables.get(symbol):
        owners.append(graph.variables.get(symbol))

    # fall back to relationship-based inference
    if not owners:
        for rel in relationships.by_source(symbol) + relationships.by_target(symbol):
            file_candidate = rel.source_file
            if file_candidate and file_candidate not in owners:
                owners.append(file_candidate)

    return owners
