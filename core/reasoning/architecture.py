"""Architecture rule checks.

Provides rule-based checks for:
 - forbidden dependencies between layers
 - circular layer dependencies
 - unexpected cross-feature imports (by filename pattern)

Rules example expected by detect_architecture_violations:
{
  "layers": {
    "ui": ["/ui/", "components/"],
    "services": ["/services/"],
    "data": ["/data/"]
  },
  "forbidden": [ ["ui", "data"] ]  # ui -> data imports are forbidden
}

The implementation is intentionally conservative: filename pattern matching is substring-based
for simplicity; callers can implement more advanced matching if needed.
"""
from typing import Dict, List, Tuple, Set
from collections import defaultdict

from core.relationship import RelationshipGraph, Relation


def _assign_layers(files: List[str], layer_map: Dict[str, List[str]]) -> Dict[str, str]:
    """Assign a layer name to each file based on substring matching of patterns.

    Returns mapping file -> layer_name or None if no match.
    """
    file_layer = {}
    for f in files:
        assigned = None
        for layer, patterns in layer_map.items():
            for p in patterns:
                if p and p in f:
                    assigned = layer
                    break
            if assigned:
                break
        if assigned:
            file_layer[f] = assigned
    return file_layer


def detect_architecture_violations(graph: RelationshipGraph, rules: Dict) -> Dict:
    """Detect architecture violations according to provided rules.

    Returns a dict with keys:
      - forbidden_violations: list of tuples (from_file, to_file, from_layer, to_layer)
      - circular_layers: list of layer-cycles (list of layer names)
    """
    layers = rules.get("layers", {})
    forbidden = rules.get("forbidden", [])

    # gather all files
    files = set()
    for rel in graph.relationships:
        if rel.source_file:
            files.add(rel.source_file)
        if rel.source and any(sep in rel.source for sep in ("/","\\")):
            files.add(rel.source)
        if rel.target and any(sep in rel.target for sep in ("/","\\")):
            files.add(rel.target)

    file_layer = _assign_layers(list(files), layers)

    # Build import edges and map to layers
    violations = []
    for rel in graph.by_relation(Relation.IMPORTS):
        src = rel.source_file
        tgt = rel.target
        if not src or not tgt:
            continue
        src_layer = file_layer.get(src)
        tgt_layer = file_layer.get(tgt)
        if not src_layer or not tgt_layer:
            continue
        for forb in forbidden:
            if len(forb) >= 2 and forb[0] == src_layer and forb[1] == tgt_layer:
                violations.append((src, tgt, src_layer, tgt_layer))

    # Detect circular layers: build layer graph and find cycles
    layer_adj = defaultdict(set)
    for rel in graph.by_relation(Relation.IMPORTS):
        src = rel.source_file
        tgt = rel.target
        if not src or not tgt:
            continue
        src_layer = file_layer.get(src)
        tgt_layer = file_layer.get(tgt)
        if src_layer and tgt_layer and src_layer != tgt_layer:
            layer_adj[src_layer].add(tgt_layer)

    # find cycles in layer_adj via DFS
    visited = set()
    stack = []
    temp = set()
    cycles = []

    def visit(layer):
        if layer in temp:
            if layer in stack:
                idx = stack.index(layer)
                cycles.append(stack[idx:] + [layer])
            return
        if layer in visited:
            return
        temp.add(layer)
        stack.append(layer)
        for nb in layer_adj.get(layer, []):
            visit(nb)
        stack.pop()
        temp.remove(layer)
        visited.add(layer)

    for l in layer_adj.keys():
        if l not in visited:
            visit(l)

    # normalize layer cycles (remove duplicate rotations)
    unique = []
    seen = set()
    for c in cycles:
        seq = c[:-1] if c and c[0] == c[-1] else c
        if not seq:
            continue
        minrot = min([tuple(seq[i:] + seq[:i]) for i in range(len(seq))])
        if minrot not in seen:
            seen.add(minrot)
            unique.append(list(minrot))

    return {
        "forbidden_violations": violations,
        "circular_layers": unique,
    }
