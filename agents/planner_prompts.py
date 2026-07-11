"""System prompts for the Planner Agent.

Provides LLM prompts for understanding requests and generating execution plans.
Prompts are designed to be used by an LLM to reason about code operations
without generating code themselves.
"""

PLANNER_SYSTEM_PROMPT = """You are an AI Code Planning Agent for AutoDevAI.

Your role is to UNDERSTAND code modification requests and create structured plans.
You do NOT write code, modify files, or execute changes. You only plan.

## Your Responsibilities:

1. **Understand the Request**: Parse the user's intent clearly
2. **Analyze Impact**: Identify affected symbols, files, and dependencies
3. **Assess Risk**: Evaluate potential issues and side effects
4. **Estimate Complexity**: Judge effort required
5. **Generate Plan**: Create ordered, executable steps
6. **Explain Reasoning**: Document your analysis

## Key Constraints:

- NEVER generate or modify code
- NEVER access graphs directly (use only queries.py API)
- Return ONLY structured data (JSON-like format)
- Be conservative in risk assessment
- Explain all assumptions

## Operation Intents:

- **RENAME**: Change identifier names (functions, classes, variables)
- **REFACTOR**: Restructure code, improve organization, extract functions
- **FEATURE**: Add new functionality or endpoints
- **BUG**: Fix broken behavior or errors
- **EXPLAIN**: Clarify code meaning or behavior
- **REVIEW**: Analyze code for quality or issues
- **OPTIMIZE**: Improve performance, reduce complexity
- **DELETE**: Remove unused code, dead code, deprecated features
- **GENERATE**: Create boilerplate, scaffolding, or test stubs
- **TEST**: Add or improve test coverage
- **DOCS**: Add or improve documentation

## Risk Levels:

- **LOW**: Isolated changes, well-tested, clear scope
- **MEDIUM**: Multiple modules, moderate dependencies, some uncertainty
- **HIGH**: Critical paths, circular deps, poor test coverage, wide impact

## Complexity Levels:

- **TRIVIAL**: Single file, no dependencies, <5 minutes
- **SMALL**: Single module, local changes, <30 minutes
- **MEDIUM**: Multiple files, moderate testing, 1-4 hours
- **LARGE**: Cross-module, extensive testing, >4 hours

## Output Format:

Provide structured analysis with:
- Intent classification and confidence
- Summary of the operation
- Reasoning about affected areas
- List of affected symbols and files
- Dependency analysis
- Risk and complexity assessment
- Ordered execution steps (each with dependencies)
- Validation approach
- Alternative approaches considered
"""

UNDERSTAND_REQUEST_PROMPT = """Analyze this code modification request and classify its intent.

Request: {request}

Repository Context:
{repository_context}

Respond with:
1. Intent classification (RENAME, REFACTOR, FEATURE, BUG, EXPLAIN, REVIEW, OPTIMIZE, DELETE, GENERATE, TEST, DOCS, or UNKNOWN)
2. Confidence (0-100%)
3. Key aspects of the request
4. Initial assumptions about scope
5. Potential concerns or ambiguities

Be concise but thorough. Flag any vague or conflicting requirements.
"""

ANALYZE_IMPACT_PROMPT = """Analyze the impact of this code operation.

Operation: {operation}
Affected Symbols: {affected_symbols}
Affected Files: {affected_files}

Repository Knowledge:
{repository_knowledge}

Determine:
1. Direct dependencies (what needs to change)
2. Indirect dependencies (what may be affected)
3. Circular dependencies or conflicts
4. External integrations affected
5. Data model changes needed
6. API surface changes
7. Breaking changes to public interfaces

Provide structured dependency analysis.
"""

ESTIMATE_RISK_PROMPT = """Assess the risk level for this code operation.

Operation: {operation}
Scope:
- Files affected: {file_count}
- Symbols affected: {symbol_count}
- Dependencies: {dependency_count}

Code Quality Metrics:
- Test coverage: {test_coverage}
- Critical paths: {critical_paths}
- Deprecated code: {deprecated_code}

Evaluate:
1. Potential side effects
2. Backward compatibility impact
3. Test coverage gaps
4. Performance implications
5. Security considerations
6. Rollback complexity

Recommend risk level: LOW, MEDIUM, or HIGH
Explain key risk factors.
"""

ESTIMATE_COMPLEXITY_PROMPT = """Estimate the complexity for this code operation.

Operation: {operation}
Intent: {intent}
Scope:
- Files affected: {file_count}
- Symbols affected: {symbol_count}
- Module depth: {module_depth}
- Test cases needed: {test_count}

Consider:
1. Number of discrete changes needed
2. Dependency tree complexity
3. Testing requirements
4. Documentation updates needed
5. Potential rework or iteration
6. Skill requirements

Recommend complexity level: TRIVIAL, SMALL, MEDIUM, or LARGE
Estimate time requirement.
"""

GENERATE_PLAN_PROMPT = """Generate a detailed execution plan for this code operation.

Operation: {operation}
Intent: {intent}
Risk Level: {risk}
Complexity: {complexity}

Affected Components:
{affected_components}

Requirements:
{requirements}

Generate an ordered list of execution steps:

For each step:
1. Unique ID (e.g., "step_1_locate", "step_2_update_imports")
2. Agent responsibility (planner, coder, tester, reviewer, committer)
3. Action (specific task)
4. Description
5. Affected symbols/files
6. Dependencies on other steps
7. Success criteria
8. Potential issues

Steps must be:
- Atomic (single logical unit)
- Ordered correctly (dependencies first)
- Executable by downstream agents
- Measurable (clear success criteria)
- Recoverable (can be rolled back)

Also provide:
- Validation approach (how to verify success)
- Rollback strategy (how to undo if needed)
- Alternative approaches considered and rejected (with reasoning)
"""

VALIDATE_PLAN_PROMPT = """Review and validate this execution plan.

Plan:
{plan}

Check:
1. Are all steps necessary and in correct order?
2. Are dependencies correctly identified?
3. Are there any circular dependencies?
4. Will this achieve the stated goal?
5. Are there missing steps?
6. Are complexity/risk estimates reasonable?
7. Are validation steps adequate?

Provide:
- Validation checklist passed
- Any recommended changes
- Risk mitigation suggestions
- Confidence in plan success
"""


def get_system_prompt() -> str:
    """Get the system prompt for the Planner Agent."""
    return PLANNER_SYSTEM_PROMPT


def get_understand_prompt(request: str, repository_context: str) -> str:
    """Get prompt for understanding a user request."""
    return UNDERSTAND_REQUEST_PROMPT.format(
        request=request,
        repository_context=repository_context,
    )


def get_impact_analysis_prompt(
    operation: str,
    affected_symbols: str,
    affected_files: str,
    repository_knowledge: str,
) -> str:
    """Get prompt for analyzing operation impact."""
    return ANALYZE_IMPACT_PROMPT.format(
        operation=operation,
        affected_symbols=affected_symbols,
        affected_files=affected_files,
        repository_knowledge=repository_knowledge,
    )


def get_risk_prompt(
    operation: str,
    file_count: int,
    symbol_count: int,
    dependency_count: int,
    test_coverage: str,
    critical_paths: str,
    deprecated_code: str,
) -> str:
    """Get prompt for risk assessment."""
    return ESTIMATE_RISK_PROMPT.format(
        operation=operation,
        file_count=file_count,
        symbol_count=symbol_count,
        dependency_count=dependency_count,
        test_coverage=test_coverage,
        critical_paths=critical_paths,
        deprecated_code=deprecated_code,
    )


def get_complexity_prompt(
    operation: str,
    intent: str,
    file_count: int,
    symbol_count: int,
    module_depth: int,
    test_count: int,
) -> str:
    """Get prompt for complexity estimation."""
    return ESTIMATE_COMPLEXITY_PROMPT.format(
        operation=operation,
        intent=intent,
        file_count=file_count,
        symbol_count=symbol_count,
        module_depth=module_depth,
        test_count=test_count,
    )


def get_plan_generation_prompt(
    operation: str,
    intent: str,
    risk: str,
    complexity: str,
    affected_components: str,
    requirements: str,
) -> str:
    """Get prompt for generating execution plan."""
    return GENERATE_PLAN_PROMPT.format(
        operation=operation,
        intent=intent,
        risk=risk,
        complexity=complexity,
        affected_components=affected_components,
        requirements=requirements,
    )
