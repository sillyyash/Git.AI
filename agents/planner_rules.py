"""Intent classification and heuristic rules for the Planner Agent.

Analyzes user requests and classifies them into well-defined intents.
Provides heuristics for risk, complexity, and confidence estimation.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

from agents.planner_models import Intent, Risk, Complexity, IntentClassificationResult
from agents.planner_config import DEFAULT_RISK_WEIGHTS, DEFAULT_COMPLEXITY_WEIGHTS


# ---------------------------------------------------------------------------
# Intent Keywords and Patterns
# ---------------------------------------------------------------------------

INTENT_KEYWORDS: Dict[Intent, List[str]] = {
    Intent.RENAME: [
        "rename", "refactor name", "change name", "rename to", "call it",
        "rename function", "rename class", "rename variable", "rename method",
    ],
    Intent.REFACTOR: [
        "refactor", "rewrite", "restructure", "reorganize", "clean up",
        "extract", "consolidate", "merge", "split", "simplify",
        "improve code", "code quality", "make it cleaner", "reorganize code",
    ],
    Intent.FEATURE: [
        "add feature", "implement", "add", "new functionality", "add support",
        "enable", "support", "create", "build", "add endpoint", "add page",
        "new route", "new component", "add button", "add field",
    ],
    Intent.BUG: [
        "fix bug", "bug", "broken", "not working", "crash", "error",
        "fix issue", "issue", "problem", "fix the", "fix it",
        "wrong behavior", "incorrect", "broken", "fails",
    ],
    Intent.EXPLAIN: [
        "explain", "help understand", "what does", "how does", "why",
        "what is", "tell me about", "describe", "clarify", "how it works",
        "understand", "learn about", "what's the", "where is",
    ],
    Intent.REVIEW: [
        "review", "code review", "check", "look at", "examine",
        "review code", "review changes", "review pull", "pr review",
        "check for", "find issues", "lint",
    ],
    Intent.OPTIMIZE: [
        "optimize", "performance", "speed up", "make faster", "efficiency",
        "improve performance", "benchmark", "profile", "improve speed",
        "optimize for", "cache", "reduce complexity",
    ],
    Intent.DELETE: [
        "delete", "remove", "remove code", "dead code", "remove file",
        "clean up", "remove unused", "trim", "prune", "get rid of",
        "eliminate", "drop support for",
    ],
    Intent.GENERATE: [
        "generate", "create from", "auto generate", "scaffold", "template",
        "boilerplate", "generate test", "generate code", "generate docs",
        "create skeleton", "stub out",
    ],
    Intent.TEST: [
        "test", "write test", "add test", "unit test", "integration test",
        "testing", "test case", "add tests", "test coverage", "e2e test",
        "acceptance test", "test suite",
    ],
    Intent.DOCS: [
        "document", "add docs", "documentation", "docstring", "comment",
        "add comment", "explain in docs", "document the", "readme",
        "api docs", "documentation",
    ],
}

# Reverse index: keyword -> intents
KEYWORD_TO_INTENTS: Dict[str, Set[Intent]] = {}
for intent, keywords in INTENT_KEYWORDS.items():
    for keyword in keywords:
        if keyword not in KEYWORD_TO_INTENTS:
            KEYWORD_TO_INTENTS[keyword] = set()
        KEYWORD_TO_INTENTS[keyword].add(intent)


# ---------------------------------------------------------------------------
# Classification Functions
# ---------------------------------------------------------------------------

def classify_intent(request: str) -> IntentClassificationResult:
    """Classify user intent from request text using keyword/pattern heuristics."""
    request_lower = request.lower()
    request_tokens = set(re.findall(r'\b\w+\b', request_lower))

    intent_scores: Dict[Intent, Tuple[float, List[str]]] = {
        intent: (0.0, []) for intent in Intent
    }

    for keyword, intents in KEYWORD_TO_INTENTS.items():
        if keyword in request_lower:
            for intent in intents:
                score, matched = intent_scores[intent]
                intent_scores[intent] = (score + 1.0, matched + [keyword])

    for keyword, intents in KEYWORD_TO_INTENTS.items():
        tokens = keyword.split()
        if all(t in request_tokens for t in tokens):
            for intent in intents:
                score, matched = intent_scores[intent]
                if keyword not in matched:
                    intent_scores[intent] = (score + 0.5, matched)

    if re.search(r'\bcall\s+(\w+)', request_lower):
        intent_scores[Intent.RENAME] = (intent_scores[Intent.RENAME][0] + 0.3,
                                        intent_scores[Intent.RENAME][1])

    if re.search(r'(import|from)\s+', request_lower):
        intent_scores[Intent.REFACTOR] = (intent_scores[Intent.REFACTOR][0] + 0.2,
                                          intent_scores[Intent.REFACTOR][1])

    if re.search(r'(where|how|what|explain|understand|tell)', request_lower):
        intent_scores[Intent.EXPLAIN] = (intent_scores[Intent.EXPLAIN][0] + 0.3,
                                         intent_scores[Intent.EXPLAIN][1])

    best_intent = Intent.UNKNOWN
    best_score = 0.0
    best_keywords: List[str] = []

    for intent, (score, keywords) in intent_scores.items():
        if score > best_score:
            best_score = score
            best_intent = intent
            best_keywords = keywords

    confidence = min(best_score / max(5.0, len(request_tokens)), 1.0)

    if best_score == 0.0:
        best_intent = Intent.UNKNOWN
        confidence = 0.0

    reasoning = f"Matched keywords: {', '.join(best_keywords)}" if best_keywords else "No keyword matches"

    return IntentClassificationResult(
        intent=best_intent,
        confidence=confidence,
        keywords=best_keywords,
        reasoning=reasoning,
    )


# ---------------------------------------------------------------------------
# Risk Estimation Heuristics (config-driven, no hardcoded weights)
# ---------------------------------------------------------------------------

_HIGH_RISK_INTENTS = {Intent.DELETE, Intent.REFACTOR, Intent.FEATURE, Intent.OPTIMIZE}
_MEDIUM_RISK_INTENTS = {Intent.BUG, Intent.GENERATE, Intent.RENAME, Intent.TEST}


def estimate_risk(
    intent: Intent,
    affected_file_count: int,
    affected_symbol_count: int,
    dependency_count: int,
    has_test_coverage: bool,
    is_critical_path: bool,
    weights: Optional[Dict[str, float]] = None,
) -> Risk:
    """Estimate risk level for a planned operation. `weights` overrides the
    scoring contribution of each factor; defaults come from PlannerConfig."""
    w = weights or DEFAULT_RISK_WEIGHTS
    risk_score = 0.0

    if intent in _HIGH_RISK_INTENTS:
        risk_score += w["intent_high"]
    if intent in _MEDIUM_RISK_INTENTS:
        risk_score += w["intent_medium"]

    if affected_file_count > 10:
        risk_score += w["files_gt10"]
    elif affected_file_count > 5:
        risk_score += w["files_gt5"]
    elif affected_file_count > 1:
        risk_score += w["files_gt1"]

    if affected_symbol_count > 20:
        risk_score += w["symbols_gt20"]
    elif affected_symbol_count > 10:
        risk_score += w["symbols_gt10"]

    if dependency_count > 50:
        risk_score += w["deps_gt50"]
    elif dependency_count > 20:
        risk_score += w["deps_gt20"]
    elif dependency_count > 5:
        risk_score += w["deps_gt5"]

    if not has_test_coverage:
        risk_score += w["no_test_coverage"]

    if is_critical_path:
        risk_score += w["critical_path"]

    if risk_score >= w["threshold_high"]:
        return Risk.HIGH
    elif risk_score >= w["threshold_medium"]:
        return Risk.MEDIUM
    return Risk.LOW


# ---------------------------------------------------------------------------
# Complexity Estimation Heuristics (config-driven, no hardcoded weights)
# ---------------------------------------------------------------------------

_LARGE_COMPLEXITY_INTENTS = {Intent.FEATURE, Intent.REFACTOR, Intent.GENERATE}
_MEDIUM_COMPLEXITY_INTENTS = {Intent.OPTIMIZE, Intent.DELETE, Intent.BUG, Intent.RENAME}
_SMALL_COMPLEXITY_INTENTS = {Intent.TEST, Intent.DOCS, Intent.EXPLAIN, Intent.REVIEW}


def estimate_complexity(
    intent: Intent,
    affected_file_count: int,
    affected_symbol_count: int,
    dependency_depth: int,
    has_circular_dependencies: bool,
    requires_data_migration: bool,
    weights: Optional[Dict[str, float]] = None,
) -> Complexity:
    """Estimate complexity level for a planned operation. `weights` overrides
    the scoring contribution of each factor; defaults come from PlannerConfig."""
    w = weights or DEFAULT_COMPLEXITY_WEIGHTS
    complexity_score = 0.0

    if intent in _LARGE_COMPLEXITY_INTENTS:
        complexity_score += w["intent_large"]
    if intent in _MEDIUM_COMPLEXITY_INTENTS:
        complexity_score += w["intent_medium"]
    if intent in _SMALL_COMPLEXITY_INTENTS:
        complexity_score += w["intent_small"]

    if affected_file_count > 10:
        complexity_score += w["files_gt10"]
    elif affected_file_count > 5:
        complexity_score += w["files_gt5"]
    elif affected_file_count > 1:
        complexity_score += w["files_gt1"]

    if affected_symbol_count > 30:
        complexity_score += w["symbols_gt30"]
    elif affected_symbol_count > 15:
        complexity_score += w["symbols_gt15"]
    elif affected_symbol_count > 5:
        complexity_score += w["symbols_gt5"]

    if dependency_depth > 10:
        complexity_score += w["depth_gt10"]
    elif dependency_depth > 5:
        complexity_score += w["depth_gt5"]

    if has_circular_dependencies:
        complexity_score += w["circular_deps"]

    if requires_data_migration:
        complexity_score += w["data_migration"]

    if complexity_score >= w["threshold_large"]:
        return Complexity.LARGE
    elif complexity_score >= w["threshold_medium"]:
        return Complexity.MEDIUM
    elif complexity_score >= w["threshold_small"]:
        return Complexity.SMALL
    return Complexity.TRIVIAL


# ---------------------------------------------------------------------------
# Confidence Estimation
# ---------------------------------------------------------------------------

def compute_confidence(
    intent_confidence: float,
    symbol_match_ratio: float,
    repository_confidence: float,
    dependency_confidence: float,
) -> float:
    """Combine intent/search/repository/dependency confidence into one
    normalized 0.0-1.0 score. Weights sum to 1.0."""
    weights = (0.40, 0.25, 0.20, 0.15)
    values = (intent_confidence, symbol_match_ratio, repository_confidence, dependency_confidence)
    score = sum(w * max(0.0, min(1.0, v)) for w, v in zip(weights, values))
    return max(0.0, min(1.0, score))