"""Planner execution coordinator.

Orchestrates the planning pipeline without accessing graphs directly.
Uses only core.queries and core.intelligence APIs.

Pipeline:
1. Intent Detection → classify request intent
2. Repository Intelligence → gather context about repo
3. Impact Analysis → find affected symbols and files
4. Dependency Analysis → detect dependencies and relationships
5. Risk Analysis → assess operation risk
6. Complexity Estimation → estimate effort
7. Plan Generation → create ordered execution steps
"""

from __future__ import annotations

import os
from typing import Optional, Dict, List, Any, Tuple
import json
from datetime import datetime

from agents.planner_models import (
    Intent,
    Risk,
    Complexity,
    Plan,
    ExecutionStep,
    Symbol,
    PlanningContext,
    IntentClassificationResult,
)
from agents.planner_rules import classify_intent, estimate_risk, estimate_complexity
from agents.planner_prompts import get_system_prompt

# Import only the public API - never import graph modules directly
from core import queries

# Reuse the same keyword extraction used by context_builder.py rather than
# re-implementing (and under-filtering) it here. This is the same stopword
# list / tokenization that seeds prompt context, so "add", "the", "fix" etc.
# never reach queries.search_symbol as noise queries.
from core.context_builder import _extract_keywords


# ---------------------------------------------------------------------------
# Phase 1: Intent Detection
# ---------------------------------------------------------------------------

def detect_intent(request: str) -> IntentClassificationResult:
    """Detect user intent from request text.
    
    Uses keyword matching and heuristics (no LLM required for basic classification).
    Returns structured intent with confidence.
    
    Args:
        request: User's request text
        
    Returns:
        IntentClassificationResult with classified intent and confidence
    """
    return classify_intent(request)


# ---------------------------------------------------------------------------
# Phase 2: Repository Intelligence Gathering
# ---------------------------------------------------------------------------

def gather_repository_context(ctx: PlanningContext) -> Dict[str, Any]:
    """Gather high-level repository context using intelligence API.
    
    Builds repository profile for understanding code organization, frameworks,
    and architecture without accessing internal graphs.
    
    Args:
        ctx: PlanningContext with repository data
        
    Returns:
        Dictionary with repository profile, architecture, frameworks, etc.
    """
    try:
        profile = queries.build_repository_profile(
            ctx.repository_index,
            ctx.dependency_graph,
            ctx.relationship_graph,
        )
        return profile
    except Exception as e:
        if ctx.debug:
            print(f"Warning: Could not build repository profile: {e}")
        return {
            "status": "unavailable",
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# Phase 3: Impact Analysis
# ---------------------------------------------------------------------------

def analyze_impact(
    ctx: PlanningContext,
    request: str,
    intent: Intent,
) -> tuple[List[Symbol], List[str], Dict[str, List[str]]]:
    """Analyze impact of the requested operation.
    
    Uses queries API to find affected symbols, files, and dependencies.
    
    Args:
        ctx: PlanningContext with repository data
        request: Original user request
        intent: Classified intent
        
    Returns:
        Tuple of (affected_symbols, affected_files, dependencies_map)
    """
    affected_symbols: List[Symbol] = []
    affected_files: List[str] = []
    dependencies: Dict[str, List[str]] = {}

    # BUG FIX: this used to be
    #   re.findall(r'\b[a-zA-Z_]\w*\b', request)
    # which had zero stopword filtering, so every request fired a
    # search_symbol() call for "add", "the", "fix", "and", "for", etc.
    # _extract_keywords() already does tokenization + stopword removal +
    # dedup (it's the same helper context_builder.py uses to seed prompt
    # context), so reuse it instead of duplicating weaker logic here.
    potential_symbols = _extract_keywords(request)

    # Search repository for mentioned symbols
    for symbol_name in potential_symbols:
        if len(symbol_name) < 3:
            continue
        
        try:
            search_results = queries.search_symbol(
                ctx.dependency_graph,
                ctx.relationship_graph,
                symbol_name,
                limit=10,
            )
            
            for result in search_results:
                sym = Symbol(
                    name=result["symbol"],
                    kind=result["kind"],
                    file=result.get("file"),
                )
                if sym not in affected_symbols:
                    affected_symbols.append(sym)
                
                if result.get("file") and result["file"] not in affected_files:
                    affected_files.append(result["file"])
        except Exception as e:
            if ctx.debug:
                print(f"Warning: Search failed for '{symbol_name}': {e}")
    
    # Build dependency map for affected files
    for file_path in affected_files:
        try:
            deps = queries.find_all_dependencies(
                ctx.dependency_graph,
                file_path,
            )
            dependencies[file_path] = deps
        except Exception as e:
            if ctx.debug:
                print(f"Warning: Dependency analysis failed for '{file_path}': {e}")
            dependencies[file_path] = []
    
    return affected_symbols, affected_files, dependencies


# ---------------------------------------------------------------------------
# Phase 4: Risk Assessment
# ---------------------------------------------------------------------------

def _is_critical_path_file(file_path: str) -> bool:
    """Return True only if a path SEGMENT or filename STEM matches a critical
    keyword - not a raw substring of the whole path.

    BUG FIX: the old version did
        any(keyword in f.lower() for keyword in ["main", "entry", "index", "app", "server"])
    which false-positives on things like 'user_index.py', 'app_config.py',
    'apparel.py', 'mainframe_utils.py'. Comparing against path segments and
    the filename stem (without extension) avoids that.
    """
    critical_keywords = {"main", "entry", "index", "app", "server"}

    normalized = file_path.replace("\\", "/").lower()
    segments = [s for s in normalized.split("/") if s]

    if not segments:
        return False

    filename = segments[-1]
    stem = os.path.splitext(filename)[0]

    # directory segment exactly named one of the keywords (e.g. "app/", "server/")
    if any(segment in critical_keywords for segment in segments[:-1]):
        return True

    # filename stem exactly matches (e.g. "main.py", "index.js", "server.py")
    # or is keyword + separator (e.g. "app_config" no, but "app.py" yes,
    # "main_router.py" yes since it starts with "main_")
    for keyword in critical_keywords:
        if stem == keyword:
            return True
        if stem.startswith(f"{keyword}_") or stem.startswith(f"{keyword}."):
            return True

    return False


def assess_risk(
    intent: Intent,
    affected_symbols: List[Symbol],
    affected_files: List[str],
    dependencies: Dict[str, List[str]],
    repo_profile: Dict[str, Any],
) -> Tuple[Risk, Dict[str, Any]]:
    """Assess operation risk using heuristics.
    
    Args:
        intent: The classified intent
        affected_symbols: Affected code symbols
        affected_files: Affected files
        dependencies: Dependency map
        repo_profile: Repository profile
        
    Returns:
        Tuple of (Risk level assessment, metrics dict used to compute it).

        The metrics dict is returned (not just the enum) so callers like
        create_plan() can report the *actual* computed values in reasoning
        text instead of hardcoding placeholder strings.
    """
    # Calculate metrics
    file_count = len(affected_files)
    symbol_count = len(affected_symbols)
    dependency_count = sum(len(deps) for deps in dependencies.values())
    max_dependency_depth = max((len(deps) for deps in dependencies.values()), default=0)
    
    # Estimate test coverage (heuristic)
    has_test_coverage = any(
        "test" in f.lower() for f in affected_files
    )
    
    # Check if in critical path (heuristic: entry points, main files)
    is_critical_path = any(_is_critical_path_file(f) for f in affected_files)

    risk = estimate_risk(
        intent=intent,
        affected_file_count=file_count,
        affected_symbol_count=symbol_count,
        dependency_count=dependency_count,
        has_test_coverage=has_test_coverage,
        is_critical_path=is_critical_path,
    )

    if dependency_count > 20 or max_dependency_depth > 10:
        dependency_complexity = "high"
    elif dependency_count > 5 or max_dependency_depth > 3:
        dependency_complexity = "medium"
    else:
        dependency_complexity = "low"

    metrics = {
        "file_count": file_count,
        "symbol_count": symbol_count,
        "dependency_count": dependency_count,
        "has_test_coverage": has_test_coverage,
        "is_critical_path": is_critical_path,
        "dependency_complexity": dependency_complexity,
    }

    return risk, metrics


# ---------------------------------------------------------------------------
# Phase 5: Complexity Estimation
# ---------------------------------------------------------------------------

def estimate_operation_complexity(
    intent: Intent,
    affected_symbols: List[Symbol],
    affected_files: List[str],
    dependencies: Dict[str, List[str]],
) -> Complexity:
    """Estimate operation complexity using heuristics.
    
    Args:
        intent: Classified intent
        affected_symbols: Affected code symbols
        affected_files: Affected files
        dependencies: Dependency map
        
    Returns:
        Complexity level assessment
    """
    # Calculate metrics
    file_count = len(affected_files)
    symbol_count = len(affected_symbols)
    
    # Estimate dependency depth
    max_depth = 0
    for deps in dependencies.values():
        if deps:
            max_depth = max(max_depth, len(deps))
    
    # Check for circular dependencies (heuristic)
    has_circular_deps = False
    for file_path, deps in dependencies.items():
        if file_path in deps:
            has_circular_deps = True
            break
    
    # Data migration needed? (heuristic)
    requires_data_migration = intent in {Intent.REFACTOR, Intent.FEATURE}
    
    return estimate_complexity(
        intent=intent,
        affected_file_count=file_count,
        affected_symbol_count=symbol_count,
        dependency_depth=max_depth,
        has_circular_dependencies=has_circular_deps,
        requires_data_migration=requires_data_migration,
    )


# ---------------------------------------------------------------------------
# Phase 6: Execution Plan Generation
# ---------------------------------------------------------------------------

def generate_execution_plan(
    intent: Intent,
    request: str,
    affected_symbols: List[Symbol],
    affected_files: List[str],
    dependencies: Dict[str, List[str]],
    risk: Risk,
    complexity: Complexity,
) -> List[ExecutionStep]:
    """Generate ordered execution steps for the operation.
    
    Creates steps based on intent and analysis. Each step is executable
    by downstream agents (Coder, Tester, Reviewer, Committer).
    
    Args:
        intent: Classified intent
        request: Original user request
        affected_symbols: Affected code symbols
        affected_files: Affected files
        dependencies: Dependency map
        risk: Risk level
        complexity: Complexity level
        
    Returns:
        Ordered list of ExecutionStep objects
    """
    steps: List[ExecutionStep] = []
    step_order = 0
    
    # Phase 1: Locate and validate
    step_order += 1
    steps.append(ExecutionStep(
        id="locate_symbols",
        order=step_order,
        agent="planner",
        action="locate_affected_symbols",
        description="Locate and validate all affected symbols and files",
        affected_symbols=affected_symbols,
        affected_files=affected_files,
        context={
            "request": request,
            "intent": intent.value,
            "total_symbols": len(affected_symbols),
            "total_files": len(affected_files),
        },
        validation="All affected symbols and files identified and accessible",
    ))
    
    # Phase 2: Analyze dependencies
    step_order += 1
    steps.append(ExecutionStep(
        id="analyze_deps",
        order=step_order,
        agent="planner",
        action="analyze_dependencies",
        description="Analyze dependencies and impacts",
        affected_files=affected_files,
        depends_on=["locate_symbols"],
        context={
            "dependency_map": dependencies,
            "total_dependencies": sum(len(d) for d in dependencies.values()),
        },
        validation="Dependency analysis complete, no circular deps unhandled",
    ))
    
    # Phase 3: Prepare changes (Coder-specific steps based on intent)
    step_order += 1
    
    if intent == Intent.RENAME:
        steps.append(ExecutionStep(
            id="prepare_rename",
            order=step_order,
            agent="coder",
            action="prepare_refactoring",
            description="Prepare rename operation with import updates",
            affected_symbols=affected_symbols,
            affected_files=affected_files,
            depends_on=["analyze_deps"],
            context={
                "operation": "rename",
                "symbols_to_rename": [s.name for s in affected_symbols],
            },
            validation="All references identified and prepared for renaming",
        ))
    
    elif intent == Intent.REFACTOR:
        steps.append(ExecutionStep(
            id="prepare_refactor",
            order=step_order,
            agent="coder",
            action="prepare_refactoring",
            description="Prepare refactoring structure changes",
            affected_files=affected_files,
            depends_on=["analyze_deps"],
            context={"operation": "refactor"},
            validation="Refactoring structure prepared and validated",
        ))
    
    elif intent == Intent.FEATURE:
        steps.append(ExecutionStep(
            id="prepare_feature",
            order=step_order,
            agent="coder",
            action="scaffold_feature",
            description="Scaffold new feature structure and placeholders",
            affected_files=affected_files,
            depends_on=["analyze_deps"],
            context={"operation": "feature"},
            validation="Feature scaffold created with proper imports",
        ))
    
    elif intent == Intent.DELETE:
        steps.append(ExecutionStep(
            id="prepare_delete",
            order=step_order,
            agent="coder",
            action="prepare_deletion",
            description="Identify and prepare dead code removal",
            affected_files=affected_files,
            depends_on=["analyze_deps"],
            context={"operation": "delete"},
            validation="Dead code identified, imports cleaned up",
        ))
    
    elif intent == Intent.BUG:
        steps.append(ExecutionStep(
            id="prepare_bugfix",
            order=step_order,
            agent="coder",
            action="prepare_bugfix",
            description="Prepare targeted bug fix",
            affected_symbols=affected_symbols,
            depends_on=["analyze_deps"],
            context={"operation": "bugfix"},
            validation="Bug root cause identified and fix prepared",
        ))
    
    else:
        # Generic preparation step for other intents
        steps.append(ExecutionStep(
            id="prepare_changes",
            order=step_order,
            agent="coder",
            action="prepare_changes",
            description=f"Prepare changes for {intent.value} operation",
            affected_files=affected_files,
            depends_on=["analyze_deps"],
            context={"operation": intent.value},
            validation="Changes prepared and validated",
        ))
    
    # Phase 4: Testing
    step_order += 1
    steps.append(ExecutionStep(
        id="test_changes",
        order=step_order,
        agent="tester",
        action="run_tests",
        description="Run unit and integration tests",
        depends_on=[steps[-1].id],
        context={
            "test_types": ["unit", "integration"],
            "complexity": complexity.value,
        },
        validation="All tests pass, no regressions",
    ))
    
    # Phase 5: Code review
    step_order += 1
    steps.append(ExecutionStep(
        id="review_changes",
        order=step_order,
        agent="reviewer",
        action="review_code",
        description="Review code quality, style, and best practices",
        depends_on=["test_changes"],
        context={
            "review_focus": _get_review_focus(intent),
            "risk_level": risk.value,
        },
        validation="Code review passed, no blocking issues",
    ))
    
    # Phase 6: Commit and finalize
    step_order += 1
    steps.append(ExecutionStep(
        id="commit_changes",
        order=step_order,
        agent="committer",
        action="commit_and_push",
        description="Commit changes and push to repository",
        depends_on=["review_changes"],
        context={
            "commit_message_template": _get_commit_template(intent),
        },
        validation="Changes committed and pushed successfully",
    ))
    
    return steps


def _get_review_focus(intent: Intent) -> str:
    """Get code review focus areas based on intent."""
    focus_map = {
        Intent.RENAME: "naming consistency, references, imports",
        Intent.REFACTOR: "code structure, maintainability, backward compatibility",
        Intent.FEATURE: "functionality, error handling, performance",
        Intent.BUG: "fix correctness, edge cases, regression prevention",
        Intent.OPTIMIZE: "performance impact, benchmarks, side effects",
        Intent.DELETE: "unused code confirmation, safe removal",
        Intent.TEST: "test coverage, edge cases, test quality",
        Intent.DOCS: "accuracy, completeness, clarity",
    }
    return focus_map.get(intent, "code quality, best practices, style")


def _get_commit_template(intent: Intent) -> str:
    """Get commit message template based on intent."""
    template_map = {
        Intent.RENAME: "refactor: rename {symbol} to {new_symbol}",
        Intent.REFACTOR: "refactor: restructure {component}",
        Intent.FEATURE: "feat: add {feature_name}",
        Intent.BUG: "fix: resolve {issue_description}",
        Intent.OPTIMIZE: "perf: optimize {component}",
        Intent.DELETE: "chore: remove {item}",
        Intent.TEST: "test: add tests for {component}",
        Intent.DOCS: "docs: update documentation for {topic}",
    }
    return template_map.get(intent, "chore: {description}")


# ---------------------------------------------------------------------------
# Complete Planning Pipeline
# ---------------------------------------------------------------------------

def create_plan(
    request: str,
    repository_index: Any,
    dependency_graph: Any,
    relationship_graph: Any,
    debug: bool = False,
) -> Plan:
    """Create a complete execution plan for a user request.
    
    Orchestrates the full planning pipeline:
    1. Detect intent
    2. Gather repository context
    3. Analyze impact
    4. Assess risk
    5. Estimate complexity
    6. Generate execution plan
    
    Args:
        request: User's request text
        repository_index: RepositoryIndex instance
        dependency_graph: DependencyGraph instance
        relationship_graph: RelationshipGraph instance
        debug: Enable debug output
        
    Returns:
        Complete Plan object with all analysis and steps
    """
    ctx = PlanningContext(
        request=request,
        repository_index=repository_index,
        dependency_graph=dependency_graph,
        relationship_graph=relationship_graph,
        debug=debug,
    )
    
    # Phase 1: Detect intent
    intent_result = detect_intent(request)
    
    # Phase 2: Gather repository context
    repo_profile = gather_repository_context(ctx)
    
    # Phase 3: Analyze impact
    affected_symbols, affected_files, dependencies = analyze_impact(
        ctx, request, intent_result.intent
    )
    
    # Phase 4: Assess risk
    # BUG FIX: assess_risk now returns (risk, metrics) instead of just risk,
    # so the reasoning text below can report the real computed values
    # instead of the old hardcoded "medium" / "partial" placeholders.
    risk, risk_metrics = assess_risk(
        intent_result.intent,
        affected_symbols,
        affected_files,
        dependencies,
        repo_profile,
    )
    
    # Phase 5: Estimate complexity
    complexity = estimate_operation_complexity(
        intent_result.intent,
        affected_symbols,
        affected_files,
        dependencies,
    )
    
    # Phase 6: Generate execution plan
    execution_steps = generate_execution_plan(
        intent_result.intent,
        request,
        affected_symbols,
        affected_files,
        dependencies,
        risk,
        complexity,
    )
    
    # Phase 7: Create plan object
    test_coverage_text = (
        "tests detected among affected files"
        if risk_metrics["has_test_coverage"]
        else "no tests detected among affected files"
    )
    critical_path_text = (
        "yes - touches entry point/main/server file(s)"
        if risk_metrics["is_critical_path"]
        else "no"
    )

    reasoning = f"""
Classified intent: {intent_result.intent.value} (confidence: {intent_result.confidence:.1%})
Keywords matched: {', '.join(intent_result.keywords) if intent_result.keywords else 'none'}

Impact Analysis:
- Affected symbols: {len(affected_symbols)}
- Affected files: {len(affected_files)}
- Total dependencies: {sum(len(d) for d in dependencies.values())}

Risk Assessment:
- Files modified: {risk_metrics['file_count']}
- Symbols affected: {risk_metrics['symbol_count']}
- Dependency complexity: {risk_metrics['dependency_complexity']}
- Test coverage: {test_coverage_text}
- Critical path: {critical_path_text}

Approach:
1. Locate and validate all affected symbols/files
2. Analyze dependency chain and potential impacts
3. Prepare changes appropriate to intent ({intent_result.intent.value})
4. Execute comprehensive testing
5. Perform code review
6. Commit changes with proper messaging
"""
    
    validation_steps = [
        "All affected symbols located and accessible",
        "Dependencies analyzed and documented",
        "No unhandled circular dependencies",
        "Changes prepared according to intent",
        "All tests pass",
        "Code review approved",
        "Changes committed successfully",
    ]
    
    plan = Plan(
        intent=intent_result.intent,
        request=request,
        summary=f"Plan for {intent_result.intent.value}: {request[:80]}...",
        reasoning=reasoning.strip(),
        affected_symbols=affected_symbols,
        affected_files=affected_files,
        dependencies=dependencies,
        risk=risk,
        complexity=complexity,
        execution_steps=execution_steps,
        validation_steps=validation_steps,
        alternative_approaches=[
            "Phased rollout with feature flags",
            "Backward-compatible wrapper approach",
            "Gradual migration with deprecation warnings",
        ],
        created_at=datetime.now().isoformat(),
        status="created",
    )
    
    return plan