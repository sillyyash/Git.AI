"""Demo and Usage Examples for the AI Planner Agent.

This script demonstrates how to use the Planner Agent to create execution plans
for various code modification requests.
"""

import json
from unittest.mock import Mock

from agents.planner import create_planner, plan_code_operation
from agents.planner_models import Intent, Risk, Complexity


def create_mock_graphs():
    """Create realistic mock graphs for demonstration."""
    mock_index = Mock()
    mock_index.files = []
    
    mock_dep_graph = Mock()
    mock_dep_graph.imports = {
        "app.py": ["auth.py", "utils.py", "database.py"],
        "auth.py": ["utils.py", "database.py"],
        "utils.py": ["database.py"],
        "database.py": [],
    }
    mock_dep_graph.reverse_imports = {
        "database.py": ["app.py", "auth.py", "utils.py"],
        "utils.py": ["app.py", "auth.py"],
        "auth.py": ["app.py"],
    }
    mock_dep_graph.functions = {
        "login": "auth.py",
        "validateEmail": "auth.py",
        "calculateTotal": "utils.py",
        "getUser": "database.py",
    }
    mock_dep_graph.classes = {
        "User": "database.py",
        "AuthManager": "auth.py",
    }
    mock_dep_graph.selectors = {}
    mock_dep_graph.css_classes = {}
    mock_dep_graph.ids = {}
    mock_dep_graph.variables = {}
    
    mock_rel_graph = Mock()
    mock_rel_graph.by_target = Mock(return_value=[])
    mock_rel_graph.by_source = Mock(return_value=[])
    mock_rel_graph.by_file = Mock(return_value=[])
    mock_rel_graph.by_relation = Mock(return_value=[])
    
    return mock_index, mock_dep_graph, mock_rel_graph


def print_plan(plan, title="Execution Plan"):
    """Pretty-print a plan."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)
    
    print(f"\n[REQUEST]")
    print(f"   {plan.request}")
    
    print(f"\n[INTENT]: {plan.intent.value.upper()}")
    print(f"   Confidence: {plan.execution_steps[0].context.get('intent', 'N/A')}")
    
    print(f"\n[RISK LEVEL]: {plan.risk.value.upper()}")
    print(f"   Complexity: {plan.complexity.value.upper()}")
    
    print(f"\n[SCOPE]:")
    print(f"   - Affected Files: {len(plan.affected_files)}")
    print(f"   - Affected Symbols: {len(plan.affected_symbols)}")
    print(f"   - Dependencies: {sum(len(d) for d in plan.dependencies.values())}")
    
    print(f"\n[SUMMARY]:")
    print(f"   {plan.summary}")
    
    print(f"\n[REASONING]:")
    for line in plan.reasoning.split('\n'):
        if line.strip():
            print(f"   {line}")
    
    print(f"\n[EXECUTION STEPS] ({len(plan.execution_steps)} steps):")
    for i, step in enumerate(plan.execution_steps, 1):
        print(f"\n   Step {step.order}: {step.action}")
        print(f"   >> Agent: {step.agent}")
        print(f"   >> Description: {step.description}")
        if step.depends_on:
            print(f"   >> Depends on: {', '.join(step.depends_on)}")
        if step.affected_files:
            print(f"   >> Files: {', '.join(step.affected_files[:3])}" +
                  (f" +{len(step.affected_files)-3} more" if len(step.affected_files) > 3 else ""))
    
    print(f"\n[VALIDATION STEPS] ({len(plan.validation_steps)}):")
    for step in plan.validation_steps[:3]:
        print(f"   * {step}")
    if len(plan.validation_steps) > 3:
        print(f"   ... and {len(plan.validation_steps)-3} more")
    
    if plan.warnings:
        print(f"\n[WARNINGS] ({len(plan.warnings)}):")
        for warning in plan.warnings:
            print(f"   ! {warning}")
    
    print("\n" + "=" * 80 + "\n")


def demo_rename_operation():
    """Demo: Rename a function."""
    print("\n" + "=== " * 10)
    print("DEMO 1: Rename Operation")
    print("=== " * 10)
    
    planner = create_planner(debug=False)
    index, dep_graph, rel_graph = create_mock_graphs()
    
    request = "rename the login function to authenticate and update all references"
    plan = planner.plan(request, index, dep_graph, rel_graph)
    
    print_plan(plan, "Rename Operation Plan")
    
    return plan


def demo_feature_addition():
    """Demo: Add a new feature."""
    print("\n" + "=== " * 10)
    print("DEMO 2: Feature Addition")
    print("=== " * 10)
    
    planner = create_planner(debug=False)
    index, dep_graph, rel_graph = create_mock_graphs()
    
    request = "add two-factor authentication support to the auth module"
    plan = planner.plan(request, index, dep_graph, rel_graph)
    
    print_plan(plan, "Feature Addition Plan")
    
    return plan


def demo_bug_fix():
    """Demo: Fix a bug."""
    print("\n" + "=== " * 10)
    print("DEMO 3: Bug Fix")
    print("=== " * 10)
    
    planner = create_planner(debug=False)
    index, dep_graph, rel_graph = create_mock_graphs()
    
    request = "fix the email validation bug that crashes on invalid input"
    plan = planner.plan(request, index, dep_graph, rel_graph)
    
    print_plan(plan, "Bug Fix Plan")
    
    return plan


def demo_refactoring():
    """Demo: Refactor code."""
    print("\n" + "=== " * 10)
    print("DEMO 4: Refactoring")
    print("=== " * 10)
    
    planner = create_planner(debug=False)
    index, dep_graph, rel_graph = create_mock_graphs()
    
    request = "refactor the authentication module to use dependency injection"
    plan = planner.plan(request, index, dep_graph, rel_graph)
    
    print_plan(plan, "Refactoring Plan")
    
    return plan


def demo_test_addition():
    """Demo: Add tests."""
    print("\n" + "=== " * 10)
    print("DEMO 5: Add Tests")
    print("=== " * 10)
    
    planner = create_planner(debug=False)
    index, dep_graph, rel_graph = create_mock_graphs()
    
    request = "write comprehensive unit tests for the authentication module"
    plan = planner.plan(request, index, dep_graph, rel_graph)
    
    print_plan(plan, "Add Tests Plan")
    
    return plan


def demo_json_export(plan):
    """Demo: Export plan to JSON."""
    print("\n" + "=== " * 10)
    print("DEMO: JSON Export")
    print("=== " * 10)
    
    planner = create_planner()
    plan_dict = planner.plan_to_dict(plan)
    plan_json = planner.plan_to_json(plan)
    
    print("\n[PLAN AS JSON] (truncated):")
    print(plan_json[:500] + "...\n")
    
    # Show structure
    print("[PLAN STRUCTURE]:")
    for key in plan_dict.keys():
        if isinstance(plan_dict[key], list):
            print(f"   - {key}: {len(plan_dict[key])} items")
        else:
            print(f"   - {key}: {type(plan_dict[key]).__name__}")


def demo_comparison():
    """Demo: Compare different operations."""
    print("\n" + "=== " * 10)
    print("COMPARISON: Different Operations")
    print("=== " * 10)
    
    planner = create_planner()
    index, dep_graph, rel_graph = create_mock_graphs()
    
    operations = [
        ("Rename operation", "rename login to authenticate"),
        ("Bug fix", "fix email validation crash"),
        ("Feature addition", "add 2FA support"),
        ("Refactoring", "refactor to use DI pattern"),
        ("Add tests", "add unit tests for auth"),
    ]
    
    print("\n" + "-" * 80)
    print(f"{'Operation':<25} {'Intent':<12} {'Risk':<8} {'Complexity':<10} {'Steps':<6}")
    print("-" * 80)
    
    for title, request in operations:
        plan = planner.plan(request, index, dep_graph, rel_graph)
        print(
            f"{title:<25} "
            f"{plan.intent.value:<12} "
            f"{plan.risk.value:<8} "
            f"{plan.complexity.value:<10} "
            f"{len(plan.execution_steps):<6}"
        )
    
    print("-" * 80 + "\n")


def main():
    """Run all demos."""
    print("\n" * 2)
    print("=" * 80)
    print("  AI Planner Agent - Comprehensive Demo & Usage Examples")
    print("=" * 80)
    
    print("\n[INFO] This demo shows the Planner Agent creating structured execution plans")
    print("   for different types of code modification requests.\n")
    
    # Run demos
    plan1 = demo_rename_operation()
    plan2 = demo_feature_addition()
    plan3 = demo_bug_fix()
    plan4 = demo_refactoring()
    plan5 = demo_test_addition()
    
    # Export demo
    demo_json_export(plan1)
    
    # Comparison
    demo_comparison()
    
    # Summary
    print("\n" + "=" * 80)
    print("  DEMO SUMMARY")
    print("=" * 80)
    print("""
[KEY FEATURES DEMONSTRATED]

1. [OK] Intent Classification
   - Automatically detects operation type (rename, feature, bug, etc.)
   
2. [OK] Risk Assessment
   - Evaluates potential side effects and impact
   
3. [OK] Complexity Estimation
   - Estimates effort required for implementation
   
4. [OK] Dependency Analysis
   - Identifies affected files and symbols
   
5. [OK] Execution Plan Generation
   - Creates ordered, executable steps with dependencies
   
6. [OK] Structured Output
   - Plans are JSON-serializable and self-documenting

[PLANNER PRINCIPLES]

The Planner Agent uses ONLY the public core.queries.* API and never:
   - Modifies code or files
   - Accesses graphs directly
   - Calls LLM/Ollama directly
   - Generates code (only plans)

[NEXT STEPS]

   - Coder Agent consumes plans and generates code
   - Tester Agent runs tests
   - Reviewer Agent performs code review
   - Committer Agent commits changes
""")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
