import unittest

from core.context_builder import build_context
from core.graph import build_graph
from core.indexer import IndexedFile, RepositoryIndex
from core.relationship import RelationshipBuilder


class TestContextBuilder(unittest.TestCase):

    def setUp(self):
        self.index = RepositoryIndex(files=[
            IndexedFile(
                path="app.py",
                language="Python",
                size=0,
                lines=0,
                imports=["flask"],
                functions=["login_handler"],
                classes=[],
                exports=["login_handler"],
                selectors=[],
                ids=[],
                css_classes=[],
                variables=[],
                animations=[],
                media_queries=[],
                elements=[],
                calls=[],
                dom_references=[],
                class_ops=[],
            ),
        ])
        self.graph = build_graph(self.index)
        self.relationships = RelationshipBuilder(self.index).build()

    def test_build_context_contains_expected_keys(self):
        context = build_context("Rename the login handler", self.index, self.graph, self.relationships)
        self.assertEqual(context["request"], "Rename the login handler")
        self.assertIn("repository_profile", context)
        self.assertIn("symbols", context)
        self.assertIn("definitions", context)
        self.assertIn("references", context)
        self.assertIn("owners", context)
        self.assertIn("dependency_tree", context)
        self.assertIn("impact_analysis", context)
        self.assertIn("query_history", context)
        self.assertIn("repository_context", context)
        self.assertIn("estimated_context_tokens", context["repository_context"])

    def test_build_context_finds_symbol_by_request(self):
        context = build_context("Rename the login handler", self.index, self.graph, self.relationships)
        self.assertTrue(any(symbol["symbol"] == "login_handler" for symbol in context["symbols"]))
        self.assertTrue(any("app.py" in owner for owner in context["owners"]))
