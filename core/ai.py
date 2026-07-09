from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.context_builder import build_context
from core.logger import log_ai_event
from core.model import ModelConfig, OllamaClient
from core.prompt_builder import build_prompt


def generate_response(
    request: str,
    repository_index: Any,
    dependency_graph: Any,
    relationship_graph: Any,
    model_config: Optional[Dict[str, Any]] = None,
    return_dict: bool = False,
    prompt_mode: str = "coder",
    prompt_output_format: str = "text",
    prompt_max_length: Optional[int] = None,
    debug: bool = False,
    log_request: bool = True,
) -> Any:
    """Generate an AI response for a user request.

    This orchestrator is intentionally thin: it builds context, builds a prompt,
    and delegates generation to the model client.
    """
    context = build_context(request, repository_index, dependency_graph, relationship_graph)
    prompt, prompt_stats = build_prompt(
        request,
        context,
        mode=prompt_mode,
        output_format=prompt_output_format,
        max_length=prompt_max_length,
        return_stats=True,
    )

    if isinstance(model_config, ModelConfig):
        client = OllamaClient(config=model_config)
    else:
        client = OllamaClient(**(model_config or {}))

    result = client.generate_with_stats(prompt)
    model_stats = {k: v for k, v in result.items() if k != "response"}
    response_text = result["response"]

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request": request,
        "prompt_mode": prompt_mode,
        "prompt_output_format": prompt_output_format,
        "model_config": {
            "model": client.config.model,
            "base_url": client.config.base_url,
            "temperature": client.config.temperature,
            "max_tokens": client.config.max_tokens,
        },
        "query_history": context.get("query_history", []),
        "repository_profile": context.get("repository_profile"),
        "context_summary": context.get("repository_context"),
        "prompt_stats": prompt_stats,
        "model_stats": model_stats,
        "response": response_text,
    }

    log_path = None
    if log_request:
        try:
            log_path = log_ai_event(log_entry)
        except Exception:
            log_path = None

    if debug:
        debug_result = {
            "request": request,
            "context": context,
            "prompt": prompt,
            "prompt_stats": prompt_stats,
            "model_stats": model_stats,
            "response": response_text,
            "log_path": log_path,
        }
        return debug_result

    if return_dict:
        response_data = {"response": response_text}
        response_data.update(model_stats)
        if log_path:
            response_data["log_path"] = log_path
        return response_data

    return response_text


def stream_response(
    request: str,
    repository_index: Any,
    dependency_graph: Any,
    relationship_graph: Any,
    model_config: Optional[Dict[str, Any]] = None,
    prompt_mode: str = "coder",
    prompt_output_format: str = "text",
    prompt_max_length: Optional[int] = None,
):
    context = build_context(request, repository_index, dependency_graph, relationship_graph)
    prompt = build_prompt(
        request,
        context,
        mode=prompt_mode,
        output_format=prompt_output_format,
        max_length=prompt_max_length,
    )

    if isinstance(model_config, ModelConfig):
        client = OllamaClient(config=model_config)
    else:
        client = OllamaClient(**(model_config or {}))

    return client.stream(prompt)


if __name__ == "__main__":
    print(
        "core.ai is an orchestrator for AI generation. "
        "Use generate_response(request, repository_index, dependency_graph, relationship_graph, model_config)"
    )
