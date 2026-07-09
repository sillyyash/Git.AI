from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


SYSTEM_INSTRUCTIONS = (
    "You are a repository-aware AI assistant. Use only the repository context provided below to answer the user's request. "
    "Do not invent details that are not present in the context. If the request involves code changes, explain the affected files and related symbols."
)

MODE_PROMPTS = {
    "coder": "Generate code or design recommendations based on the repository context. Ensure the response is precise, actionable, and aligned with the user's request.",
    "planner": "Produce a high-level plan or analysis using the repository context. Focus on next steps, dependencies, and potential risks.",
    "reviewer": "Review the requested change in the context of the repository. Call out issues, inconsistencies, and suggestions without making unverified assumptions.",
    "tester": "Suggest tests, test cases, and validation steps that cover the requested change using the repository context.",
}

OUTPUT_INSTRUCTIONS = {
    "text": "Provide a concise, human-readable response.",
    "markdown": "Provide the response in Markdown format.",
    "json": "Return only valid JSON with no markdown or explanation outside the JSON object.",
    "patch": "Return a unified diff patch that makes the requested changes.",
    "diff": "Return a unified diff patch that makes the requested changes.",
}

SECTION_ORDER = [
    "Repository summary",
    "Request",
    "Relevant symbols",
    "Definitions",
    "References",
    "Owners",
    "Components",
    "Dependency tree",
    "Impact analysis",
    "Related files",
    "Instructions",
    "Output format",
]


def _render_bullets(title: str, items: List[Any]) -> str:
    if not items:
        return ""
    lines = [f"{title}:"]
    for item in items:
        if isinstance(item, dict):
            if "symbol" in item and "file" in item:
                lines.append(f"- {item.get('symbol')} ({item.get('kind')}) -> {item.get('file')}")
            else:
                lines.append(f"- {json.dumps(item, sort_keys=True)}")
        else:
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _render_summary(title: str, summary: Dict[str, Any]) -> str:
    if not summary:
        return ""
    lines = [f"{title}:"]
    for key, value in sorted(summary.items()):
        if isinstance(value, (str, int, float, bool)):
            lines.append(f"- {key}: {value}")
        else:
            lines.append(f"- {key}: {json.dumps(value, sort_keys=True)}")
    return "\n".join(lines) + "\n"


def _render_item_list(title: str, items: List[Dict[str, Any]]) -> str:
    if not items:
        return ""
    lines = [f"{title}:"]
    for item in items:
        if isinstance(item, dict):
            description = ", ".join(f"{k}={v}" for k, v in item.items() if k != "score")
            lines.append(f"- {description}")
        else:
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _render_dict(title: str, data: Dict[str, Any]) -> str:
    if not data:
        return ""
    try:
        content = json.dumps(data, indent=2, sort_keys=True)
        return f"{title}:\n{content}\n"
    except (TypeError, ValueError):
        return f"{title}: {data}\n"


def _truncate_prompt(prompt: str, max_length: int) -> str:
    if not max_length or len(prompt) <= max_length:
        return prompt
    return prompt[: max_length - 3].rstrip() + "..."


def _build_prompt_stats(prompt: str, mode: str, output_format: str) -> Dict[str, Any]:
    lines = prompt.splitlines()
    return {
        "mode": mode,
        "output_format": output_format,
        "length_chars": len(prompt),
        "length_lines": len(lines),
        "estimated_tokens": max(0, len(prompt) // 4),
    }


def build_prompt(
    request: str,
    context: Dict[str, Any],
    mode: str = "coder",
    output_format: str = "text",
    max_length: Optional[int] = None,
    return_stats: bool = False,
) -> Any:
    """Build an optimized prompt from the request and repository context."""
    mode = mode.lower()
    output_format = output_format.lower()

    instructions = MODE_PROMPTS.get(mode, MODE_PROMPTS["coder"])
    output_instructions = OUTPUT_INSTRUCTIONS.get(output_format, OUTPUT_INSTRUCTIONS["text"])

    sections: List[str] = [SYSTEM_INSTRUCTIONS, "", f"Mode: {mode}", instructions, "", "User request:", request, ""]

    summary = context.get("repository_profile") or {}
    if isinstance(summary, dict):
        sections.append(_render_summary("Repository summary", summary))

    symbols = context.get("symbols") or []
    if symbols:
        sections.append(_render_item_list("Relevant symbols", symbols[:10]))

    definitions = context.get("definitions") or []
    if definitions:
        sections.append(_render_item_list("Definitions", definitions[:8]))

    references = context.get("references") or []
    if references:
        sections.append(_render_item_list("References", references[:10]))

    owners = context.get("owners") or []
    if owners:
        sections.append(_render_bullets("Owners", owners[:8]))

    components = context.get("components") or []
    if components:
        sections.append(_render_item_list("Components", components[:8]))

    dependency_tree = context.get("dependency_tree") or {}
    if dependency_tree:
        sections.append(_render_dict("Dependency tree", dependency_tree))

    impact_analysis = context.get("impact_analysis") or {}
    if impact_analysis:
        sections.append(_render_dict("Impact analysis", impact_analysis))

    related_files = context.get("related_files") or []
    if related_files:
        sections.append(_render_bullets("Related files", related_files[:10]))

    sections.append("Instructions:")
    sections.append(output_instructions)
    sections.append("Output format:")
    if output_format in {"patch", "diff"}:
        sections.append("Return a unified diff patch only.")
    elif output_format == "json":
        sections.append("Return valid JSON only, with no surrounding markdown.")
    elif output_format == "markdown":
        sections.append("Return markdown formatted output.")
    else:
        sections.append("Return a concise human-readable answer.")

    prompt = "\n".join(section for section in sections if section is not None)
    if max_length is not None:
        prompt = _truncate_prompt(prompt, max_length)

    if return_stats:
        return prompt, _build_prompt_stats(prompt, mode, output_format)
    return prompt
