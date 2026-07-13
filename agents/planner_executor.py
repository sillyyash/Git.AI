"""Planner execution coordinator.

Orchestrates the planning pipeline. Never accesses graphs directly and never
re-implements repository intelligence, context gathering, or prompt assembly
- those are core.queries / core.context_builder / core.prompt_builder's job.

Pipeline:

    User request
        v
    classify_intent()                  (agents.planner_rules - planner's own job)
        v
    context_builder.build_context()    (repository intelligence, symbol search,
        v                               dependency/impact analysis - reused, not duplicated)
    [missing-info / clarification check -> early return if ambiguous]
        v
    prompt_builder.build_prompt(mode="planner", output_format="json")
        v
    core.model.OllamaClient.generate()  (LLM plans; heuristics are the fallback,
        v                                not the primary path)
    parse structured JSON -> risk/complexity/steps/confidence/reasoning
        v
    (heuristic estimate_risk/estimate_complexity/generate_execution_plan
     fill in anything the LLM didn't return, or everything if use_llm=False
     or the model call fails)
        v
    validate + repair execution steps
        v
    Plan object
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Type

from agents.planner_config import PlannerConfig
from agents.planner_models import (
    Intent,
    Risk,
    Complexity,
    Plan,
    ExecutionStep,
    Symbol,
    IntentClassificationResult,
)
from agents.planner_rules import classify_intent, estimate_risk, estimate_complexity, compute_confidence
from agents.planner_prompts import get_planner_json_prompt

# Public APIs only - this is the whole point of the rewrite.
from core import queries
from core.context_builder import build_context
from core.prompt_builder import build_prompt
from core.model import OllamaClient


# ---------------------------------------------------------------------------
# Phase 1: Intent Detection
# ---------------------------------------------------------------------------

def detect_intent(request: str) -> IntentClassificationResult:
    """Detect user intent from request text (keyword/pattern heuristics)."""
    return classify_intent(request)


# ---------------------------------------------------------------------------
# Phase 2: Impact extraction from Context Builder output
# ---------------------------------------------------------------------------
#
# NOTE: this used to be a hand-rolled analyze_impact() that called
# queries.search_symbol() in a loop and re-derived affected files/deps
# itself - duplicating what context_builder.build_context() already does
# (symbol scoring, definitions, references, owners, components, dependency
# tree, impact analysis, related files, caching). That loop is gone; we now
# just read the fields context_builder already computed.

def _affected_symbols_from_context(context: Dict[str, Any], config: PlannerConfig) -> List[Symbol]:
    symbols: List[Symbol] = []
    for entry in (context.get("symbols") or [])[: config.max_symbols]:
        name = entry.get("symbol")
        if not name:
            continue
        symbols.append(Symbol(name=name, kind=entry.get("kind", "unknown"), file=entry.get("file")))
    return symbols


def _affected_files_from_context(context: Dict[str, Any], config: PlannerConfig) -> List[str]:
    files: List[str] = []

    def add(f: Optional[str]) -> None:
        if f and f not in files:
            files.append(f)

    for entry in context.get("symbols") or []:
        add(entry.get("file"))
    for f in context.get("owners") or []:
        add(f)
    for f in context.get("related_files") or []:
        add(f)
    for f in context.get("query_files") or []:
        add(f)

    return files[: config.max_files]


# ---------------------------------------------------------------------------
# Phase 3: Critical-path detection (used for risk scoring)
# ---------------------------------------------------------------------------

_CRITICAL_KEYWORDS = {"main", "entry", "index", "app", "server"}


def _is_critical_path_file(file_path: str) -> bool:
    """True only if a path SEGMENT or filename STEM matches a critical
    keyword - not a raw substring (avoids false positives like
    'user_index.py' or 'apparel.py')."""
    normalized = file_path.replace("\\", "/").lower()
    segments = [s for s in normalized.split("/") if s]
    if not segments:
        return False

    filename = segments[-1]
    stem = os.path.splitext(filename)[0]

    if any(segment in _CRITICAL_KEYWORDS for segment in segments[:-1]):
        return True
    for keyword in _CRITICAL_KEYWORDS:
        if stem == keyword or stem.startswith(f"{keyword}_") or stem.startswith(f"{keyword}."):
            return True
    return False


# ---------------------------------------------------------------------------
# Phase 4: LLM-driven planning (primary path)
# ---------------------------------------------------------------------------

def _call_llm_planner(client: OllamaClient, prompt: str) -> Optional[Dict[str, Any]]:
    """Call the model and parse a structured plan. Returns None (never
    raises) on any failure so callers always have a heuristic fallback."""
    try:
        raw = client.generate(prompt)
    except Exception:
        return None

    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text[:4].lower() == "json":
            text = text[4:]
        text = text.strip()

    import json as _json
    try:
        parsed = _json.loads(text)
    except (ValueError, TypeError):
        return None

    return parsed if isinstance(parsed, dict) else None


def _coerce_enum(enum_cls: Type, value: Any, fallback: Any) -> Any:
    if isinstance(value, str):
        try:
            return enum_cls(value.strip().lower())
        except ValueError:
            return fallback
    return fallback


def _steps_from_llm(raw_steps: List[Any], config: PlannerConfig) -> List[ExecutionStep]:
    steps: List[ExecutionStep] = []
    for i, raw in enumerate(raw_steps[: config.max_steps]):
        if not isinstance(raw, dict):
            continue
        symbols = [
            Symbol(name=s, kind="unknown")
            for s in (raw.get("symbols") or [])
            if isinstance(s, str)
        ]
        steps.append(ExecutionStep(
            id=str(raw.get("id") or f"step_{i + 1}"),
            order=i + 1,
            agent=str(raw.get("agent") or "coder"),
            action=str(raw.get("action") or "unspecified"),
            description=str(raw.get("description") or ""),
            affected_symbols=symbols,
            affected_files=[f for f in (raw.get("files") or []) if isinstance(f, str)],
            depends_on=[d for d in (raw.get("depends_on") or []) if isinstance(d, str)],
            validation=raw.get("validation") if isinstance(raw.get("validation"), str) else None,
        ))
    return steps


# ---------------------------------------------------------------------------
# Phase 5: Heuristic execution plan generation (fallback path)
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
    """Generate ordered execution steps for the operation using fixed
    per-intent templates. Used when LLM planning is disabled or fails."""
    steps: List[ExecutionStep] = []
    step_order = 0

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

    step_order += 1
    intent_step_map = {
        Intent.RENAME: ("prepare_rename", "prepare_refactoring", "Prepare rename operation with import updates",
                        {"operation": "rename", "symbols_to_rename": [s.name for s in affected_symbols]}),
        Intent.REFACTOR: ("prepare_refactor", "prepare_refactoring", "Prepare refactoring structure changes",
                           {"operation": "refactor"}),
        Intent.FEATURE: ("prepare_feature", "scaffold_feature", "Scaffold new feature structure and placeholders",
                          {"operation": "feature"}),
        Intent.DELETE: ("prepare_delete", "prepare_deletion", "Identify and prepare dead code removal",
                         {"operation": "delete"}),
        Intent.BUG: ("prepare_bugfix", "prepare_bugfix", "Prepare targeted bug fix",
                     {"operation": "bugfix"}),
    }
    step_id, action, description, extra_context = intent_step_map.get(
        intent, (f"prepare_{intent.value}", "prepare_changes", f"Prepare changes for {intent.value} operation",
                 {"operation": intent.value})
    )
    steps.append(ExecutionStep(
        id=step_id,
        order=step_order,
        agent="coder",
        action=action,
        description=description,
        affected_symbols=affected_symbols if intent in {Intent.RENAME, Intent.BUG} else [],
        affected_files=affected_files if intent != Intent.BUG else [],
        depends_on=["analyze_deps"],
        context=extra_context,
        validation="Changes prepared and validated",
    ))

    step_order += 1
    steps.append(ExecutionStep(
        id="test_changes",
        order=step_order,
        agent="tester",
        action="run_tests",
        description="Run unit and integration tests",
        depends_on=[steps[-1].id],
        context={"test_types": ["unit", "integration"], "complexity": complexity.value},
        validation="All tests pass, no regressions",
    ))

    step_order += 1
    steps.append(ExecutionStep(
        id="review_changes",
        order=step_order,
        agent="reviewer",
        action="review_code",
        description="Review code quality, style, and best practices",
        depends_on=["test_changes"],
        context={"review_focus": _get_review_focus(intent), "risk_level": risk.value},
        validation="Code review passed, no blocking issues",
    ))

    step_order += 1
    steps.append(ExecutionStep(
        id="commit_changes",
        order=step_order,
        agent="committer",
        action="commit_and_push",
        description="Commit changes and push to repository",
        depends_on=["review_changes"],
        context={"commit_message_template": _get_commit_template(intent)},
        validation="Changes committed and pushed successfully",
    ))

    return steps


def _get_review_focus(intent: Intent) -> str:
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
# Phase 6: Plan validation / repair
# ---------------------------------------------------------------------------

def _validate_and_repair(
    steps: List[ExecutionStep],
    affected_files: List[str],
    affected_symbols: List[Symbol],
) -> List[str]:
    """Every non-planner step must reference at least one file or symbol.
    Repair by falling back to the global affected set; record what was
    repaired instead of silently returning an incomplete plan."""
    warnings: List[str] = []
    for step in steps:
        if step.agent == "planner":
            continue
        if not step.affected_files and not step.affected_symbols:
            step.affected_files = list(affected_files)
            step.affected_symbols = list(affected_symbols)
            warnings.append(
                f"Step '{step.id}' had no files/symbols; repaired using globally affected files/symbols."
            )
    return warnings


# ---------------------------------------------------------------------------
# Phase 7: Reasoning text (heuristic fallback, when LLM has none)
# ---------------------------------------------------------------------------

def _build_heuristic_reasoning(
    intent_result: IntentClassificationResult,
    affected_symbols: List[Symbol],
    affected_files: List[str],
    dependencies: Dict[str, List[str]],
    has_test_coverage: bool,
    is_critical_path: bool,
    dependency_complexity: str,
) -> str:
    test_coverage_text = (
        "tests detected among affected files" if has_test_coverage
        else "no tests detected among affected files"
    )
    critical_path_text = (
        "yes - touches entry point/main/server file(s)" if is_critical_path else "no"
    )
    return f"""
Classified intent: {intent_result.intent.value} (confidence: {intent_result.confidence:.1%})
Keywords matched: {', '.join(intent_result.keywords) if intent_result.keywords else 'none'}

Impact Analysis:
- Affected symbols: {len(affected_symbols)}
- Affected files: {len(affected_files)}
- Total dependencies: {sum(len(d) for d in dependencies.values())}

Risk Assessment:
- Dependency complexity: {dependency_complexity}
- Test coverage: {test_coverage_text}
- Critical path: {critical_path_text}

Approach:
1. Locate and validate all affected symbols/files
2. Analyze dependency chain and potential impacts
3. Prepare changes appropriate to intent ({intent_result.intent.value})
4. Execute comprehensive testing
5. Perform code review
6. Commit changes with proper messaging
""".strip()


# ---------------------------------------------------------------------------
# Complete Planning Pipeline
# ---------------------------------------------------------------------------

def create_plan(
    request: str,
    repository_index: Any,
    dependency_graph: Any,
    relationship_graph: Any,
    config: Optional[PlannerConfig] = None,
    debug: bool = False,
) -> Plan:
    """Create a complete execution plan for a user request.

    Args:
        request: User's request text
        repository_index: RepositoryIndex instance
        dependency_graph: DependencyGraph instance
        relationship_graph: RelationshipGraph instance
        config: PlannerConfig (thresholds/weights/mode); defaults if omitted
        debug: Enable debug output

    Returns:
        Complete Plan object with all analysis and steps
    """
    config = config or PlannerConfig()

    # Phase 1: intent
    intent_result = detect_intent(request)

    # Phase 2: repository context (Context Builder owns symbol search,
    # definitions/references/owners/components, dependency tree, impact
    # analysis, and the repository profile - not re-implemented here)
    context = build_context(
        request, repository_index, dependency_graph, relationship_graph,
        max_symbols=config.max_symbols,
    )
    repository_profile: Dict[str, Any] = dict(context.get("repository_profile") or {})

    if config.planning_mode == "deep":
        try:
            full_profile = queries.build_repository_profile(
                repository_index, dependency_graph, relationship_graph
            )
            repository_profile = {**repository_profile, **full_profile}
        except Exception as e:
            if debug:
                print(f"Warning: deep-mode repository profile unavailable: {e}")

    affected_symbols = _affected_symbols_from_context(context, config)
    affected_files = _affected_files_from_context(context, config)

    # Phase 3: missing-information / clarification detection - return early
    # rather than fabricate a plan on ambiguous or unsupported requests.
    missing_information: List[str] = []
    clarification_questions: List[str] = []

    # Don't force clarification for feature requests simply because the
    # classifier confidence is low.
    if (
        intent_result.intent == Intent.UNKNOWN
        or (
            intent_result.intent != Intent.FEATURE
            and intent_result.confidence < config.clarification_threshold
        )
    ): 
        missing_information.append(
             "Intent could not be classified confidently from the request text."
        )
        clarification_questions.append(
             "Could you clarify the type of change you want (rename, add a feature, fix a bug, etc.)?"
        )

    # Existing symbols/files are required for operations that modify code.
    # Feature creation is allowed even when the symbol does not yet exist.
    if (
        intent_result.intent 
        not in {
            Intent.FEATURE,
        }
        and not affected_symbols
        and not affected_files
    ):
        missing_information.append(
            "No matching symbols or files were found in the repository for this request."
        )
        clarification_questions.append(
           "Which file(s) or symbol(s) should this change involve?"
        )

    if clarification_questions:
        return Plan(
            intent=intent_result.intent,
            request=request,
            summary="Clarification needed before a plan can be produced.",
            reasoning="\n".join(missing_information),
            confidence=intent_result.confidence,
            repository_profile=repository_profile,
            missing_information=missing_information,
            clarification_questions=clarification_questions,
            status="needs_clarification",
            created_at=datetime.now().isoformat(),
        )

    # Phase 4: dependency assembly (skipped/limited in "quick" mode)
    if config.planning_mode == "quick":
        affected_files = affected_files[:5]
        dependencies: Dict[str, List[str]] = {}
    else:
        dependencies = {
            f: queries.find_all_dependencies(dependency_graph, f)
            for f in affected_files
        }

    has_test_coverage = any("test" in f.lower() for f in affected_files)
    is_critical_path = any(_is_critical_path_file(f) for f in affected_files)
    dependency_count = sum(len(d) for d in dependencies.values())
    dependency_depth = max((len(d) for d in dependencies.values()), default=0)
    has_circular_deps = any(f in deps for f, deps in dependencies.items())
    requires_data_migration = intent_result.intent in {Intent.REFACTOR, Intent.FEATURE}

    if dependency_count > 20 or dependency_depth > 10:
        dependency_complexity = "high"
    elif dependency_count > 5 or dependency_depth > 3:
        dependency_complexity = "medium"
    else:
        dependency_complexity = "low"

    # Phase 5: heuristic risk/complexity (always computed - either the final
    # answer, or the fallback if the LLM call below fails/is disabled)
    risk = estimate_risk(
        intent_result.intent, len(affected_files), len(affected_symbols),
        dependency_count, has_test_coverage, is_critical_path,
        weights=config.risk_weights,
    )
    complexity = estimate_complexity(
        intent_result.intent, len(affected_files), len(affected_symbols),
        dependency_depth, has_circular_deps, requires_data_migration,
        weights=config.complexity_weights,
    )

    # Phase 6: LLM-driven planning (primary path) via Prompt Builder + model.py
    llm_plan: Optional[Dict[str, Any]] = None
    if config.use_llm:
        try:
            prompt, _ = build_prompt(
                request, context, mode="planner", output_format="json", return_stats=True,
            )
            prompt = f"{prompt}\n\n{get_planner_json_prompt()}"
            client = OllamaClient(**(config.model_overrides or {}))
            llm_plan = _call_llm_planner(client, prompt)
        except Exception as e:
            if debug:
                print(f"Warning: LLM planning unavailable, using heuristics only: {e}")
            llm_plan = None

    if llm_plan:
        risk = _coerce_enum(Risk, llm_plan.get("risk"), risk)
        complexity = _coerce_enum(Complexity, llm_plan.get("complexity"), complexity)

    execution_steps = (
        _steps_from_llm(llm_plan["steps"], config)
        if llm_plan and llm_plan.get("steps")
        else generate_execution_plan(
            intent_result.intent, request, affected_symbols, affected_files,
            dependencies, risk, complexity,
        )
    )[: config.max_steps]

    warnings = _validate_and_repair(execution_steps, affected_files, affected_symbols)

    # Phase 7: confidence - combines intent confidence, how much of the
    # symbol budget we actually filled, and whether repository/dependency
    # context was available at all, then blends in the LLM's own confidence
    # if it returned one.
    symbol_match_ratio = min(1.0, len(affected_symbols) / max(1, config.max_symbols))
    repository_confidence = 1.0 if repository_profile else 0.5
    dependency_confidence = 1.0 if dependencies else 0.5
    confidence = compute_confidence(
        intent_result.confidence, symbol_match_ratio, repository_confidence, dependency_confidence
    )
    llm_confidence = llm_plan.get("confidence") if llm_plan else None
    if isinstance(llm_confidence, (int, float)):
        confidence = (confidence + max(0.0, min(1.0, float(llm_confidence)))) / 2

    reasoning = (
        llm_plan["reasoning"] if llm_plan and isinstance(llm_plan.get("reasoning"), str)
        else _build_heuristic_reasoning(
            intent_result, affected_symbols, affected_files, dependencies,
            has_test_coverage, is_critical_path, dependency_complexity,
        )
    )
    summary = (
        llm_plan["summary"] if llm_plan and isinstance(llm_plan.get("summary"), str)
        else f"Plan for {intent_result.intent.value}: {request[:80]}..."
    )
    assumptions = (
        [a for a in llm_plan.get("assumptions", []) if isinstance(a, str)] if llm_plan else []
    )

    return Plan(
        intent=intent_result.intent,
        request=request,
        summary=summary,
        reasoning=reasoning,
        confidence=confidence,
        repository_profile=repository_profile,
        affected_symbols=affected_symbols,
        affected_files=affected_files,
        dependencies=dependencies,
        risk=risk,
        complexity=complexity,
        execution_steps=execution_steps,
        validation_steps=[
            "All affected symbols located and accessible",
            "Dependencies analyzed and documented",
            "No unhandled circular dependencies",
            "Changes prepared according to intent",
            "All tests pass",
            "Code review approved",
            "Changes committed successfully",
        ],
        alternative_approaches=[
            "Phased rollout with feature flags",
            "Backward-compatible wrapper approach",
            "Gradual migration with deprecation warnings",
        ],
        assumptions=assumptions,
        warnings=warnings,
        created_at=datetime.now().isoformat(),
        status="created",
    )