"""Impact analysis: given a node, compute nodes that may be affected by a change.

Algorithm:
- Start from the changed node (file, function, class, symbol)
- Walk reverse edges that represent "uses" (IMPORTS, REFERENCES, CALLS, CALLS_*),
  accumulating nodes that depend on the changed node.
- Also traverse transitive dependents to produce a full impact set.

Returns: dict with keys:
  - impacted_files: set of file paths
  - impacted_symbols: set of symbol identifiers (functions/classes)
"""
from typing import Dict, Set, List
from collections import deque, defaultdict

from core.relationship import RelationshipGraph, Relation


# relations that imply "use" (if A -> REL -> B, A uses B). For impact of B changing,
# we need to find nodes that point to B (reverse traversal)
_IMPACT_RELATIONS = {
    Relation.IMPORTS,
    Relation.REFERENCES,
    Relation.CALLS,
    Relation.CALLS_FUNCTION,
    Relation.CALLS_METHOD,
    Relation.STYLES,
    Relation.USES_CLASS,
    Relation.USES_ID,
    Relation.FORM_CONTAINS,
    Relation.USES_ASSET,
    Relation.USES_VARIABLE,
}


def impact_analysis(graph: RelationshipGraph, node: str, max_depth: int = 50) -> Dict[str, List[str]]:
    """Return the nodes (files and symbols) that may be affected when `node` changes.

    node can be a file path or a symbol/function/class identifier used in the graph.

    Returns a structure:
      {
        "impacted_files": [file_path, ...],
        "impacted_symbols": [symbol, ...],
        "paths": {node: [[via_node, ...], ...]}  # sample paths from impacted node back to changed node
      }
    """
    # Build reverse adjacency for selected relations
    rev = defaultdict(list)
    for rel in graph.relationships:
        if rel.relation in _IMPACT_RELATIONS and rel.target:
            # rel: source --REL--> target  means source uses target
            rev[rel.target].append((rel.source, rel.relation))

    impacted_symbols: Set[str] = set()
    impacted_files: Set[str] = set()

    # BFS on reverse graph from node
    dq = deque([(node, 0)])
    visited = {node}
    parent_map = defaultdict(list)  # child -> list of parents for path reconstruction

    while dq:
        cur, depth = dq.popleft()
        if depth >= max_depth:
            continue
        for src, rel in rev.get(cur, []):
            if src in visited:
                continue
            visited.add(src)
            parent_map[src].append(cur)
            dq.append((src, depth + 1))

    # classify visited nodes (exclude the original node)
    for n in visited:
        if n == node:
            continue
        # heuristics: file paths have '/' or '\\' or end with known extensions
        if any(sep in n for sep in ("/", "\\")) or n.endswith(('.js', '.ts', '.py', '.html', '.css')):
            impacted_files.add(n)
        else:
            impacted_symbols.add(n)

    # Build simple path samples for a subset of impacted nodes (first 20)
    def build_path(target):
        # reconstruct one path backwards using parent_map
        path = [target]
        cur = target
        while parent_map.get(cur):
            nxt = parent_map[cur][0]
            path.append(nxt)
            cur = nxt
            if cur == node:
                break
        return list(reversed(path))

    paths = {n: build_path(n) for i, n in enumerate(list(impacted_files) + list(impacted_symbols)) if i < 20}

    return {
        "impacted_files": sorted(list(impacted_files)),
        "impacted_symbols": sorted(list(impacted_symbols)),
        "paths": paths,
    }
