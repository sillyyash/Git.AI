import unittest

from core.prompt_builder import build_prompt


class TestPromptBuilder(unittest.TestCase):

    def test_build_prompt_includes_request_and_context(self):
        context = {
            "request": "Rename the login handler",
            "repository_profile": {"framework": "Flask", "architecture": "MVC"},
            "symbols": [{"symbol": "login_handler", "kind": "function", "file": "app.py"}],
            "definitions": [{"symbol": "login_handler", "file": "app.py", "kind": "function"}],
            "references": [],
            "owners": ["app.py"],
            "components": [],
            "dependency_tree": {},
            "impact_analysis": {},
            "related_files": [],
        }
        prompt = build_prompt("Rename the login handler", context)

        self.assertIn("Rename the login handler", prompt)
        self.assertIn("Repository summary", prompt)
        self.assertIn("Flask", prompt)
        self.assertIn("login_handler", prompt)

    def test_build_prompt_respects_mode_and_output_format(self):
        context = {
            "request": "Rename the login handler",
            "repository_profile": {"framework": "Flask"},
            "symbols": [],
            "definitions": [],
            "references": [],
            "owners": [],
            "components": [],
            "dependency_tree": {},
            "impact_analysis": {},
            "related_files": [],
        }
        prompt = build_prompt("Rename the login handler", context, mode="planner", output_format="json")
 
        self.assertIn("Mode: planner", prompt)
        self.assertIn("valid JSON only", prompt)
        self.assertIn("Repository summary", prompt)

    def test_build_prompt_returns_stats(self):
        context = {
            "request": "Rename the login handler",
            "repository_profile": {"framework": "Flask"},
            "symbols": [],
            "definitions": [],
            "references": [],
            "owners": [],
            "components": [],
            "dependency_tree": {},
            "impact_analysis": {},
            "related_files": [],
        }
        prompt, stats = build_prompt("Rename the login handler", context, return_stats=True)
 
        self.assertIsInstance(prompt, str)
        self.assertIsInstance(stats, dict)
        self.assertEqual(stats["mode"], "coder")
        self.assertEqual(stats["output_format"], "text")
        self.assertGreater(stats["length_chars"], 0)
