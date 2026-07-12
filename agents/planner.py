"""AI Planner Agent for AutoDevAI.

The Planner is the first agent in the AI pipeline. It:
- Understands user requests
- Classifies intent
- Analyzes repository impact via Context Builder / Query API
- Plans via the LLM (core.model), falling back to heuristics
- Estimates risk, complexity, and confidence
- Generates ordered execution plans

The Planner ONLY plans; it never modifies code, files, or repositories.

Output is strictly structured data (Plan objects) suitable for downstream
agents (Coder, Tester, Reviewer, Committer) to execute.

Architecture:
- Uses ONLY core.queries.* for repository knowledge
- Uses core.context_builder for repository context (never re-derives it)
- Uses core.prompt_builder for prompt assembly (never hand-builds prompts)
- Uses core.model.OllamaClient for generation (never touches HTTP/Ollama directly)
- Never accesses graphs directly
- All thresholds/weights/modes come from PlannerConfig, never hardcoded
"""

from __future__ import annotations

from typing import Any, Optional, Dict
import json

from agents.planner_config import PlannerConfig
from agents.planner_models import Plan
from agents.planner_executor import create_plan


class PlannerAgent:
    """Main Planner Agent class.
    
    Orchestrates planning for code modification requests. Public interface
    for creating structured execution plans.
    """
    
    def __init__(self, config: Optional[PlannerConfig] = None, debug: bool = False):
        """Initialize the Planner Agent.
        
        Args:
            config: PlannerConfig controlling thresholds, weights, planning
                mode, and LLM usage. Defaults to PlannerConfig() if omitted.
            debug: Enable debug output
        """
        self.config = config or PlannerConfig()
        self.debug = debug
    
    def plan(
        self,
        request: str,
        repository_index: Any,
        dependency_graph: Any,
        relationship_graph: Any,
    ) -> Plan:
        """Create an execution plan for a user request.
        
        This is the main entry point. Given a user request and repository
        graphs, returns a complete structured plan for downstream agents.
        
        Args:
            request: User's code modification request
            repository_index: RepositoryIndex instance
            dependency_graph: DependencyGraph instance
            relationship_graph: RelationshipGraph instance
            
        Returns:
            Plan object with full analysis and execution steps
        """
        return create_plan(
            request,
            repository_index,
            dependency_graph,
            relationship_graph,
            config=self.config,
            debug=self.debug,
        )
    
    def plan_to_dict(self, plan: Plan) -> Dict[str, Any]:
        """Convert plan to dictionary for serialization."""
        return plan.to_dict()
    
    def plan_to_json(self, plan: Plan) -> str:
        """Convert plan to JSON string."""
        return json.dumps(self.plan_to_dict(plan), indent=2, default=str)


# Public API

def create_planner(config: Optional[PlannerConfig] = None, debug: bool = False) -> PlannerAgent:
    """Factory function to create a Planner Agent."""
    return PlannerAgent(config=config, debug=debug)


def plan_code_operation(
    request: str,
    repository_index: Any,
    dependency_graph: Any,
    relationship_graph: Any,
    config: Optional[PlannerConfig] = None,
    debug: bool = False,
) -> Plan:
    """Create an execution plan for a code operation.
    
    Convenience function for one-off planning without creating an agent.
    """
    planner = create_planner(config=config, debug=debug)
    return planner.plan(
        request,
        repository_index,
        dependency_graph,
        relationship_graph,
    )


__all__ = [
    "PlannerAgent",
    "create_planner",
    "plan_code_operation",
]