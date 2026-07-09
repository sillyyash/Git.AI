"""Duplicate utility detection.

Heuristic: functions with very similar dependency neighborhoods (incoming and outgoing)
are likely duplicates. Compute neighborhood sets and measure Jaccard similarity.

API:
- find_duplicate_utilities(graph, threshold=0.8) -> list of tuples (func_a, func_b, similarity)
"""
from typing import List, Tuple, Dict, Set
from collections import defaultdict

from core.relationship import RelationshipGraph, Relation




def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 1.0
    inter = len(a & b)
    uni = len(a | b)
    if uni == 0:
        return 0.0
    return inter / uni


def find_duplicate_utilities(graph: RelationshipGraph, threshold: float = 0.8) -> List[Tuple[str, str, float]]:
    """Return pairs of functions with neighborhood similarity >= threshold.

    The function names are drawn from relationship sources that appear in CALLS/CALLS_* relations.
    """
    neighborhoods = defaultdict(set)
    # collect from CALLS, CALLS_FUNCTION, CALLS_METHOD and REFERENCES
    for rel in graph.by_relation(Relation.CALLS) + graph.by_relation(Relation.CALLS_FUNCTION) + graph.by_relation(Relation.CALLS_METHOD):
        if rel.source and rel.target:
            neighborhoods[rel.source].add("calls:" + rel.target)
            neighborhoods[rel.target].add("called_by:" + rel.source)
    for rel in graph.by_relation(Relation.REFERENCES):
        if rel.source and rel.target:
            neighborhoods[rel.source].add("refers:" + rel.target)
            neighborhoods[rel.target].add("referred_by:" + rel.source)

    funcs = list(neighborhoods.keys())
    duplicates = []
    for i in range(len(funcs)):
        for j in range(i + 1, len(funcs)):
            a = funcs[i]
            b = funcs[j]
            sim = _jaccard(neighborhoods[a], neighborhoods[b])
            if sim >= threshold:
                duplicates.append((a, b, sim))
    return duplicates
