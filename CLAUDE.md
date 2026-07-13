# AutoDevAI

## Project Goal

AutoDevAI is a modular autonomous software engineering system.

The objective is to understand an existing repository, reason about it, plan implementation work, generate minimal code changes, review them, test them and eventually commit them.

The architecture is intentionally modular. Every component should have a single responsibility.

---

# Current Architecture

Repository Scanner
↓
Language Detection
↓
Language Parsers
↓
Repository Index
↓
Dependency Graph
↓
Relationship Graph
↓
Query Engine
↓
Context Builder
↓
Reasoning Engine
↓
Planner
↓
Coder
↓
Reviewer
↓
Tester
↓
Committer

Execution starts from:

- run_ai.py
- main.py

---

# Repository Structure

agents/
    planner.py
    planner_executor.py
    planner_models.py
    planner_prompts.py
    planner_rules.py
    planner_config.py
    coder.py
    reviewer.py
    tester.py
    committer.py

core/
    repository.py
    indexer.py
    graph.py
    relationship.py
    queries.py
    context_builder.py
    prompt_builder.py
    intelligence.py
    ai.py
    model.py

core/parsers/
    python_parser.py
    javascript_parser.py
    html_parser.py
    css_parser.py

core/reasoning/
    architecture.py
    dependency.py
    impact.py
    ownership.py
    duplicate.py
    dead_code.py

---

# Coding Rules

Always preserve the existing architecture.

Never redesign the architecture unless explicitly requested.

Prefer extending existing modules instead of creating new ones.

Keep functions small and cohesive.

Avoid unnecessary abstractions.

Avoid duplicate logic.

Never rewrite an entire file if a targeted modification is sufficient.

Generate the smallest correct patch.

Preserve formatting and coding style.

---

# Agent Responsibilities

Planner
- Understand the request.
- Break work into implementation steps.
- Produce structured plans.

Coder
- Modify only necessary files.
- Generate minimal edits.
- Preserve public APIs unless requested.

Reviewer
- Detect bugs.
- Detect regressions.
- Detect style issues.
- Suggest improvements.

Tester
- Identify required tests.
- Add tests when appropriate.
- Ensure modified code paths are covered.

Committer
- Produce clear commit messages.
- Never commit automatically unless instructed.

---

# Development Preferences

Before writing code:

1. Understand the repository.
2. Trace dependencies.
3. Check related modules.
4. Explain the intended change briefly.

When editing:

- Prefer patches over rewrites.
- Reuse existing utilities.
- Avoid dead code.
- Avoid breaking APIs.

After editing:

- Check imports.
- Check syntax.
- Check obvious edge cases.

---

# Response Style

Be concise.

Do not explain obvious Python syntax.

When a design issue is discovered:

- explain the problem
- explain the impact
- propose the fix
- then implement after approval if the change is architectural.

Do not make speculative changes.

Ask questions only if information is actually missing.

## Repository Analysis Rules

Never assume the architecture from documentation alone.

Before answering architectural questions:

- inspect the actual source files
- trace imports
- trace function calls
- identify execution flow
- reference concrete filenames, classes, and functions

If documentation and source disagree, trust the source code.