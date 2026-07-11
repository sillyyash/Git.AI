"""Integration tests for the Planner Agent.

Demonstrates the Planner Agent's capabilities and usage patterns.
Tests intent classification, impact analysis, risk/complexity estimation,
and execution plan generation.
"""

import unittest
import json
from unittest.mock import Mock, MagicMock

from agents.planner_models import (
    Intent,
    Risk,
    Complexity,
    Plan,
    Symbol,
    ExecutionStep,
    IntentClassificationResult,
)
from agents.planner_rules import (
    classify_intent,
    estimate_risk,
    estimate_complexity,
)
from agents.planner import (
    PlannerAgent,
    create_planner,
    plan_code_operation,
)
from agents.planner_executor import (
    detect_intent,
    gather_repository_context,
    analyze_impact,
    assess_risk,
    estimate_operation_complexity,
    generate_execution_plan,
)


class TestIntentClassification(unittest.TestCase):
    """Test intent classification from user requests."""
    
    def test_classify_rename_intent(self):
        """Test classification of rename operations."""
        request = "rename the function calculateTotal to computeSum"
        result = classify_intent(request)
        
        self.assertEqual(result.intent, Intent.RENAME)
        self.assertGreater(result.confidence, 0.2)
        self.assertTrue(any("rename" in k for k in result.keywords))
    
    def test_classify_refactor_intent(self):
        """Test classification of refactor operations."""
        request = "refactor the authentication module to use middleware pattern"
        result = classify_intent(request)
        
        self.assertEqual(result.intent, Intent.REFACTOR)
        self.assertGreater(result.confidence, 0.1)
    
    def test_classify_feature_intent(self):
        """Test classification of feature addition."""
        request = "add dark mode support to the UI"
        result = classify_intent(request)
        
        self.assertEqual(result.intent, Intent.FEATURE)
        self.assertGreater(result.confidence, 0.1)
    
    def test_classify_bug_intent(self):
        """Test classification of bug fix."""
        request = "fix the bug where login crashes on invalid email"
        result = classify_intent(request)
        
        self.assertEqual(result.intent, Intent.BUG)
        self.assertGreater(result.confidence, 0.1)
    
    def test_classify_test_intent(self):
        """Test classification of testing operations."""
        request = "write unit tests for the payment module"
        result = classify_intent(request)
        
        self.assertEqual(result.intent, Intent.TEST)
        self.assertGreater(result.confidence, 0.1)
    
    def test_classify_explain_intent(self):
        """Test classification of explain/help requests."""
        request = "help me understand how the caching layer works"
        result = classify_intent(request)
        
        self.assertEqual(result.intent, Intent.EXPLAIN)
        self.assertGreater(result.confidence, 0.1)
    
    def test_unknown_intent(self):
        """Test classification of unclear requests."""
        request = "xyzzy qwerty asdf"
        result = classify_intent(request)
        
        self.assertEqual(result.intent, Intent.UNKNOWN)
        self.assertEqual(result.confidence, 0.0)


class TestRiskEstimation(unittest.TestCase):
    """Test risk estimation heuristics."""
    
    def test_low_risk_rename(self):
        """Test low-risk rename estimation."""
        risk = estimate_risk(
            intent=Intent.RENAME,
            affected_file_count=1,
            affected_symbol_count=1,
            dependency_count=0,
            has_test_coverage=True,
            is_critical_path=False,
        )
        
        self.assertEqual(risk, Risk.LOW)
    
    def test_high_risk_delete(self):
        """Test high-risk delete estimation."""
        risk = estimate_risk(
            intent=Intent.DELETE,
            affected_file_count=15,
            affected_symbol_count=50,
            dependency_count=100,
            has_test_coverage=False,
            is_critical_path=True,
        )
        
        self.assertEqual(risk, Risk.HIGH)
    
    def test_medium_risk_refactor(self):
        """Test medium-risk refactor estimation."""
        risk = estimate_risk(
            intent=Intent.REFACTOR,
            affected_file_count=5,
            affected_symbol_count=10,
            dependency_count=20,
            has_test_coverage=True,
            is_critical_path=False,
        )
        
        self.assertEqual(risk, Risk.MEDIUM)


class TestComplexityEstimation(unittest.TestCase):
    """Test complexity estimation heuristics."""
    
    def test_trivial_complexity(self):
        """Test trivial complexity estimation."""
        complexity = estimate_complexity(
            intent=Intent.DOCS,
            affected_file_count=1,
            affected_symbol_count=1,
            dependency_depth=0,
            has_circular_dependencies=False,
            requires_data_migration=False,
        )
        
        self.assertEqual(complexity, Complexity.TRIVIAL)
    
    def test_small_complexity(self):
        """Test small complexity estimation."""
        complexity = estimate_complexity(
            intent=Intent.RENAME,
            affected_file_count=2,
            affected_symbol_count=5,
            dependency_depth=2,
            has_circular_dependencies=False,
            requires_data_migration=False,
        )
        
        self.assertEqual(complexity, Complexity.SMALL)
    
    def test_large_complexity(self):
        """Test large complexity estimation."""
        complexity = estimate_complexity(
            intent=Intent.REFACTOR,
            affected_file_count=20,
            affected_symbol_count=50,
            dependency_depth=15,
            has_circular_dependencies=True,
            requires_data_migration=True,
        )
        
        self.assertEqual(complexity, Complexity.LARGE)


class TestPlannerAgent(unittest.TestCase):
    """Test the main PlannerAgent class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.planner = create_planner(debug=False)
        
        # Create mock graphs
        self.mock_index = Mock()
        self.mock_index.files = []
        
        self.mock_dep_graph = Mock()
        self.mock_dep_graph.imports = {}
        self.mock_dep_graph.reverse_imports = {}
        self.mock_dep_graph.functions = {}
        self.mock_dep_graph.classes = {}
        self.mock_dep_graph.selectors = {}
        self.mock_dep_graph.css_classes = {}
        self.mock_dep_graph.ids = {}
        self.mock_dep_graph.variables = {}
        
        self.mock_rel_graph = Mock()
        self.mock_rel_graph.by_target = Mock(return_value=[])
        self.mock_rel_graph.by_source = Mock(return_value=[])
        self.mock_rel_graph.by_file = Mock(return_value=[])
        self.mock_rel_graph.by_relation = Mock(return_value=[])
    
    def test_planner_creation(self):
        """Test planner agent creation."""
        planner = create_planner(debug=False)
        self.assertIsNotNone(planner)
        self.assertFalse(planner.debug)
        
        planner_debug = create_planner(debug=True)
        self.assertTrue(planner_debug.debug)
    
    def test_plan_creation_structure(self):
        """Test that plan creation returns proper structure."""
        plan = self.planner.plan(
            "rename the calculateTotal function to computeSum",
            self.mock_index,
            self.mock_dep_graph,
            self.mock_rel_graph,
        )
        
        self.assertIsNotNone(plan)
        self.assertIsInstance(plan, Plan)
        self.assertIsNotNone(plan.intent)
        self.assertIsNotNone(plan.execution_steps)
        self.assertGreater(len(plan.execution_steps), 0)
    
    def test_plan_to_dict_conversion(self):
        """Test plan conversion to dictionary."""
        plan = self.planner.plan(
            "add a new feature",
            self.mock_index,
            self.mock_dep_graph,
            self.mock_rel_graph,
        )
        
        plan_dict = self.planner.plan_to_dict(plan)
        self.assertIsInstance(plan_dict, dict)
        self.assertIn("intent", plan_dict)
        self.assertIn("execution_steps", plan_dict)
        self.assertIn("risk", plan_dict)
        self.assertIn("complexity", plan_dict)
    
    def test_plan_to_json_conversion(self):
        """Test plan conversion to JSON string."""
        plan = self.planner.plan(
            "fix a bug in the auth module",
            self.mock_index,
            self.mock_dep_graph,
            self.mock_rel_graph,
        )
        
        plan_json = self.planner.plan_to_json(plan)
        self.assertIsInstance(plan_json, str)
        
        # Verify it's valid JSON
        parsed = json.loads(plan_json)
        self.assertIsNotNone(parsed)
        self.assertIn("intent", parsed)


class TestExecutionPlanGeneration(unittest.TestCase):
    """Test execution plan generation for different intents."""
    
    def test_rename_execution_plan(self):
        """Test execution plan for rename operations."""
        steps = generate_execution_plan(
            intent=Intent.RENAME,
            request="rename calculateTotal to computeSum",
            affected_symbols=[Symbol(name="calculateTotal", kind="function")],
            affected_files=["utils.py"],
            dependencies={"utils.py": []},
            risk=Risk.LOW,
            complexity=Complexity.SMALL,
        )
        
        self.assertGreater(len(steps), 0)
        
        # Should have locate, analyze, prepare, test, review, commit steps
        action_types = {step.action for step in steps}
        self.assertIn("locate_affected_symbols", action_types)
        self.assertIn("prepare_refactoring", action_types)
        self.assertIn("run_tests", action_types)
        self.assertIn("review_code", action_types)
    
    def test_feature_execution_plan(self):
        """Test execution plan for feature addition."""
        steps = generate_execution_plan(
            intent=Intent.FEATURE,
            request="add dark mode support",
            affected_symbols=[],
            affected_files=["ui/theme.py", "ui/components.py"],
            dependencies={},
            risk=Risk.MEDIUM,
            complexity=Complexity.MEDIUM,
        )
        
        self.assertGreater(len(steps), 0)
        
        action_types = {step.action for step in steps}
        self.assertIn("scaffold_feature", action_types)
    
    def test_bug_fix_execution_plan(self):
        """Test execution plan for bug fixes."""
        steps = generate_execution_plan(
            intent=Intent.BUG,
            request="fix login crash on invalid email",
            affected_symbols=[Symbol(name="validateEmail", kind="function")],
            affected_files=["auth.py"],
            dependencies={},
            risk=Risk.MEDIUM,
            complexity=Complexity.SMALL,
        )
        
        self.assertGreater(len(steps), 0)
        
        action_types = {step.action for step in steps}
        self.assertIn("prepare_bugfix", action_types)
    
    def test_execution_steps_have_dependencies(self):
        """Test that execution steps have proper dependencies."""
        steps = generate_execution_plan(
            intent=Intent.REFACTOR,
            request="refactor auth module",
            affected_symbols=[],
            affected_files=["auth.py"],
            dependencies={},
            risk=Risk.MEDIUM,
            complexity=Complexity.MEDIUM,
        )
        
        # Steps should have ordered dependencies
        # First step should have no dependencies
        first_step = steps[0]
        self.assertEqual(len(first_step.depends_on), 0)
        
        # Later steps should depend on earlier ones
        for step in steps[1:]:
            # Each step should either have dependencies or be independent
            self.assertIsNotNone(step.depends_on)


class TestPlannerModels(unittest.TestCase):
    """Test data models."""
    
    def test_symbol_creation(self):
        """Test Symbol dataclass."""
        sym = Symbol(
            name="calculateTotal",
            kind="function",
            file="utils.py",
            line=42,
        )
        
        self.assertEqual(sym.name, "calculateTotal")
        self.assertEqual(sym.kind, "function")
        self.assertEqual(sym.file, "utils.py")
        self.assertEqual(sym.line, 42)
    
    def test_execution_step_creation(self):
        """Test ExecutionStep dataclass."""
        step = ExecutionStep(
            id="step_1",
            order=1,
            agent="coder",
            action="update_imports",
            description="Update imports after rename",
            affected_files=["utils.py"],
        )
        
        self.assertEqual(step.id, "step_1")
        self.assertEqual(step.agent, "coder")
        self.assertEqual(len(step.affected_files), 1)
    
    def test_plan_creation(self):
        """Test Plan dataclass."""
        plan = Plan(
            intent=Intent.RENAME,
            request="rename foo to bar",
            summary="Rename function foo",
            reasoning="Simple rename operation",
            risk=Risk.LOW,
            complexity=Complexity.SMALL,
        )
        
        self.assertEqual(plan.intent, Intent.RENAME)
        self.assertEqual(plan.risk, Risk.LOW)
        self.assertEqual(plan.complexity, Complexity.SMALL)
        self.assertEqual(plan.status, "created")


class TestIntegration(unittest.TestCase):
    """Integration tests for complete planning pipeline."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.planner = create_planner(debug=True)
        
        # Create realistic mock graphs
        self.mock_index = Mock()
        self.mock_index.files = []
        
        self.mock_dep_graph = Mock()
        self.mock_dep_graph.imports = {
            "app.py": ["auth.py", "utils.py"],
            "auth.py": ["utils.py"],
        }
        self.mock_dep_graph.reverse_imports = {
            "utils.py": ["app.py", "auth.py"],
            "auth.py": ["app.py"],
        }
        self.mock_dep_graph.functions = {
            "login": "auth.py",
            "validateEmail": "auth.py",
        }
        self.mock_dep_graph.classes = {}
        self.mock_dep_graph.selectors = {}
        self.mock_dep_graph.css_classes = {}
        self.mock_dep_graph.ids = {}
        self.mock_dep_graph.variables = {}
        
        self.mock_rel_graph = Mock()
        self.mock_rel_graph.by_target = Mock(return_value=[])
        self.mock_rel_graph.by_source = Mock(return_value=[])
        self.mock_rel_graph.by_file = Mock(return_value=[])
        self.mock_rel_graph.by_relation = Mock(return_value=[])
    
    def test_complete_planning_pipeline(self):
        """Test complete planning pipeline from request to plan."""
        request = "rename the login function to authenticate"
        
        plan = self.planner.plan(
            request,
            self.mock_index,
            self.mock_dep_graph,
            self.mock_rel_graph,
        )
        
        # Verify plan structure
        self.assertIsNotNone(plan)
        self.assertEqual(plan.intent, Intent.RENAME)
        self.assertIn("rename", plan.summary.lower())
        self.assertGreater(len(plan.execution_steps), 0)
        
        # Verify execution steps
        for step in plan.execution_steps:
            self.assertIsNotNone(step.id)
            self.assertIsNotNone(step.agent)
            self.assertIsNotNone(step.action)
            self.assertIsNotNone(step.description)


if __name__ == "__main__":
    unittest.main()
