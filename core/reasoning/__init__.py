"""Repository Reasoning package

Expose independent reasoning algorithms that operate on the RelationshipGraph
and (optionally) the repository index and dependency graph.

APIs are intentionally small and focused so they can be composed by queries.py
or ai.py later.
"""

from .dead_code import find_dead_code, find_unused_imports, find_unused_exports
from .dependency import find_cycles, dependency_tree_forward, dependency_tree_reverse
from .impact import impact_analysis
from .architecture import detect_architecture_violations
from .ownership import feature_ownership
from .duplicate import find_duplicate_utilities

__all__ = [
    "find_dead_code",
    "find_unused_imports",
    "find_unused_exports",
    "find_cycles",
    "dependency_tree_forward",
    "dependency_tree_reverse",
    "impact_analysis",
    "detect_architecture_violations",
    "feature_ownership",
    "find_duplicate_utilities",
]
