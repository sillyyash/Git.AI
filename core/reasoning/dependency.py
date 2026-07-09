"""Dependency analysis: cycles and dependency trees.

Functions:
- find_cycles(graph) -> list of cycles (each cycle is list of nodes in order)
- dependency_tree_forward(graph, start, max_depth=50) -> dict of node -> distance
- dependency_tree_reverse(graph, start, max_depth=50) -> dict of node -> distance

These functions operate primarily on IMPORTS relations but accept any graph.
"""
from typing import List, Dict, Set, Tuple
from collections import defaultdict, deque

from core.relationship import RelationshipGraph, Relation


def _build_import_adj(graph: RelationshipGraph) -> Dict[str, List[str]]:
    adj = defaultdict(list)
    for rel in graph.by_relation(Relation.IMPORTS):
        src = rel.source_file
        tgt = rel.target
        if src and tgt:
            adj[src].append(tgt)
    return adj


def find_cycles(graph: RelationshipGraph) -> List[List[str]]:
    """Find cycles in the module import graph using DFS and return list of cycles.

    Each cycle is returned as a list of file paths in cycle order.
    """
    adj = _build_import_adj(graph)
    temp_mark = set()
    perm_mark = set()
    stack: List[str] = []
    cycles: List[List[str]] = []

    def visit(node: str):
        if node in perm_mark:
            return
        if node in temp_mark:
            # found a cycle; capture from node's first occurrence in stack
            if node in stack:
                idx = stack.index(node)
                cycles.append(stack[idx:] + [node])
            return
        temp_mark.add(node)
        stack.append(node)
        for n in adj.get(node, []):
            visit(n)
        stack.pop()
        temp_mark.remove(node)
        perm_mark.add(node)

    for node in list(adj.keys()):
        if node not in perm_mark:
            visit(node)

    # Deduplicate cycles (normalize rotation)
    normalized = set()
    unique_cycles: List[List[str]] = []
    for c in cycles:
        # create rotation-invariant representation
        if not c:
            continue
        seq = c[:-1] if c[0] == c[-1] else c
        minrot = min([tuple(seq[i:] + seq[:i]) for i in range(len(seq))])
        if minrot not in normalized:
            normalized.add(minrot)
            unique_cycles.append(list(minrot))
    return unique_cycles


def dependency_tree_forward(graph: RelationshipGraph, start: str, max_depth: int = 50) -> Dict[str, int]:
    """Return forward dependency distances from `start` following IMPORTS edges.

    Returns mapping node -> distance (0 = start)
    """
    adj = _build_import_adj(graph)
    distances: Dict[str, int] = {}
    dq = deque([(start, 0)])
    while dq:
        node, d = dq.popleft()
        if node in distances and distances[node] <= d:
            continue
        distances[node] = d
        if d >= max_depth:
            continue
        for child in adj.get(node, []):
            dq.append((child, d + 1))
    return distances


def dependency_tree_reverse(graph: RelationshipGraph, start: str, max_depth: int = 50) -> Dict[str, int]:
    """Return reverse dependency distances to `start` following IMPORTS edges in reverse.

    Returns mapping node -> distance (0 = start)
    """
    adj = _build_import_adj(graph)
    # build reverse adjacency
    rev = defaultdict(list)
    for src, targets in adj.items():
        for t in targets:
            rev[t].append(src)

    distances: Dict[str, int] = {}
    dq = deque([(start, 0)])
    while dq:
        node, d = dq.popleft()
        if node in distances and distances[node] <= d:
            continue
        distances[node] = d
        if d >= max_depth:
            continue
        for parent in rev.get(node, []):
            dq.append((parent, d + 1))
    return distances
