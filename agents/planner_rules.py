"""Intent classification and heuristic rules for the Planner Agent.

Analyzes user requests and classifies them into well-defined intents.
Provides heuristics for risk and complexity estimation.
"""

from __future__ import annotations

import re
from typing import Dict, List, Set, Tuple

from agents.planner_models import Intent, Risk, Complexity, IntentClassificationResult


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
    """Classify user intent from request text.
    
    Uses keyword matching, patterns, and heuristics to determine the most
    likely intent with a confidence score.
    
    Args:
        request: User's request text
        
    Returns:
        IntentClassificationResult with intent, confidence, keywords, and reasoning
    """
    request_lower = request.lower()
    request_tokens = set(re.findall(r'\b\w+\b', request_lower))
    
    # Score each intent based on keyword matches
    intent_scores: Dict[Intent, Tuple[float, List[str]]] = {
        intent: (0.0, []) for intent in Intent
    }
    
    # Exact keyword matches
    for keyword, intents in KEYWORD_TO_INTENTS.items():
        if keyword in request_lower:
            for intent in intents:
                score, matched = intent_scores[intent]
                intent_scores[intent] = (score + 1.0, matched + [keyword])
    
    # Partial/token matches (lower weight)
    for keyword, intents in KEYWORD_TO_INTENTS.items():
        tokens = keyword.split()
        if all(t in request_tokens for t in tokens):
            for intent in intents:
                score, matched = intent_scores[intent]
                if keyword not in matched:
                    intent_scores[intent] = (score + 0.5, matched)
    
    # Pattern-based detection
    if re.search(r'\bcall\s+(\w+)', request_lower):
        intent_scores[Intent.RENAME] = (intent_scores[Intent.RENAME][0] + 0.3,
                                        intent_scores[Intent.RENAME][1])
    
    if re.search(r'(import|from)\s+', request_lower):
        intent_scores[Intent.REFACTOR] = (intent_scores[Intent.REFACTOR][0] + 0.2,
                                          intent_scores[Intent.REFACTOR][1])
    
    if re.search(r'(where|how|what|explain|understand|tell)', request_lower):
        intent_scores[Intent.EXPLAIN] = (intent_scores[Intent.EXPLAIN][0] + 0.3,
                                         intent_scores[Intent.EXPLAIN][1])
    
    # Find best match
    best_intent = Intent.UNKNOWN
    best_score = 0.0
    best_keywords: List[str] = []
    
    for intent, (score, keywords) in intent_scores.items():
        if score > best_score:
            best_score = score
            best_intent = intent
            best_keywords = keywords
    
    # Normalize confidence to 0.0-1.0
    confidence = min(best_score / max(5.0, len(request_tokens)), 1.0)
    
    # If no good match, default to UNKNOWN
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
# Risk Estimation Heuristics
# ---------------------------------------------------------------------------

def estimate_risk(
    intent: Intent,
    affected_file_count: int,
    affected_symbol_count: int,
    dependency_count: int,
    has_test_coverage: bool,
    is_critical_path: bool,
) -> Risk:
    """Estimate risk level for a planned operation.
    
    Args:
        intent: The classified intent
        affected_file_count: Number of files affected
        affected_symbol_count: Number of symbols affected
        dependency_count: Number of dependencies detected
        has_test_coverage: Whether affected code has tests
        is_critical_path: Whether code is in critical path
        
    Returns:
        Risk level assessment
    """
    risk_score = 0.0
    
    # Intent-based baseline
    high_risk_intents = {Intent.DELETE, Intent.REFACTOR, Intent.FEATURE, Intent.OPTIMIZE}
    if intent in high_risk_intents:
        risk_score += 2.0
    
    medium_risk_intents = {Intent.BUG, Intent.GENERATE, Intent.RENAME, Intent.TEST}
    if intent in medium_risk_intents:
        risk_score += 1.0
    
    # Impact-based scoring
    if affected_file_count > 10:
        risk_score += 2.0
    elif affected_file_count > 5:
        risk_score += 1.0
    elif affected_file_count > 1:
        risk_score += 0.5
    
    if affected_symbol_count > 20:
        risk_score += 2.0
    elif affected_symbol_count > 10:
        risk_score += 1.0
    
    if dependency_count > 50:
        risk_score += 2.0
    elif dependency_count > 20:
        risk_score += 1.0
    elif dependency_count > 5:
        risk_score += 0.5
    
    # Test coverage
    if not has_test_coverage:
        risk_score += 2.0
    
    # Critical path
    if is_critical_path:
        risk_score += 2.0
    
    # Normalize and classify
    if risk_score >= 6.0:
        return Risk.HIGH
    elif risk_score >= 3.0:
        return Risk.MEDIUM
    else:
        return Risk.LOW


# ---------------------------------------------------------------------------
# Complexity Estimation Heuristics
# ---------------------------------------------------------------------------

def estimate_complexity(
    intent: Intent,
    affected_file_count: int,
    affected_symbol_count: int,
    dependency_depth: int,
    has_circular_dependencies: bool,
    requires_data_migration: bool,
) -> Complexity:
    """Estimate complexity level for a planned operation.
    
    Args:
        intent: The classified intent
        affected_file_count: Number of files affected
        affected_symbol_count: Number of symbols affected
        dependency_depth: Max depth of dependency tree
        has_circular_dependencies: Whether circular deps exist
        requires_data_migration: Whether data migration needed
        
    Returns:
        Complexity level assessment
    """
    complexity_score = 0.0
    
    # Intent-based baseline
    large_intents = {Intent.FEATURE, Intent.REFACTOR, Intent.GENERATE}
    if intent in large_intents:
        complexity_score += 2.0
    
    medium_intents = {Intent.OPTIMIZE, Intent.DELETE, Intent.BUG, Intent.RENAME}
    if intent in medium_intents:
        complexity_score += 1.0
    
    small_intents = {Intent.TEST, Intent.DOCS, Intent.EXPLAIN, Intent.REVIEW}
    if intent in small_intents:
        complexity_score += 0.5
    
    # Impact-based scoring
    if affected_file_count > 10:
        complexity_score += 2.0
    elif affected_file_count > 5:
        complexity_score += 1.0
    elif affected_file_count > 1:
        complexity_score += 0.5
    
    if affected_symbol_count > 30:
        complexity_score += 2.0
    elif affected_symbol_count > 15:
        complexity_score += 1.0
    elif affected_symbol_count > 5:
        complexity_score += 0.5
    
    # Dependency complexity
    if dependency_depth > 10:
        complexity_score += 2.0
    elif dependency_depth > 5:
        complexity_score += 1.0
    
    if has_circular_dependencies:
        complexity_score += 2.0
    
    if requires_data_migration:
        complexity_score += 2.0
    
    # Normalize and classify
    if complexity_score >= 6.0:
        return Complexity.LARGE
    elif complexity_score >= 3.0:
        return Complexity.MEDIUM
    elif complexity_score >= 1.0:
        return Complexity.SMALL
    else:
        return Complexity.TRIVIAL
