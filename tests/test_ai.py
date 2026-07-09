import unittest
from unittest.mock import Mock, patch

from core.ai import generate_response
from core.graph import build_graph
from core.indexer import IndexedFile, RepositoryIndex
from core.relationship import RelationshipBuilder


class TestAIOrchestrator(unittest.TestCase):

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

    @patch("core.ai.OllamaClient.generate_with_stats")
    def test_generate_response_calls_model(self, mock_generate_with_stats):
        mock_generate_with_stats.return_value = {"response": "response text"}
        response = generate_response(
            "Rename the login handler",
            self.index,
            self.graph,
            self.relationships,
            model_config={"model": "test-model", "base_url": "http://localhost:11434"},
        )

        self.assertEqual(response, "response text")
        mock_generate_with_stats.assert_called_once()

    @patch("core.ai.OllamaClient.generate_with_stats")
    def test_generate_response_returns_dict_when_requested(self, mock_generate_with_stats):
        mock_generate_with_stats.return_value = {"response": "response text", "tokens_input": 10}
        result = generate_response(
            "Rename the login handler",
            self.index,
            self.graph,
            self.relationships,
            model_config={"model": "test-model", "base_url": "http://localhost:11434"},
            return_dict=True,
        )
 
        self.assertIsInstance(result, dict)
        self.assertEqual(result["response"], "response text")

    @patch("core.ai.OllamaClient.generate_with_stats")
    def test_generate_response_debug_returns_prompt_and_context(self, mock_generate_with_stats):
        mock_generate_with_stats.return_value = {"response": "debug response", "tokens_input": 10, "tokens_output": 2}
        result = generate_response(
            "Rename the login handler",
            self.index,
            self.graph,
            self.relationships,
            model_config={"model": "test-model", "base_url": "http://localhost:11434"},
            debug=True,
            log_request=False,
        )

        self.assertIsInstance(result, dict)
        self.assertEqual(result["response"], "debug response")
        self.assertIn("prompt", result)
        self.assertIn("context", result)
        self.assertIn("prompt_stats", result)
        self.assertIn("model_stats", result)
