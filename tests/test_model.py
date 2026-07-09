import unittest
from unittest.mock import Mock, patch

from core.model import ModelConfig, OllamaClient


class TestOllamaClient(unittest.TestCase):

    @patch("core.model.requests.Session")
    def test_generate_returns_response_text(self, mock_session_class):
        mock_session = mock_session_class.return_value
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"response": "hello world"}
        mock_session.post.return_value = mock_response

        client = OllamaClient(model="test-model", base_url="http://localhost:11434", retries=1)
        result = client.generate("Hello")

        self.assertEqual(result, "hello world")
        mock_session.post.assert_called_once()

    @patch("core.model.requests.Session")
    def test_generate_with_stats_includes_metadata(self, mock_session_class):
        mock_session = mock_session_class.return_value
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "response": "hello world",
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "finish_reason": "stop"},
        }
        mock_session.post.return_value = mock_response

        client = OllamaClient(model="test-model", base_url="http://localhost:11434", retries=1)
        result = client.generate_with_stats("Hello")

        self.assertEqual(result["response"], "hello world")
        self.assertEqual(result["tokens_input"], 5)
        self.assertEqual(result["tokens_output"], 3)
        self.assertEqual(result["finish_reason"], "stop")

    @patch("core.model.requests.Session")
    def test_stream_yields_response_chunks(self, mock_session_class):
        mock_session = mock_session_class.return_value
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.iter_lines.return_value = [b'{"response": "hello"}', b'{"response": " world"}']
        mock_session.post.return_value = mock_response

        client = OllamaClient(model="test-model", base_url="http://localhost:11434", retries=1)
        stream = client.stream("Hello")

        self.assertEqual(list(stream), ["hello", " world"])
        mock_session.post.assert_called_once()

    @patch("core.model.requests.Session")
    def test_ping_returns_true_when_available(self, mock_session_class):
        mock_session = mock_session_class.return_value
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = OllamaClient(model="test-model", base_url="http://localhost:11434", retries=1)
        self.assertTrue(client.ping())

    @patch("core.model.requests.Session")
    def test_list_models_returns_names(self, mock_session_class):
        mock_session = mock_session_class.return_value
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = ["qwen2.5-coder:14b"]
        mock_session.get.return_value = mock_response

        client = OllamaClient(model="test-model", base_url="http://localhost:11434", retries=1)
        self.assertEqual(client.list_models(), ["qwen2.5-coder:14b"])

    def test_config_class_to_payload(self):
        config = ModelConfig(model="test-model", top_p=0.9, top_k=40, repeat_penalty=1.1)
        payload = config.to_payload("Hello", stream=False)

        self.assertEqual(payload["model"], "test-model")
        self.assertEqual(payload["top_p"], 0.9)
        self.assertEqual(payload["top_k"], 40)
        self.assertEqual(payload["repeat_penalty"], 1.1)
