"""AI Planner Agent for AutoDevAI.

The Planner is the first agent in the AI pipeline. It:
- Understands user requests
- Classifies intent
- Analyzes repository impact
- Estimates risk and complexity
- Generates ordered execution plans

The Planner ONLY plans; it never modifies code, files, or repositories.

Output is strictly structured data (Plan objects) suitable for downstream
agents (Coder, Tester, Reviewer, Committer) to execute.

Architecture:
- Uses ONLY core.queries.* for repository knowledge
- Never accesses graphs directly
- Never imports reasoning modules directly
- Never calls model/Ollama directly
- All reasoning is modular, testable, and extensible
"""

from __future__ import annotations

from typing import Any, Optional, Dict
import json

from agents.planner_models import Plan, PlanningContext
from agents.planner_executor import create_plan
from agents.planner_prompts import get_system_prompt


class PlannerAgent:
    """Main Planner Agent class.
    
    Orchestrates planning for code modification requests. Public interface
    for creating structured execution plans.
    """
    
    def __init__(self, debug: bool = False):
        """Initialize the Planner Agent.
        
        Args:
            debug: Enable debug output
        """
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
            debug=self.debug,
        )
    
    def plan_to_dict(self, plan: Plan) -> Dict[str, Any]:
        """Convert plan to dictionary for serialization.
        
        Args:
            plan: Plan object
            
        Returns:
            JSON-serializable dictionary
        """
        return plan.to_dict()
    
    def plan_to_json(self, plan: Plan) -> str:
        """Convert plan to JSON string.
        
        Args:
            plan: Plan object
            
        Returns:
            JSON string representation
        """
        return json.dumps(self.plan_to_dict(plan), indent=2, default=str)


# Public API

def create_planner(debug: bool = False) -> PlannerAgent:
    """Factory function to create a Planner Agent.
    
    Args:
        debug: Enable debug output
        
    Returns:
        Initialized PlannerAgent instance
    """
    return PlannerAgent(debug=debug)


def plan_code_operation(
    request: str,
    repository_index: Any,
    dependency_graph: Any,
    relationship_graph: Any,
    debug: bool = False,
) -> Plan:
    """Create an execution plan for a code operation.
    
    Convenience function for one-off planning without creating an agent.
    
    Args:
        request: User's code modification request
        repository_index: RepositoryIndex instance
        dependency_graph: DependencyGraph instance
        relationship_graph: RelationshipGraph instance
        debug: Enable debug output
        
    Returns:
        Plan object with full analysis and execution steps
    """
    planner = create_planner(debug=debug)
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