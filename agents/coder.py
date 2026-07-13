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
    "insert_before",
    "insert_after",
    "replace_range",
    "delete_range",
    "create_file",
    "delete_file",
    "move_symbol",
    "rename_symbol",
    "update_import",
}

REGION_OPERATIONS = {
    "insert_before",
    "insert_after",
    "replace_range",
    "delete_range",
}

# Operations that describe a whole-file or symbol-level change rather than a
# specific line region. These may omit start_line/end_line and instead rely
# on "symbol", "target_path", and/or "content" to fully describe the change.
NON_REGION_OPERATIONS = {
    "create_file",
    "delete_file",
    "move_symbol",
    "rename_symbol",
    "update_import",
}

# Semantic (business-rule) requirements per operation, enforced on top of the
# base VALID_OPERATIONS / REGION_OPERATIONS checks, so malformed change
# objects are rejected here instead of reaching the Patch Generator.
# Each value is a list of fields that must be present and non-empty for that
# operation. "metadata.new_name" is a special case handled as a nested
# lookup rather than a top-level field.
SEMANTIC_REQUIREMENTS: Dict[str, List[str]] = {
    "move_symbol": ["path", "target_path", "symbol"],
    "rename_symbol": ["path", "symbol", "metadata.new_name"],
    "update_import": ["path", "content"],
    "create_file": ["target_path", "content"],
    "delete_file": ["path"],
    "replace_range": ["start_line", "end_line", "content"],
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
    '      "operation": "insert_before" | "insert_after" | "replace_range" | "delete_range" | '
    '"create_file" | "delete_file" | "move_symbol" | "rename_symbol" | "update_import",\n'
    '      "start_line": 1,\n'
    '      "end_line": 1,\n'
    '      "content": "...",\n'
    '      "target_path": "relative/path/to/destination.ext",\n'
    '      "symbol": "function_or_class_name",\n'
    '      "metadata": {},\n'
    '      "reason": "planner_step"\n'
    "    }\n"
    "  ]\n"
    "}\n"
    "Allowed operations and what each means:\n"
    "- insert_before: insert \"content\" immediately before line \"start_line\" (end_line == start_line).\n"
    "- insert_after: insert \"content\" immediately after line \"end_line\" (start_line == end_line).\n"
    "- replace_range: replace lines \"start_line\" through \"end_line\" (inclusive) with \"content\".\n"
    "- delete_range: delete lines \"start_line\" through \"end_line\" (inclusive); omit or empty \"content\".\n"
    "- create_file: create a brand-new file. Set both \"path\" and \"target_path\" to the new file's "
    "relative path, and put the full file contents in \"content\"; omit start_line/end_line.\n"
    "- delete_file: delete the file at \"path\" entirely; omit start_line/end_line and \"content\".\n"
    "- move_symbol: move the definition named in \"symbol\" out of \"path\" and into \"target_path\", "
    "updating imports/references as needed; omit start_line/end_line unless region-scoped.\n"
    "- rename_symbol: rename the definition named in \"symbol\" (old name) to the new name given in "
    "metadata[\"new_name\"] (e.g. \"metadata\": {\"new_name\": \"sum_values\"}), updating the definition "
    "and all references; omit start_line/end_line unless region-scoped.\n"
    "- update_import: add, remove, or modify an import statement in \"path\", with the new import text "
    "in \"content\"; omit start_line/end_line unless region-scoped.\n"
    "Rules:\n"
    "- Never emit a full-file rewrite unless the operation is \"create_file\" for a new file.\n"
    "- For existing files, emit the smallest possible edit using insert_before, insert_after, "
    "replace_range, or delete_range, with 1-based inclusive line numbers from the numbered content shown below.\n"
    "- \"content\" holds only the new/changed code for that region, not the whole file (except for create_file).\n"
    "- delete_range and delete_file must omit or empty \"content\".\n"
    "- Choose the operation that matches the user's actual intent: use create_file for a brand-new file "
    "instead of insert_after into an unrelated file, use move_symbol instead of a delete+create pair when "
    "relocating a definition, and use rename_symbol instead of replace_range when only a name is changing.\n"
    "- \"target_path\", \"symbol\", and \"metadata\" are optional and only apply to certain operations "
    "(see above); omit them when not relevant instead of setting them to null.\n"
    "- Each operation has required fields that will be rejected as invalid if missing: move_symbol needs "
    "\"path\", \"target_path\", and \"symbol\"; rename_symbol needs \"path\", \"symbol\", and "
    "metadata[\"new_name\"]; update_import needs \"path\" and \"content\"; create_file needs \"target_path\" "
    "and \"content\"; delete_file needs \"path\"; replace_range needs \"start_line\", \"end_line\", and "
    "\"content\".\n"
    "- If multiple edits land in the same file, merge adjacent or overlapping regions into a single change object.\n"
    "- Preserve all unchanged code by omitting it entirely; do not restate untouched lines.\n"
    "- Match existing formatting, indentation, naming, typing, docstring style, logging, and import ordering exactly.\n"
    "- Do not introduce new dependencies unless explicitly requested by the step.\n"
    "- Set \"reason\" to the planner step id this change fulfills.\n"
    "- If a step cannot be completed as specified, set \"status\" to \"failed\" and explain in \"errors\"; do not invent a workaround."
)

OPERATION_SELECTION_GUIDE = (
    "Operation selection — prefer semantic operations over text edits whenever one applies. "
    "Only fall back to insert_before, insert_after, replace_range, or delete_range when no semantic "
    "operation below matches the intent.\n"
    "- \"Move add() to utils.py\" -> operation \"move_symbol\": symbol \"add\", path is the current file, "
    "target_path \"utils.py\".\n"
    "- \"Create utils.py\" / \"Create a new file for the math helpers\" -> operation \"create_file\": "
    "path and target_path both set to the new file's path, full contents in \"content\".\n"
    "- \"Rename add() to sum_values()\" -> operation \"rename_symbol\": symbol \"add\", "
    "metadata {\"new_name\": \"sum_values\"}.\n"
    "- \"Update the imports in app.py\" / \"Import multiply from utils\" -> operation \"update_import\": "
    "the new import statement(s) go in \"content\".\n"
    "- \"Delete utils.py\" / \"Remove the unused helper file\" -> operation \"delete_file\".\n"
    "- A small in-place text change with no matching semantic operation above (e.g. tweaking a condition, "
    "adding a log line inside an existing function) -> insert_before, insert_after, replace_range, or "
    "delete_range, whichever is smallest.\n"
)

LINE_NUMBER_RULES = (
    "Line Number Rules:\n"
    "- Use the 1-based line numbers shown in the numbered source code above.\n"
    "- Never guess line numbers.\n"
    "- If modifying existing code, use the exact line numbers from the numbered source.\n"
    "- If creating a new file, leave start_line and end_line as null.\n"
    "- If moving or renaming a symbol, specify the symbol name (\"symbol\") instead of guessing line numbers; "
    "leave start_line and end_line as null unless the change is also region-scoped.\n"
)


@dataclass
class Change:
    """
    A single repository edit produced by the Coder Agent.

    The Patch Generator is responsible for applying these changes.
    """
    # Target file
    path: str

    # Operation type
    operation: str

    # Why this exists
    reason: str

    # Region affected
    start_line: Optional[int] = None
    end_line: Optional[int] = None

    # New content
    content: str = ""

    # Optional metadata
    target_path: Optional[str] = None
    symbol: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

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
        sections.append("Prefer semantic operations over text edits whenever one applies:")
        sections.append("- Use move_symbol for moving a function, class, or module to another file.")
        sections.append("- Use rename_symbol for renaming an identifier.")
        sections.append("- Use update_import for adding, removing, or changing import statements.")
        sections.append("- Use create_file when a step requires a brand-new file.")
        sections.append("- Use delete_file when a step requires removing an entire file.")
        sections.append(
            "Use insert_before, insert_after, replace_range, or delete_range only when no semantic "
            "operation applies."
        )
        sections.append("Produce the minimal set of Change objects required.")
        sections.append("Assume a Validator, Patch Generator, and Repository Writer will process your output.")
        sections.append("Return ONLY valid JSON matching the required schema.")
        sections.append("")
        sections.append(OPERATION_SELECTION_GUIDE)
        sections.append("")
        sections.append(LINE_NUMBER_RULES)
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

    def _check_semantic_requirements(
        self,
        operation: str,
        path: str,
        content: str,
        start_line: Optional[int],
        end_line: Optional[int],
        target_path: Optional[str],
        symbol: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> None:
        """Enforce the SEMANTIC_REQUIREMENTS table for `operation`.

        This is business-rule validation on top of the structural checks
        already done in _validate_change_entry (valid operation, correct
        field types, integer line ranges). It exists so a malformed
        semantic operation (e.g. a move_symbol with no target_path) is
        rejected here rather than silently reaching the Patch Generator.
        """
        required_fields = SEMANTIC_REQUIREMENTS.get(operation)
        if not required_fields:
            return

        values: Dict[str, Any] = {
            "path": path,
            "target_path": target_path,
            "symbol": symbol,
            "content": content,
            "start_line": start_line,
            "end_line": end_line,
        }

        for field_name in required_fields:
            if field_name == "metadata.new_name":
                new_name = (metadata or {}).get("new_name")
                if not isinstance(new_name, str) or not new_name.strip():
                    raise CoderExecutionError(
                        f"'{operation}' change for '{path}' requires metadata[\"new_name\"]."
                    )
                continue

            value = values.get(field_name)
            if value is None:
                missing = True
            elif isinstance(value, str):
                missing = not value.strip()
            else:
                missing = False

            if missing:
                raise CoderExecutionError(
                    f"'{operation}' change for '{path}' requires '{field_name}'."
                )

    def _validate_change_entry(self, entry: Any, step: ExecutionStep) -> Change:
        if not isinstance(entry, dict):
            raise CoderExecutionError("each change entry must be an object.")

        path = entry.get("path")
        operation = entry.get("operation")
        content = entry.get("content", "") or ""
        reason = entry.get("reason") or step.id
        start_line = entry.get("start_line")
        end_line = entry.get("end_line")
        target_path = entry.get("target_path")
        symbol = entry.get("symbol")
        metadata = entry.get("metadata")

        if not isinstance(path, str) or not path:
            raise CoderExecutionError("change entry missing valid 'path'.")
        if operation not in VALID_OPERATIONS:
            raise CoderExecutionError(f"change entry '{path}' has invalid operation: {operation}")
        if target_path is not None and not isinstance(target_path, str):
            raise CoderExecutionError(f"change entry '{path}' has non-string 'target_path'.")
        if symbol is not None and not isinstance(symbol, str):
            raise CoderExecutionError(f"change entry '{path}' has non-string 'symbol'.")
        if metadata is not None and not isinstance(metadata, dict):
            raise CoderExecutionError(f"change entry '{path}' has non-object 'metadata'.")
        if operation in REGION_OPERATIONS:
            if not isinstance(start_line, int) or not isinstance(end_line, int):
                raise CoderExecutionError(
                    f"'{operation}' change for '{path}' requires integer start_line and end_line."
                )
            if start_line < 1 or end_line < start_line:
                raise CoderExecutionError(f"'{operation}' change for '{path}' has invalid line range.")
        if operation in {"delete_range", "delete_file"} and content.strip():
            content = ""

        self._check_semantic_requirements(
            operation, path, content, start_line, end_line, target_path, symbol, metadata
        )

        return Change(
            path=path,
            operation=operation,
            reason=str(reason),
            start_line=start_line if isinstance(start_line, int) else None,
            end_line=end_line if isinstance(end_line, int) else None,
            content=content,
            target_path=target_path,
            symbol=symbol,
            metadata=metadata,
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