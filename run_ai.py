import sys
import json

from core.repository import scan_repository
from core.indexer import build_index
from core.graph import build_graph
from core.relationship import RelationshipBuilder
from agents.planner import create_planner
from agents.coder import create_coder


def run_ai_pipeline(root_dir=None):
    repo_path = root_dir or "repos/website"

    # Repository Scan
    repo = scan_repository(repo_path)

    # Repository Index
    index = build_index(repo)

    # Dependency Graph
    graph = build_graph(index)

    # Relationship Graph
    relationship_graph = RelationshipBuilder(index).build()

    # Ask for Prompt
    prompt = input("Enter your AI development prompt: ")

    # Planner
    planner = create_planner()
    plan = planner.plan(prompt, index, graph, relationship_graph)
    print(planner.plan_to_json(plan))

    # Coder
    coder = create_coder()
    result = coder.execute(plan, repo, index, graph, relationship_graph)

    # Print Change Objects
    for change in result.changes:
        print(change.to_dict())


if __name__ == "__main__":
    root_dir = sys.argv[1] if len(sys.argv) > 1 else None
    run_ai_pipeline(root_dir)