"""Feature ownership heuristics.

Clusters files into features/components based on graph connectivity using
simple union-find over relations that commonly indicate ownership boundaries.

API:
- feature_ownership(graph, min_cluster_size=1) -> dict mapping cluster_id -> list[file_paths]
"""
from typing import Dict, List
from collections import defaultdict

from core.relationship import RelationshipGraph, Relation


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        if self.parent.get(x, x) != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent.get(x, x)

    def union(self, a, b):
        ra = self.find(a)
        rb = self.find(b)
        if ra == rb:
            return
        self.parent[rb] = ra


def feature_ownership(graph: RelationshipGraph, min_cluster_size: int = 1) -> Dict[str, List[str]]:
    """Return clusters of files that likely belong to the same feature.

    Uses undirected connectivity over relations: IMPORTS, REFERENCES, STYLES, USES_CLASS.
    """
    uf = UnionFind()
    files = set()

    def union_pair(a, b):
        if not a or not b:
            return
        files.add(a)
        files.add(b)
        uf.union(a, b)

    for rel in graph.relationships:
        if rel.relation in {Relation.IMPORTS, Relation.REFERENCES, Relation.STYLES, Relation.USES_CLASS, Relation.USES_ID, Relation.FORM_CONTAINS}:
            a = rel.source_file or rel.source
            b = rel.target or rel.target
            if a and b:
                union_pair(a, b)

    # produce clusters
    clusters = defaultdict(list)
    for f in files:
        root = uf.find(f)
        clusters[root].append(f)

    # filter by min_cluster_size and produce stable ids
    result = {}
    idx = 1
    for root, members in clusters.items():
        if len(members) >= min_cluster_size:
            cid = f"feature_{idx}"
            result[cid] = sorted(members)
            idx += 1
    return result
