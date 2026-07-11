"""Data models for the AI Planner Agent.

Defines structured dataclasses for representing planning operations,
execution steps, risk/complexity assessments, and the complete plan output.

All models are strongly typed, JSON-serializable (via asdict), and
properly documented for AI agents consuming them.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional, Any


class Intent(str, Enum):
    """Classification of user intent for code operations.
    
    Used to determine strategy and complexity estimation.
    """
    RENAME = "rename"
    REFACTOR = "refactor"
    FEATURE = "feature"
    BUG = "bug"
    EXPLAIN = "explain"
    REVIEW = "review"
    OPTIMIZE = "optimize"
    DELETE = "delete"
    GENERATE = "generate"
    TEST = "test"
    DOCS = "docs"
    UNKNOWN = "unknown"


class Risk(str, Enum):
    """Risk level for a planned operation.
    
    LOW: Changes affect only isolated, well-tested code with clear dependencies.
    MEDIUM: Changes affect multiple modules or have some unclear dependencies.
    HIGH: Changes affect critical code, have circular dependencies, or low test coverage.
    """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Complexity(str, Enum):
    """Complexity estimate for a planned operation.
    
    TRIVIAL: Single-file changes, no dependencies.
    SMALL: Single module/component, local changes, clear scope.
    MEDIUM: Multiple files/modules, moderate dependencies, testing required.
    LARGE: Cross-module refactoring, many dependencies, major testing required.
    """
    TRIVIAL = "trivial"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


@dataclass
class Symbol:
    """Represents a code symbol (function, class, selector, etc.)."""
    name: str
    kind: str  # "function", "class", "selector", "css_class", "id", "variable", etc.
    file: Optional[str] = None
    line: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class ExecutionStep:
    """A single atomic step in the execution plan.
    
    Steps are ordered and may have dependencies. Each step represents a logical
    unit of work to be performed by Coder, Tester, or Reviewer agents.
    """
    id: str
    order: int
    agent: str  # "planner", "coder", "tester", "reviewer", "committer"
    action: str  # e.g., "locate_symbol", "update_imports", "run_tests", "create_pr"
    description: str
    
    affected_symbols: List[Symbol] = field(default_factory=list)
    affected_files: List[str] = field(default_factory=list)
    
    # Dependencies on other steps (step IDs)
    depends_on: List[str] = field(default_factory=list)
    
    # Context and hints for the agent executing this step
    context: Dict[str, Any] = field(default_factory=dict)
    
    # Expected outcome validation
    validation: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data["affected_symbols"] = [s.to_dict() for s in self.affected_symbols]
        return data


@dataclass
class Plan:
    """Complete planning output for a user request.
    
    Represents the full strategy, analysis, and execution plan for a code operation.
    This is the primary output of the Planner Agent and input to downstream agents.
    """
    
    # Core identification
    intent: Intent
    request: str
    summary: str
    reasoning: str
    
    # Analysis results
    affected_symbols: List[Symbol] = field(default_factory=list)
    affected_files: List[str] = field(default_factory=list)
    dependencies: Dict[str, List[str]] = field(default_factory=dict)  # file -> [dependencies]
    
    # Risk and complexity assessment
    risk: Risk = Risk.MEDIUM
    complexity: Complexity = Complexity.MEDIUM
    
    # Execution strategy
    execution_steps: List[ExecutionStep] = field(default_factory=list)
    validation_steps: List[str] = field(default_factory=list)
    
    # Additional metadata
    alternative_approaches: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # Execution tracking
    status: str = "created"  # "created", "in_progress", "completed", "failed"
    created_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data["intent"] = self.intent.value
        data["risk"] = self.risk.value
        data["complexity"] = self.complexity.value
        data["affected_symbols"] = [s.to_dict() for s in self.affected_symbols]
        data["execution_steps"] = [s.to_dict() for s in self.execution_steps]
        return data
    
    def to_json_serializable(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return self.to_dict()


@dataclass
class PlanningContext:
    """Context passed to planning functions.
    
    Encapsulates all required data for planning without requiring direct
    access to graphs or other internal structures.
    """
    request: str
    repository_index: Any  # RepositoryIndex
    dependency_graph: Any  # DependencyGraph
    relationship_graph: Any  # RelationshipGraph
    debug: bool = False


@dataclass
class IntentClassificationResult:
    """Result of intent classification."""
    intent: Intent
    confidence: float  # 0.0 to 1.0
    keywords: List[str]
    reasoning: str
