from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Generator, List, Optional, Sequence

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass
class ModelConfig:
    model: str = "qwen2.5-coder:14b"
    base_url: str = "http://localhost:11434"
    system_prompt: Optional[str] = None
    temperature: float = 0.7
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    repeat_penalty: Optional[float] = None
    max_tokens: int = 1024
    timeout: float = 30.0
    retries: int = 3
    retry_backoff: float = 1.0
    keep_alive: bool = True
    context_window: Optional[int] = None

    def to_payload(self, prompt: str, stream: bool = False) -> Dict[str, Any]:
        text = prompt.strip()
        if self.system_prompt:
            text = f"{self.system_prompt.strip()}\n\n{text}"

        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": text,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": stream,
        }
        if self.top_p is not None:
            payload["top_p"] = self.top_p
        if self.top_k is not None:
            payload["top_k"] = self.top_k
        if self.repeat_penalty is not None:
            payload["repeat_penalty"] = self.repeat_penalty
        if self.context_window is not None:
            payload["context_window"] = self.context_window
        return payload


@dataclass
class ModelResult:
    response: str
    tokens_input: Optional[int]
    tokens_output: Optional[int]
    latency_ms: float
    finish_reason: Optional[str]
    model: str
    raw: Any

    def to_dict(self) -> Dict[str, Any]:
        return {
            "response": self.response,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "latency_ms": self.latency_ms,
            "finish_reason": self.finish_reason,
            "model": self.model,
            "raw": self.raw,
        }


class OllamaClient:
    """Production-grade Ollama client for repository-aware AI.

    Responsibilities:
      - connection management and health checks
      - model discovery and validation
      - generation, streaming, chat
      - result metadata and statistics
      - robust error handling
    """

    def __init__(
        self,
        config: Optional[ModelConfig] = None,
        **overrides: Any,
    ) -> None:
        if config is not None:
            self.config = config
            if overrides:
                raise ValueError("Cannot pass overrides when config is provided.")
        else:
            self.config = ModelConfig(**overrides)
        self.base_url = self.config.base_url.rstrip("/")
        self._session: Optional[requests.Session] = None

    def _get_session(self) -> requests.Session:
        if self._session is not None:
            return self._session

        session = requests.Session()
        if self.config.keep_alive:
            session.headers.update({"Connection": "keep-alive"})

        try:
            retry = Retry(
                total=self.config.retries,
                backoff_factor=self.config.retry_backoff,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=frozenset(["POST", "GET"]),
            )
        except TypeError:
            retry = Retry(
                total=self.config.retries,
                backoff_factor=self.config.retry_backoff,
                status_forcelist=[429, 500, 502, 503, 504],
                method_whitelist=frozenset(["POST", "GET"]),
            )

        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        self._session = session
        return self._session

    def _request(
        self,
        endpoint: str,
        payload: Optional[Dict[str, Any]] = None,
        stream: bool = False,
        timeout: Optional[float] = None,
        method: str = "POST",
    ) -> requests.Response:
        url = f"{self.base_url}{endpoint}"
        session = self._get_session()
        timeout = timeout if timeout is not None else self.config.timeout

        if method.upper() == "GET":
            response = session.get(url, timeout=timeout)
        else:
            response = session.post(url, json=payload or {}, timeout=timeout, stream=stream)
        response.raise_for_status()
        return response

    def _parse_response_body(self, response: requests.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return response.text

    def _extract_stats(self, payload: Any, latency_ms: float) -> Dict[str, Any]:
        tokens_input = None
        tokens_output = None
        finish_reason = None

        if isinstance(payload, dict):
            usage = payload.get("usage") or payload.get("metadata") or {}
            if isinstance(usage, dict):
                tokens_input = usage.get("prompt_tokens") or usage.get("input_tokens") or usage.get("tokens_input")
                tokens_output = usage.get("completion_tokens") or usage.get("output_tokens") or usage.get("tokens_output")
                finish_reason = usage.get("finish_reason") or payload.get("finish_reason")
            if tokens_input is None and isinstance(payload.get("metadata"), dict):
                tokens_input = payload["metadata"].get("token_count")

        return {
            "tokens_input": int(tokens_input) if isinstance(tokens_input, (int, float)) else None,
            "tokens_output": int(tokens_output) if isinstance(tokens_output, (int, float)) else None,
            "latency_ms": latency_ms,
            "finish_reason": finish_reason,
            "model": self.config.model,
        }

    def _determine_text(self, payload: Any) -> str:
        if isinstance(payload, dict):
            if "response" in payload:
                return str(payload["response"])
            if "output" in payload:
                return str(payload["output"])
            if "text" in payload:
                return str(payload["text"])
            if "results" in payload and isinstance(payload["results"], list):
                parts: List[str] = []
                for item in payload["results"]:
                    if isinstance(item, dict):
                        text_item = item.get("response") or item.get("output") or item.get("text")
                        if text_item:
                            parts.append(str(text_item))
                    else:
                        parts.append(str(item))
                return "".join(parts)
            return json.dumps(payload)
        return str(payload)

    def _make_prompt_payload(self, prompt: str, stream: bool = False) -> Dict[str, Any]:
        return self.config.to_payload(prompt, stream=stream)

    def generate_with_stats(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        payload = self._make_prompt_payload(prompt, stream=False)
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        start = time.monotonic()
        try:
            response = self._request("/api/generate", payload=payload, timeout=timeout, stream=False)
            body = self._parse_response_body(response)
            elapsed = (time.monotonic() - start) * 1000.0
            stats = self._extract_stats(body, elapsed)
            result = ModelResult(
                response=self._determine_text(body),
                tokens_input=stats["tokens_input"],
                tokens_output=stats["tokens_output"],
                latency_ms=stats["latency_ms"],
                finish_reason=stats["finish_reason"],
                model=stats["model"],
                raw=body,
            )
            return result.to_dict()
        except requests.RequestException as exc:
            raise RuntimeError(f"Model generation failed: {exc}") from exc

    def generate(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> str:
        return self.generate_with_stats(prompt, temperature=temperature, max_tokens=max_tokens, timeout=timeout)["response"]

    def stream(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> Generator[str, None, None]:
        payload = self._make_prompt_payload(prompt, stream=True)
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        response = self._request("/api/generate", payload=payload, stream=True, timeout=timeout)

        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            chunk = raw_line.strip()
            try:
                event = json.loads(chunk)
                if isinstance(event, dict):
                    if "response" in event:
                        yield str(event["response"])
                        continue
                    if "output" in event:
                        yield str(event["output"])
                        continue
                    if "text" in event:
                        yield str(event["text"])
                        continue
                yield chunk
            except ValueError:
                yield chunk

    def chat(
        self,
        messages: Sequence[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> str:
        prompt_segments: List[str] = []
        for message in messages:
            role = message.get("role", "user").strip().lower()
            content = message.get("content", "")
            prompt_segments.append(f"[{role}] {content}")
        prompt = "\n".join(prompt_segments)
        return self.generate(prompt, temperature=temperature, max_tokens=max_tokens, timeout=timeout)

    def complete_json(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        text = self.generate(prompt, temperature=temperature, max_tokens=max_tokens, timeout=timeout)
        try:
            return json.loads(text)
        except ValueError as exc:
            raise ValueError(f"Response is not valid JSON: {text}") from exc

    def ping(self, timeout: Optional[float] = None) -> bool:
        try:
            response = self._request("/api/ping", payload=None, timeout=timeout, method="GET")
            return response.status_code == 200
        except requests.RequestException:
            return False

    def list_models(self, timeout: Optional[float] = None) -> List[str]:
        try:
            response = self._request("/api/models", payload=None, timeout=timeout, method="GET")
            payload = self._parse_response_body(response)
            if isinstance(payload, list):
                return [str(item) for item in payload]
            if isinstance(payload, dict):
                if "models" in payload and isinstance(payload["models"], list):
                    return [str(item.get("name", item)) if isinstance(item, dict) else str(item) for item in payload["models"]]
                return [str(item) for item in payload.values()]
        except requests.RequestException:
            pass
        return []

    def model_info(self, timeout: Optional[float] = None) -> Dict[str, Any]:
        models = self.list_models(timeout=timeout)
        available = self.config.model in models
        return {
            "model": self.config.model,
            "available": available,
            "source": self.base_url,
            "models": models,
        }

    def available(self, timeout: Optional[float] = None) -> bool:
        return self.ping(timeout=timeout)