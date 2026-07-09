import unittest

from core.graph import build_graph
from core.indexer import IndexedFile, RepositoryIndex
from core.relationship import RelationshipGraph
from core import queries


class TestQueriesIntelligenceWrappers(unittest.TestCase):

    def setUp(self):
        self.index = RepositoryIndex(files=[
            IndexedFile(
                path="index.html",
                language="Html",
                size=0,
                lines=0,
                imports=[],
                functions=[],
                classes=[],
                exports=[],
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
            IndexedFile(
                path="app.py",
                language="Python",
                size=0,
                lines=0,
                imports=["flask"],
                functions=["create_app"],
                classes=[],
                exports=[],
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
        self.relationships = RelationshipGraph()

    def test_detect_architecture_wrapper(self):
        result = queries.detect_architecture(self.index, self.graph, self.relationships)
        self.assertIsInstance(result, dict)
        self.assertIn("architecture", result)
        self.assertIn("confidence", result)
        self.assertIn("evidence", result)

    def test_detect_frameworks_wrapper(self):
        result = queries.detect_frameworks(self.index, self.graph, self.relationships)
        self.assertIsInstance(result, dict)
        self.assertIn("Flask", result)
        self.assertGreater(result["Flask"]["confidence"], 0.0)

    def test_build_repository_profile_wrapper(self):
        profile = queries.build_repository_profile(self.index, self.graph, self.relationships)
        self.assertIsInstance(profile, dict)
        self.assertIn("summary", profile)
        self.assertIn("structure", profile)
        self.assertIn("frameworks", profile)
        self.assertIn("components", profile)
        self.assertIn("entry_points", profile["summary"])
        self.assertEqual(profile["frameworks"].get("Flask", {}).get("confidence", 0.0) > 0, True)
