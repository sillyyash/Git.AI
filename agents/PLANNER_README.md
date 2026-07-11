"""AI Planner Agent Architecture and Documentation

The Planner Agent is the first component in the AutoDevAI pipeline, sitting BEFORE
the AI generation pipeline. It understands code modification requests and produces
structured execution plans for downstream agents.

## Architecture Overview

```
User Request
    ↓
Planner Agent
├── Intent Detection
├── Repository Intelligence
├── Impact Analysis
├── Dependency Analysis
├── Risk Assessment
├── Complexity Estimation
└── Plan Generation
    ↓
Plan Object (Structured Data)
    ↓
Downstream Agents (Coder, Tester, Reviewer, Committer)
```

## Module Structure

agents/
├── planner.py                 # Main entry point and PlannerAgent class
├── planner_models.py          # Data models (Intent, Risk, Complexity, Plan, etc.)
├── planner_rules.py           # Intent classification and heuristic rules
├── planner_prompts.py         # LLM prompts for reasoning
└── planner_executor.py        # Planning pipeline coordinator

## Key Design Principles

### 1. Strict Separation of Concerns

The Planner uses ONLY the public `core.queries.*` API and never:
- Accesses DependencyGraph, RelationshipGraph, or RepositoryIndex directly
- Imports from core.reasoning modules
- Calls model/Ollama directly (that's ai.py's responsibility)
- Modifies any files or repositories
- Generates code

### 2. Structured, Strongly-Typed Output

All output is strictly typed using Python dataclasses:

```python
@dataclass
class Plan:
    intent: Intent
    request: str
    summary: str
    reasoning: str
    affected_symbols: List[Symbol]
    affected_files: List[str]
    dependencies: Dict[str, List[str]]
    risk: Risk
    complexity: Complexity
    execution_steps: List[ExecutionStep]
    validation_steps: List[str]
```

Plans are JSON-serializable and self-documenting.

### 3. Modular, Testable Reasoning

Intent classification, risk estimation, and complexity estimation are
separate, testable functions that use keyword matching and heuristics
rather than LLM calls (keeping planning fast and deterministic).

### 4. Extensibility for Future Agents

The architecture is designed to easily add Coder, Reviewer, and Tester
agents as specializations. Each agent can:
- Consume Plan objects
- Execute their assigned ExecutionSteps
- Report results back
- Propose alternative plans if needed

## Intent Classifications

The Planner classifies user requests into these intents:

- **RENAME**: Change identifier names (functions, classes, variables)
- **REFACTOR**: Restructure code, improve organization, extract functions
- **FEATURE**: Add new functionality or endpoints
- **BUG**: Fix broken behavior or errors
- **EXPLAIN**: Clarify code meaning or behavior (mostly for review/analysis)
- **REVIEW**: Analyze code for quality or issues
- **OPTIMIZE**: Improve performance, reduce complexity
- **DELETE**: Remove unused code, dead code, deprecated features
- **GENERATE**: Create boilerplate, scaffolding, or test stubs
- **TEST**: Add or improve test coverage
- **DOCS**: Add or improve documentation
- **UNKNOWN**: Unclear or ambiguous requests

## Risk Assessment

Risk levels indicate potential issues and side effects:

- **LOW**: Isolated changes, well-tested, clear scope, no circular deps
- **MEDIUM**: Multiple modules, moderate dependencies, some uncertainty
- **HIGH**: Critical paths, circular deps, poor test coverage, wide impact

Risk is estimated using heuristics:
- File count and symbol count (wider impact = higher risk)
- Dependency depth and cycles
- Test coverage gaps
- Critical path detection

## Complexity Estimation

Complexity levels indicate effort required:

- **TRIVIAL**: Single file, no dependencies, <5 minutes
- **SMALL**: Single module, local changes, <30 minutes
- **MEDIUM**: Multiple files, moderate testing, 1-4 hours
- **LARGE**: Cross-module, extensive testing, >4 hours

## Execution Plan Generation

For each request, the Planner generates an ordered sequence of ExecutionSteps.
Each step:
- Has a unique ID and order
- Is assigned to an agent (coder, tester, reviewer, committer)
- Has clear dependencies on other steps
- Includes context and hints for the executing agent
- Has validation criteria

Example plan for "rename login to authenticate":

```
1. locate_symbols (planner)
   - Locate all references to 'login'
   
2. analyze_deps (planner)
   - Analyze dependency chain
   depends_on: [locate_symbols]
   
3. prepare_rename (coder)
   - Update function definition and imports
   depends_on: [analyze_deps]
   
4. run_tests (tester)
   - Verify all tests pass
   depends_on: [prepare_rename]
   
5. review_code (reviewer)
   - Code review for correctness
   depends_on: [run_tests]
   
6. commit_changes (committer)
   - Commit and push
   depends_on: [review_code]
```

## Usage Examples

### Basic Usage

```python
from agents.planner import create_planner

# Create a planner
planner = create_planner(debug=False)

# Create a plan
plan = planner.plan(
    request="rename the calculateTotal function to computeSum",
    repository_index=index,
    dependency_graph=dep_graph,
    relationship_graph=rel_graph,
)

# Convert to JSON for storage/transmission
plan_json = planner.plan_to_json(plan)
```

### One-Off Planning

```python
from agents.planner import plan_code_operation

plan = plan_code_operation(
    "add dark mode support",
    repository_index=index,
    dependency_graph=dep_graph,
    relationship_graph=rel_graph,
    debug=True,
)
```

### Accessing Plan Data

```python
# Access individual components
print(f"Intent: {plan.intent.value}")
print(f"Risk: {plan.risk.value}")
print(f"Complexity: {plan.complexity.value}")

# Iterate over execution steps
for step in plan.execution_steps:
    print(f"Step {step.order}: {step.action} ({step.agent})")
    for dep_id in step.depends_on:
        print(f"  depends on: {dep_id}")

# Convert to dict for downstream processing
plan_dict = planner.plan_to_dict(plan)
```

## Integration with AI Pipeline

The Planner sits BEFORE the AI generation pipeline:

```
User Request
    ↓
Planner Agent ← (NO LLM CALLS)
    ↓
Plan Object
    ↓
Coder Agent ← (Uses Planner output + LLM for implementation)
Tester Agent
Reviewer Agent
Committer Agent
```

The AI pipeline (ai.py) will consume the Plan and delegate to appropriate agents.

## Testing

Comprehensive test suite in `tests/test_planner.py`:

```bash
# Run all planner tests
python -m pytest tests/test_planner.py -v

# Run specific test class
python -m pytest tests/test_planner.py::TestIntentClassification -v

# Run with coverage
python -m pytest tests/test_planner.py --cov=agents --cov-report=html
```

## Implementation Details

### Intent Classification (planner_rules.py)

Uses keyword matching and pattern detection:
- Keywords mapped to intents (e.g., "rename" → Intent.RENAME)
- Pattern-based detection for complex cases
- Confidence scoring based on match quality
- No LLM required (fast and deterministic)

### Risk Estimation (planner_rules.py)

Heuristic-based assessment:
- Intent baseline (some intents inherently riskier)
- File/symbol impact scoring
- Dependency depth and cycles
- Test coverage gaps
- Critical path detection

### Complexity Estimation (planner_rules.py)

Similar heuristic approach:
- Intent baseline
- Impact metrics
- Dependency complexity
- Data migration requirements

### Impact Analysis (planner_executor.py)

Uses `core.queries.*` API to find:
- Affected symbols (via search_symbol)
- Affected files (via impact analysis)
- Dependencies (via find_all_dependencies)
- Related files (via find_related_files)

### Plan Generation (planner_executor.py)

Creates execution steps based on intent:
- Locate and validate affected code
- Analyze dependencies
- Prepare changes (intent-specific)
- Run tests
- Code review
- Commit and push

Steps have explicit dependencies for parallel/sequential execution.

## Future Enhancements

1. **LLM-Enhanced Analysis**: Use LLM prompts (in planner_prompts.py) to
   refine plan generation based on repository-specific context.

2. **Coder Agent**: Implement code generation agent that consumes Plan
   objects and generates actual changes.

3. **Reviewer Agent**: Implement code review agent for quality checks.

4. **Tester Agent**: Implement testing agent for validation.

5. **Committer Agent**: Implement git operations agent.

6. **Plan Refinement**: Allow downstream agents to propose alternative
   plans if primary plan encounters issues.

7. **Rollback Strategy**: Add automatic rollback capabilities if plan
   execution fails.

## Constraints and Limitations

1. **No Code Generation**: Planner only plans; it never modifies code.

2. **Public API Only**: Never accesses internal graphs or reasoning modules.

3. **Deterministic**: Intent classification and estimation use heuristics,
   not LLM calls, for determinism.

4. **No Model Calls**: Planner never calls Ollama or other models directly.

5. **Strongly Typed**: All output is strictly typed for clarity.

## Performance Characteristics

- Intent classification: O(n) keyword matching, <10ms typical
- Impact analysis: O(m) symbol search, <100ms typical
- Risk/complexity estimation: O(1) heuristic scoring, <1ms typical
- Full plan generation: O(n + m) overall, <500ms typical

Suitable for real-time interactive use.

## Related Modules

- `core.queries.*`: Public query API (use this, not graph internals)
- `core.intelligence.*`: Repository intelligence (detect frameworks, etc.)
- `core.reasoning.*`: Graph analysis (dependency analysis, ownership, etc.)
- `core.ai.py`: AI generation pipeline (will use Plan objects)
"""
