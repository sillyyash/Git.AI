"""
QUICK START GUIDE - AI Planner Agent
====================================

This guide will get you up and running with the AI Planner Agent in 5 minutes.
"""

# Installation & Setup
# ====================

# 1. The Planner is already built and tested. All files are in place:
#    - agents/planner.py (main entry point)
#    - agents/planner_models.py (data models)
#    - agents/planner_rules.py (intent classification)
#    - agents/planner_prompts.py (LLM prompts)
#    - agents/planner_executor.py (planning pipeline)
#    - tests/test_planner.py (25 comprehensive tests)

# 2. Run tests to verify:
#    python -m unittest tests.test_planner -v
#    (Expected: 25 tests passing)


# BASIC USAGE
# ===========

from agents.planner import create_planner

# Create a planner instance
planner = create_planner(debug=False)

# Create a plan for a code modification request
plan = planner.plan(
    request="rename the login function to authenticate",
    repository_index=index,  # From core.repository
    dependency_graph=dep_graph,  # From core.graph
    relationship_graph=rel_graph,  # From core.relationship
)

# Access plan data
print(f"Intent: {plan.intent.value}")  # e.g., "rename"
print(f"Risk: {plan.risk.value}")  # e.g., "low"
print(f"Complexity: {plan.complexity.value}")  # e.g., "small"
print(f"Summary: {plan.summary}")

# View execution steps
for step in plan.execution_steps:
    print(f"Step {step.order}: {step.action} (Agent: {step.agent})")
    if step.depends_on:
        print(f"  Depends on: {step.depends_on}")


# COMMON OPERATIONS
# =================

# 1. RENAME
plan = planner.plan(
    "rename calculateTotal to computeSum",
    index, dep_graph, rel_graph
)
# Creates plan to rename function and update all references

# 2. FEATURE
plan = planner.plan(
    "add dark mode support to the UI",
    index, dep_graph, rel_graph
)
# Creates plan to scaffold new feature with proper integration

# 3. BUG FIX
plan = planner.plan(
    "fix the login crash on invalid email",
    index, dep_graph, rel_graph
)
# Creates plan to locate bug and apply fix

# 4. REFACTOR
plan = planner.plan(
    "refactor auth module to use dependency injection",
    index, dep_graph, rel_graph
)
# Creates plan for structural refactoring

# 5. TEST
plan = planner.plan(
    "add unit tests for payment module",
    index, dep_graph, rel_graph
)
# Creates plan to add test coverage

# 6. OPTIMIZE
plan = planner.plan(
    "optimize database queries for better performance",
    index, dep_graph, rel_graph
)
# Creates plan to improve performance


# EXPORT & SERIALIZE
# ==================

# Convert plan to dictionary
plan_dict = planner.plan_to_dict(plan)

# Convert plan to JSON
plan_json = planner.plan_to_json(plan)
# Use for storage, transmission, or logging


# ACCESSING PLAN COMPONENTS
# ==========================

# Request and summary
print(plan.request)  # Original user request
print(plan.summary)  # High-level summary

# Intent and confidence
print(plan.intent.value)  # Intent classification

# Risk and complexity
print(plan.risk.value)  # LOW, MEDIUM, HIGH
print(plan.complexity.value)  # TRIVIAL, SMALL, MEDIUM, LARGE

# Affected code
print(plan.affected_files)  # List of affected files
print(plan.affected_symbols)  # List of affected symbols
print(plan.dependencies)  # Dict of file -> dependencies

# Execution steps
for step in plan.execution_steps:
    print(f"  {step.order}. {step.action}")
    print(f"     Agent: {step.agent}")
    print(f"     Description: {step.description}")
    if step.depends_on:
        print(f"     Depends on: {step.depends_on}")

# Validation steps
for validation in plan.validation_steps:
    print(f"  Validate: {validation}")


# UNDERSTANDING INTENTS
# =====================

# The Planner classifies requests into these intents:

# RENAME - Change identifier names
# "rename foo to bar", "refactor name", "call it something else"

# REFACTOR - Restructure code
# "refactor module", "clean up", "reorganize", "extract", "simplify"

# FEATURE - Add new functionality
# "add feature", "implement", "add support", "new endpoint"

# BUG - Fix broken behavior
# "fix bug", "broken", "crash", "not working", "error"

# EXPLAIN - Clarify code meaning
# "explain", "help understand", "how does", "why", "describe"

# REVIEW - Analyze code quality
# "review", "code review", "check", "examine", "lint"

# OPTIMIZE - Improve performance
# "optimize", "performance", "speed up", "efficiency"

# DELETE - Remove unused code
# "delete", "remove", "dead code", "clean up"

# GENERATE - Create boilerplate
# "generate", "scaffold", "template", "boilerplate"

# TEST - Add test coverage
# "test", "write test", "add test", "unit test"

# DOCS - Add documentation
# "document", "add docs", "docstring", "comment"


# UNDERSTANDING RISK & COMPLEXITY
# ================================

# RISK LEVELS:
# LOW - Isolated changes, well-tested, clear scope
# MEDIUM - Multiple modules, moderate dependencies
# HIGH - Critical paths, circular deps, poor coverage

# COMPLEXITY LEVELS:
# TRIVIAL - Single file, no deps, < 5 minutes
# SMALL - Single module, local changes, < 30 minutes
# MEDIUM - Multiple files, moderate testing, 1-4 hours
# LARGE - Cross-module, extensive testing, > 4 hours


# DEBUGGING
# =========

# Create planner with debug enabled
planner = create_planner(debug=True)

# This will print debug information during planning
plan = planner.plan(request, index, dep_graph, rel_graph)


# INTEGRATION WITH DOWNSTREAM AGENTS
# ===================================

# The Plan object is designed for downstream agents:

# Step 1: Coder Agent
# - Consumes plan.execution_steps
# - Executes steps marked for "coder" agent
# - Generates actual code changes

# Step 2: Tester Agent
# - Runs tests from plan.validation_steps
# - Verifies all tests pass

# Step 3: Reviewer Agent
# - Reviews generated code
# - Checks against plan.reasoning

# Step 4: Committer Agent
# - Creates git commit
# - Pushes changes


# BEST PRACTICES
# ==============

# 1. Always check plan.risk before execution
if plan.risk.value == "HIGH":
    print("This is a high-risk change - review carefully")

# 2. Validate plan structure before passing to downstream agents
if len(plan.execution_steps) == 0:
    print("Warning: No execution steps generated")

# 3. Use plan.reasoning to understand the analysis
print(f"Analysis: {plan.reasoning}")

# 4. Check for warnings
if plan.warnings:
    for warning in plan.warnings:
        print(f"Warning: {warning}")

# 5. Consider alternative approaches
print(f"Alternatives: {plan.alternative_approaches}")


# ADVANCED USAGE
# ==============

# One-off planning without creating an agent
from agents.planner import plan_code_operation

plan = plan_code_operation(
    "add two-factor authentication",
    index, dep_graph, rel_graph,
    debug=True,
)

# Get plan as different formats
plan_dict = planner.plan_to_dict(plan)
plan_json = planner.plan_to_json(plan)

# Inspect execution step structure
step = plan.execution_steps[0]
print(f"Step ID: {step.id}")
print(f"Agent: {step.agent}")
print(f"Action: {step.action}")
print(f"Description: {step.description}")
print(f"Context: {step.context}")
print(f"Validation: {step.validation}")


# COMMON ISSUES & SOLUTIONS
# =========================

# Issue: "No symbols found"
# Solution: The planner searches for symbols in the request. Ensure
#           you use actual symbol names from the codebase.

# Issue: "Plan has no steps"
# Solution: Ensure repository graphs are properly populated.
#           Check that index, dep_graph, rel_graph are valid.

# Issue: "High risk assessment"
# Solution: This is expected for wide-scope changes. Review the
#           reasoning to understand the risk factors.

# Issue: "Intent classified as UNKNOWN"
# Solution: Use clearer language in the request. Include specific
#           keywords like "rename", "refactor", "add", "fix", etc.


# NEXT STEPS
# ==========

# 1. Review PLANNER_README.md for detailed architecture
# 2. Check planner_demo.py for example usage
# 3. Run tests: python -m unittest tests.test_planner -v
# 4. Implement Coder Agent to consume Plan objects
# 5. Implement Tester Agent to validate plans
# 6. Implement Reviewer Agent for code review
# 7. Implement Committer Agent for git operations


# SUPPORT & DOCUMENTATION
# =========================

# - Main README: agents/PLANNER_README.md
# - Architecture: agents/PLANNER_README.md
# - Demo Script: agents/planner_demo.py
# - Implementation Summary: PLANNER_IMPLEMENTATION_SUMMARY.md
# - Tests: tests/test_planner.py
"""
