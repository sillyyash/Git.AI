import unittest

from core.graph import build_graph
from core.indexer import IndexedFile, RepositoryIndex
from core.relationship import RelationshipGraph
from core import intelligence


class TestIntelligenceDetectors(unittest.TestCase):

    def setUp(self):
        self.index = RepositoryIndex(files=[
            IndexedFile(
                path="app.py",
                language="Python",
                size=0,
                lines=0,
                imports=["flask"],
                functions=["create_app"],
                classes=["App"],
                exports=["create_app"],
                selectors=[],
                ids=[],
                css_classes=[],
                variables=[],
                animations=[],
                media_queries=[],
                elements=[],
                calls=[{"callee": "app.route", "caller": "create_app"}],
                dom_references=[],
                class_ops=[],
            ),
            IndexedFile(
                path="index.html",
                language="Html",
                size=0,
                lines=0,
                imports=[],
                functions=[],
                classes=[],
                exports=[],
                selectors=["#root"],
                ids=["root"],
                css_classes=["hero"],
                variables=[],
                animations=[],
                media_queries=[],
                elements=[{"tag": "div", "id": "root", "classes": ["hero"], "attrs": {}}],
                calls=[],
                dom_references=[],
                class_ops=[],
            ),
        ])
        self.graph = build_graph(self.index)
        self.relationships = RelationshipGraph()

    def test_detect_frameworks(self):
        frameworks = intelligence.detect_frameworks(self.index, self.graph, self.relationships)
        self.assertIn("Flask", frameworks)
        self.assertGreaterEqual(frameworks["Flask"]["confidence"], 0.9)

    def test_detect_entry_points(self):
        entries = intelligence.detect_entry_points(self.index, self.graph, self.relationships)
        self.assertTrue(any(entry["file"] == "app.py" for entry in entries))

    def test_build_repository_profile(self):
        profile = intelligence.build_repository_profile(self.index, self.graph, self.relationships)
        self.assertIsInstance(profile, dict)
        self.assertIn("summary", profile)
        self.assertEqual(profile["summary"]["framework"], "Flask")
        self.assertIn("deployment", profile)
        self.assertIsInstance(profile["structure"], dict)
