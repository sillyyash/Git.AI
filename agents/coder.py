"""AI Coder Agent for AutoDevAI.

Pipeline position:
Planner -> Context Builder -> Coder -> Patch Generator -> Validator ->
Repository Writer -> Reindex -> Git

The Coder's sole responsibility is to generate repository CHANGES. It:
- Executes every "coder" execution step from the authoritative Plan, in order
- Builds per-step repository context via core.context_builder
- Builds prompts via core.prompt_builder, augmented with numbered existing
  file content and a strict JSON change-object output contract
- Calls the LLM via core.model.OllamaClient
- Parses and self-validates structured, minimal, region-based change objects

The Coder NEVER:
- Writes to disk
- Applies patches
- Performs Git operations
- Reindexes the repository
- Emits full-file rewrites unless a step explicitly requests file creation

Those responsibilities belong to the Patch Generator, Validator, Repository
Writer, Reindexer, and Git stages downstream of this agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import json
import re

from core.model import ModelConfig, OllamaClient
from core.prompt_builder import build_prompt
from core.context_builder import build_context
from core.repository import Repository
from agents.planner_models import Plan, ExecutionStep


CODE_FENCE_RE = re.compile(r"^```[a-zA-Z0-9]*\n|\n```$", re.MULTILINE)

VALID_OPERATIONS = {
    "create",
    "replace_region",
    "insert_before",
    "insert_after",
    "delete_region",
    "rename_symbol",
    "move_symbol",
}

REGION_OPERATIONS = {
    "replace_region",
    "insert_before",
    "insert_after",
    "delete_region",
}

CODER_OUTPUT_CONTRACT = (
    "Return only valid JSON with no markdown fences and no explanation outside the JSON object. "
    "The JSON object must have this exact shape:\n"
    "{\n"
    '  "status": "success" | "failed",\n'
    '  "summary": "one concise sentence describing what was done",\n'
    '  "warnings": ["..."],\n'
    '  "errors": ["..."],\n'
    '  "changes": [\n'
    "    {\n"
    '      "path": "relative/path/to/file.ext",\n'
    '      "operation": "create" | "replace_region" | "insert_before" | "insert_after" | "delete_region" | "rename_symbol" | "move_symbol",\n'
    '      "start_line": 1,\n'
    '      "end_line": 1,\n'
    '      "content": "...",\n'
    '      "reason": "planner_step"\n'
    "    }\n"
    "  ]\n"
    "}\n"
    "Rules:\n"
    "- Never emit a full-file rewrite unless the operation is \"create\" for a new file.\n"
    "- For existing files, emit the smallest possible region edit: replace_region, insert_before, "
    "insert_after, or delete_region, using 1-based inclusive line numbers from the numbered content shown below.\n"
    "- \"content\" holds only the new/changed code for that region, not the whole file.\n"
    "- delete_region must omit or empty \"content\".\n"
    "- rename_symbol and move_symbol may omit start_line/end_line if not region-scoped; describe the change fully in \"content\" and \"reason\".\n"
    "- If multiple edits land in the same file, merge adjacent or overlapping regions into a single change object.\n"
    "- Preserve all unchanged code by omitting it entirely; do not restate untouched lines.\n"
    "- Match existing formatting, indentation, naming, typing, docstring style, logging, and import ordering exactly.\n"
    "- Do not introduce new dependencies unless explicitly requested by the step.\n"
    "- Set \"reason\" to the planner step id this change fulfills.\n"
    "- If a step cannot be completed as specified, set \"status\" to \"failed\" and explain in \"errors\"; do not invent a workaround."
)


@dataclass
class Change:
    """A single minimal, region-scoped repository change."""
    path: str
    operation: str
    reason: str
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    content: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CoderResult:
    """Structured output of the Coder Agent, matching the pipeline contract."""
    status: str  # "success" or "failed"
    summary: str
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    changes: List[Change] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["changes"] = [c.to_dict() for c in self.changes]
        return data


@dataclass
class CoderConfig:
    """Coder agent configuration."""
    model: str = "deepseek-r1:14b"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.2
    max_tokens: int = 4096
    timeout: float = 120.0
    retries: int = 3


class CoderExecutionError(RuntimeError):
    """Raised when a coder step cannot be completed or self-validation fails."""


class CoderAgent:
    """Main Coder Agent class.

    Executes the coder steps of a Plan and returns structured, minimal,
    region-based change objects. Never touches disk, Git, or the index —
    those belong to downstream pipeline stages.
    """

    def __init__(self, config: Optional[CoderConfig] = None, debug: bool = False):
        self.config = config or CoderConfig()
        self.debug = debug
        self._client = OllamaClient(
            ModelConfig(
                model=self.config.model,
                base_url=self.config.base_url,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                timeout=self.config.timeout,
                retries=self.config.retries,
            )
        )

    def execute(
        self,
        plan: Plan,
        repository: Repository,
        repository_index: Any,
        dependency_graph: Any,
        relationship_graph: Any,
    ) -> CoderResult:
        """Execute every coder step in the plan, in order, and return changes.

        Args:
            plan: Authoritative Plan from the Planner.
            repository: Scanned Repository, used read-only for existing file
                content (never written to).
            repository_index: RepositoryIndex instance, passed through to
                context_builder.
            dependency_graph: DependencyGraph instance, passed through to
                context_builder.
            relationship_graph: RelationshipGraph instance, passed through to
                context_builder.

        Returns:
            CoderResult containing the aggregate, ordered set of change
            objects produced across all coder steps.
        """
        coder_steps = sorted(
            (s for s in plan.execution_steps if s.agent == "coder"),
            key=lambda s: s.order,
        )

        all_changes: List[Change] = []
        warnings: List[str] = []
        errors: List[str] = []
        overall_status = "success"

        for step in coder_steps:
            try:
                step_changes = self._execute_step(
                    step, plan, repository, repository_index, dependency_graph, relationship_graph
                )
                all_changes.extend(step_changes)
            except CoderExecutionError as exc:
                overall_status = "failed"
                errors.append(f"step {step.id}: {exc}")
                if self.debug:
                    print(f"[coder] step {step.id} failed: {exc}")

        merged_changes = self._merge_same_file_changes(all_changes)

        summary = (
            f"Executed {len(coder_steps)} coder step(s), producing "
            f"{len(merged_changes)} change object(s) across "
            f"{len({c.path for c in merged_changes})} file(s)."
        )

        return CoderResult(
            status=overall_status,
            summary=summary,
            warnings=warnings,
            errors=errors,
            changes=merged_changes,
        )

    def _execute_step(
        self,
        step: ExecutionStep,
        plan: Plan,
        repository: Repository,
        repository_index: Any,
        dependency_graph: Any,
        relationship_graph: Any,
    ) -> List[Change]:
        context = build_context(
            step.description,
            repository_index,
            dependency_graph,
            relationship_graph,
        )

        prompt = self._build_step_prompt(step, plan, repository, context)
        print("\n========== PROMPT ==========")
        print(f"Prompt length: {len(prompt):,} characters")
        print(prompt[:1000])
        print("...")
        print("========== CALLING MODEL ==========\n")

        response_text = self._call_model(prompt)

        print("\n========== MODEL RETURNED ==========\n")

        return self._parse_response(response_text, step)
    
    def _build_step_prompt(
        self,
        step: ExecutionStep,
        plan: Plan,
        repository: Repository,
        context: Dict[str, Any],
    ) -> str:
        base_prompt = build_prompt(
            plan.request,
            context,
            mode="coder",
            output_format="json",
        )

        sections: List[str] = [base_prompt, ""]

        sections.append("Execution Context:")
        sections.append(f"Original user request: {plan.request}")
        sections.append(f"Planner intent: {plan.intent.value}")
        sections.append(f"Planner summary: {plan.summary}")
        sections.append(f"Step id: {step.id}")
        sections.append(f"Step action: {step.action}")
        sections.append(f"Step description: {step.description}")
        sections.append("")

        if step.affected_files:
            sections.append("Files this step must operate on:")
            for path in step.affected_files:
                sections.append(f"- {path}")

        if step.affected_symbols:
            sections.append("Symbols this step must operate on:")
            for symbol in step.affected_symbols:
                text = f"- {symbol.name} ({symbol.kind})"
                if symbol.file:
                    text += f" in {symbol.file}"
                sections.append(text)

        numbered_content = self._collect_numbered_content(
            repository,
            step.affected_files,
        )

        if numbered_content:
            sections.append("")
            sections.append("===== SOURCE CODE =====")

            for path, numbered in numbered_content.items():
                sections.append(f"FILE: {path}")
                sections.append("=" * 80)
                sections.append(numbered)
                sections.append("=" * 80)
                sections.append(f"END FILE: {path}")
                sections.append("")

        if step.validation:
            sections.append(f"Validation expectation: {step.validation}")

        sections.append("")
        sections.append("===== CODER RESPONSIBILITIES =====")
        sections.append("You are the Coder Agent.")
        sections.append("Your job is ONLY to propose Change objects.")
        sections.append("Do NOT apply patches.")
        sections.append("Do NOT validate whether files exist.")
        sections.append("Do NOT validate line numbers.")
        sections.append("Do NOT rewrite entire files unless explicitly requested.")
        sections.append("Do NOT explain your reasoning.")
        sections.append("Produce the minimal set of Change objects required.")
        sections.append("Assume a Validator, Patch Generator, and Repository Writer will process your output.")
        sections.append("Return ONLY valid JSON matching the required schema.")
        sections.append("")
        sections.append(CODER_OUTPUT_CONTRACT)

        return "\n".join(sections)

    def _collect_numbered_content(
        self, repository: Repository, paths: List[str]
    ) -> Dict[str, str]:
        by_path = {f.path: f.content for f in repository.files}
        numbered: Dict[str, str] = {}
        for path in paths:
            content = by_path.get(path)
            if content is None:
                continue
            lines = content.splitlines()
            numbered[path] = "\n".join(f"{i + 1}\t{line}" for i, line in enumerate(lines))
        return numbered

    def _call_model(self, prompt: str) -> str:
        try:
            return self._client.generate(prompt)
        except Exception as exc:
            raise CoderExecutionError(f"model call failed: {exc}") from exc

    def _parse_response(self, response_text: str, step: ExecutionStep) -> List[Change]:
        cleaned = CODE_FENCE_RE.sub("", response_text.strip()).strip()

        try:
            payload = json.loads(cleaned)
        except ValueError as exc:
            raise CoderExecutionError(f"model response is not valid JSON: {exc}") from exc

        if not isinstance(payload, dict):
            raise CoderExecutionError("model response must be a JSON object.")

        status = payload.get("status")
        if status == "failed":
            step_errors = payload.get("errors") or ["coder reported failure with no detail"]
            raise CoderExecutionError("; ".join(str(e) for e in step_errors))
        if status != "success":
            raise CoderExecutionError(f"unexpected status field: {status!r}")

        raw_changes = payload.get("changes")
        if not isinstance(raw_changes, list):
            raise CoderExecutionError("'changes' field must be a list.")

        changes: List[Change] = []
        for entry in raw_changes:
            changes.append(self._validate_change_entry(entry, step))

        return changes

    def _validate_change_entry(self, entry: Any, step: ExecutionStep) -> Change:
        if not isinstance(entry, dict):
            raise CoderExecutionError("each change entry must be an object.")

        path = entry.get("path")
        operation = entry.get("operation")
        content = entry.get("content", "") or ""
        reason = entry.get("reason") or step.id
        start_line = entry.get("start_line")
        end_line = entry.get("end_line")

        if not isinstance(path, str) or not path:
            raise CoderExecutionError("change entry missing valid 'path'.")
        if operation not in VALID_OPERATIONS:
            raise CoderExecutionError(f"change entry '{path}' has invalid operation: {operation}")
        if operation == "create" and not content.strip():
            raise CoderExecutionError(f"'create' change for '{path}' has empty content.")
        if operation in REGION_OPERATIONS:
            if not isinstance(start_line, int) or not isinstance(end_line, int):
                raise CoderExecutionError(
                    f"'{operation}' change for '{path}' requires integer start_line and end_line."
                )
            if start_line < 1 or end_line < start_line:
                raise CoderExecutionError(f"'{operation}' change for '{path}' has invalid line range.")
        if operation == "delete_region" and content.strip():
            content = ""

        return Change(
            path=path,
            operation=operation,
            reason=str(reason),
            start_line=start_line if isinstance(start_line, int) else None,
            end_line=end_line if isinstance(end_line, int) else None,
            content=content,
        )

    def _merge_same_file_changes(self, changes: List[Change]) -> List[Change]:
        merged: List[Change] = []
        seen_region_keys: Dict[tuple, Change] = {}

        for change in changes:
            if change.operation in REGION_OPERATIONS:
                key = (change.path, change.operation, change.start_line, change.end_line)
                existing = seen_region_keys.get(key)
                if existing is not None:
                    existing.content = f"{existing.content}\n{change.content}".strip("\n")
                    existing.reason = f"{existing.reason}, {change.reason}"
                    continue
                seen_region_keys[key] = change
            merged.append(change)

        return merged


# Public API

def create_coder(config: Optional[CoderConfig] = None, debug: bool = False) -> CoderAgent:
    """Factory function to create a Coder Agent."""
    return CoderAgent(config=config, debug=debug)


def execute_plan(
    plan: Plan,
    repository: Repository,
    repository_index: Any,
    dependency_graph: Any,
    relationship_graph: Any,
    config: Optional[CoderConfig] = None,
    debug: bool = False,
) -> CoderResult:
    """Execute a plan's coder steps.

    Convenience function for one-off execution without creating an agent.
    """
    coder = create_coder(config=config, debug=debug)
    return coder.execute(plan, repository, repository_index, dependency_graph, relationship_graph)


__all__ = [
    "CoderAgent",
    "CoderConfig",
    "CoderResult",
    "Change",
    "CoderExecutionError",
    "create_coder",
    "execute_plan",
]