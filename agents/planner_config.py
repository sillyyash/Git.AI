"""Planner configuration. No planner file hardcodes thresholds, weights, or
limits - they all live here so behavior is tunable without code changes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


DEFAULT_RISK_WEIGHTS: Dict[str, float] = {
    "intent_high": 2.0, "intent_medium": 1.0,
    "files_gt10": 2.0, "files_gt5": 1.0, "files_gt1": 0.5,
    "symbols_gt20": 2.0, "symbols_gt10": 1.0,
    "deps_gt50": 2.0, "deps_gt20": 1.0, "deps_gt5": 0.5,
    "no_test_coverage": 2.0, "critical_path": 2.0,
    "threshold_high": 6.0, "threshold_medium": 3.0,
}

DEFAULT_COMPLEXITY_WEIGHTS: Dict[str, float] = {
    "intent_large": 2.0, "intent_medium": 1.0, "intent_small": 0.5,
    "files_gt10": 2.0, "files_gt5": 1.0, "files_gt1": 0.5,
    "symbols_gt30": 2.0, "symbols_gt15": 1.0, "symbols_gt5": 0.5,
    "depth_gt10": 2.0, "depth_gt5": 1.0,
    "circular_deps": 2.0, "data_migration": 2.0,
    "threshold_large": 6.0, "threshold_medium": 3.0, "threshold_small": 1.0,
}


@dataclass
class PlannerConfig:
    confidence_threshold: float = 0.4
    clarification_threshold: float = 0.3
    max_symbols: int = 8
    max_files: int = 12
    max_steps: int = 12
    validation_attempts: int = 2
    planning_mode: str = "normal"  # "quick" | "normal" | "deep"
    use_llm: bool = True
    risk_weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_RISK_WEIGHTS))
    complexity_weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_COMPLEXITY_WEIGHTS))
    model_overrides: Optional[Dict] = None