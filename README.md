AutoDevAI Development Log – Day 1
1. Designed the project architecture

Instead of writing one large script, I designed AutoDevAI as a modular system.

AutoDevAI/
├── core/
│   ├── repository.py
│   ├── indexer.py
│   ├── graph.py
│   ├── parsers/
│   └── ai.py
│
├── agent/
│
├── prompts/
│
├── repos/
│
├── logs/
│
└── main.py

Each module has one responsibility, making the system scalable and maintainable.

2. Built a Repository Scanner

Created a scanner that recursively walks through an entire project.

It automatically:

discovers every file
detects programming language
reads file contents
stores metadata

Example:

Website/

index.html
style.css
script.js
auth.py
README.md

↓

becomes

Repository

Files

Language

Contents

Path

This is the raw knowledge base for the AI.

3. Built a Repository Indexer

The scanner only reads files.

The Indexer understands them.

For every file it extracts:

file size
line count
imports
functions
classes
exports

Then stores everything inside structured Python dataclasses.

4. Built language-specific parsers

Instead of treating every file as text, I created dedicated parsers.

Python Parser

Finds

imports
functions
classes
JavaScript Parser

Finds

imports
exports
functions
classes

Supports:

JavaScript
TypeScript
React JSX
React TSX
HTML Parser

Parses:

HTML
embedded CSS
embedded JavaScript

Extracts

imports
JavaScript functions
HTML elements
IDs
CSS classes

This allows AutoDevAI to understand single-file web pages.

CSS Parser

Extracts

selectors
CSS variables
animations
media queries
IDs
classes

Preparing the AI to reason about styling relationships.

5. Built common parser utilities

Instead of repeating code in every parser, I centralized shared metadata creation.

Every parser now returns the same data structure.

This keeps the architecture consistent.

6. Built the Repository Graph

This is the biggest architectural milestone.

Instead of storing isolated files, the system now builds relationships.

It creates indexes for:

Functions

↓

File

Classes

↓

File

Selectors

↓

File

Variables

↓

File

Imports

↓

File

Reverse Imports

↓

Files using it

This allows instant lookups without AI.

7. Built a Dependency Graph

Created graph utilities capable of answering questions like

Which file defines this function?

Which files import this module?

Where is this class located?

using simple graph lookups.

No LLM required.

8. Fixed duplicate relationship bug

Found and corrected a graph issue where repeated HTML elements produced duplicate graph edges.

Example

Before

div

↓

index.html

↓

index.html

↓

index.html

After

div

↓

index.html

The graph now stores unique relationships.

9. Built a Repository Inspector

Instead of printing raw Python objects, I created a professional debugging dashboard.

It reports

Repository Summary

total files
total lines
total size
language breakdown

Graph Summary

functions
classes
selectors
variables
imports
graph nodes
graph edges

Indexes

function index
class index
selector index
HTML IDs
CSS variables
animations
import graph
reverse import graph

Query demonstrations

showing that graph lookups work correctly.

10. Connected the AI

Connected Python to a locally running Ollama server.

Architecture

Python

↓

Ollama HTTP API

↓

Qwen2.5-Coder 14B

↓

AI Response

The AI can now be called programmatically instead of manually chatting with it.

This becomes the reasoning engine of AutoDevAI.

Current Architecture
                AutoDevAI

                      │
                      ▼
          Repository Scanner
                      │
                      ▼
          Language Detection
                      │
                      ▼
         Language-specific Parsers
     (Python / JS / HTML / CSS)
                      │
                      ▼
          Repository Indexer
                      │
                      ▼
          Dependency Graph
                      │
                      ▼
        Repository Inspector
                      │
                      ▼
             Ollama AI Engine
What this means

At the start of today, AutoDevAI could only ask an AI a question.

By the end of today, it can:

Read an entire repository.
Understand multiple programming languages.
Extract code structure.
Build searchable indexes.
Build dependency relationships.
Query the codebase without using AI.
Feed structured context into a local LLM.
Progress

If we think of AutoDevAI as a complete autonomous software engineer:

Architecture         ██████████ 100%
Repository Scanner   ██████████ 100%
Language Parsers     ████████░░  85%
Repository Index     ██████████ 100%
Dependency Graph     █████████░  95%
Repository Inspector ██████████ 100%
AI Integration       ███████░░░  70%
Planner Agent        ░░░░░░░░░░   0%
Coder Agent          ░░░░░░░░░░   0%
Reviewer Agent       ░░░░░░░░░░   0%
Relationship Builder ░░░░░░░░░░   0%
Git Automation       ░░░░░░░░░░   0%


AutoDevAI Development Log – Day 2

Current Architecture
                     AutoDevAI
                          │
                          ▼
                Repository Scanner
                          │
                          ▼
               Language Detection
                          │
                          ▼
            Language-specific Parsers
      (Python / JavaScript / HTML / CSS)
                          │
                          ▼
               Repository Indexer
                          │
                          ▼
                Dependency Graph
                          │
                          ▼
              Relationship Builder   ⭐ NEW
                          │
                          ▼
                  Query Engine        ⭐ NEW
                          │
                          ▼
              Repository Inspector
                          │
                          ▼
                 Ollama AI Engine
What We Built Today
1. Fixed the entire HTML metadata pipeline ✅

At the beginning of today your inspector looked like this:

Selectors      : 0
IDs            : 0
CSS Classes    : 0
Variables      : 0
Animations     : 0
Media Queries  : 0
Elements       : 0

We traced the bug through the whole pipeline.

HTML Parser
      ↓
Indexer
      ↓
Dependency Graph
      ↓
Inspector

The problem wasn't main.py.

It was upstream.

HTML Parser

We upgraded it to extract

HTML Elements
IDs
CSS Classes
External CSS
External JS
Inline CSS
Inline JavaScript

instead of only JavaScript.

CSS Parser

This became a surprisingly large task.

We fixed

Regex grabbing CSS declarations
Encoded SVG garbage
@keyframes parsing
@media parsing
Nested braces
Comments
Duplicate selectors

Instead of relying on regex alone we ended up writing a small lexer that walks through the CSS one character at a time.

That makes the parser much more reliable.

Metadata Pipeline

Now the pipeline successfully propagates

HTML

↓

elements

↓

Dependency Graph

↓

Inspector

and

CSS

↓

selectors
variables
animations
media queries

↓

Dependency Graph

↓

Inspector
2. Repository Graph became much richer ✅

Before

Functions

↓

Files

Now

Functions

Classes

Selectors

Variables

Animations

Media Queries

HTML Elements

IDs

CSS Classes

↓

Files

The graph now understands much more of the repository.

3. Built the Relationship Builder ⭐⭐⭐⭐⭐

This was the biggest feature of the day.

Before today the Dependency Graph only answered

Where is this function?

Where is this class?

Which file imports this?

Those are indexes.

Today we built something different.

Relationship Graph

Instead of

Function

↓

File

we now have semantic relationships.

Current relationship types

HTML Element

↓

USES_CLASS

↓

CSS Class
HTML ID

↓

USES_ID

↓

CSS ID
CSS Selector

↓

STYLES

↓

HTML
File

↓

IMPORTS

↓

Module/File

And placeholders for future intelligence

CALLS_FUNCTION

CALLS

REFERENCES

USES_CLASS (JavaScript)

DOM References

These are ready to activate once the parsers become smarter.

RelationshipGraph

We built an entirely new graph.

It stores

Relationship

source

relation

target

source_file

Example

hero

↓

USES_CLASS

↓

.hero

or

.hero

↓

STYLES

↓

hero

This graph exists alongside the Dependency Graph.

Relationship Queries

It supports

by_source()

by_target()

by_relation()

by_file()

making relationship lookups extremely fast.

4. Relationship Inspector

main.py now prints

Relationship Summary

USES_CLASS

USES_ID

STYLES

IMPORTS

CALLS

REFERENCES

CALLS_FUNCTION

along with sample relationships.

This gives immediate visual verification that the graph is correct.

5. Built the Public Query Engine ⭐⭐⭐⭐⭐

This is probably the best architectural decision of the day.

Instead of future AI agents doing this

DependencyGraph

↓

functions

↓

selectors

↓

imports

↓

relationships

they now call

core/queries.py

Functions include

find_html_for_selector()

find_elements_using_selector()

find_files_using_class()

find_style_chain()

find_functions_called_by()

find_call_chain()

find_import_chain()

find_all_dependencies()

find_related_files()

The Planner will never need to know how the graphs are implemented internally.

Current Relationship Output

Your repository now reports

Total Relationships : 206

USES_CLASS      : 89
USES_ID         : 18
STYLES          : 98
IMPORTS         : 1
CALLS_FUNCTION  : 0
CALLS           : 0
REFERENCES      : 0

That is expected.

The remaining zeros are not bugs—they're waiting for richer parser data.

Bugs Solved Today

We fixed several important issues:

✅ HTML parser wasn't exposing elements, IDs, or CSS classes.
✅ CSS parser wasn't integrated into the HTML parser.
✅ clean_metadata() failed on lists containing dictionaries.
✅ Duplicate metadata handling for complex objects.
✅ CSS selector extraction capturing encoded SVG data and declaration blocks.
✅ Regex-based parsing replaced with a lexer-based approach for selectors.
✅ CSS classes renamed consistently (classes → css_classes) across the pipeline.
✅ Relationship Builder correctly producing STYLES relationships.
Current Project Status
Architecture          ██████████ 100%

Repository Scanner    ██████████ 100%

Repository Index      ██████████ 100%

Python Parser         █████████░  90%

JavaScript Parser     █████████░  90%

HTML Parser           ██████████ 100%

CSS Parser            ██████████ 100%

Dependency Graph      ██████████ 100%

Relationship Builder  █████████░  90%

Query Engine          ██████████ 100%

Repository Inspector  ██████████ 100%

Ollama Integration    ███████░░░  70%

Planner Agent         ░░░░░░░░░░   0%

Coder Agent           ░░░░░░░░░░   0%

Reviewer Agent        ░░░░░░░░░░   0%

Git Automation        ░░░░░░░░░░   0%

# AutoDevAI Development Log – Day 3

---

# Current Architecture

```text
                         AutoDevAI
                              │
                              ▼
                    Repository Scanner
                              │
                              ▼
                   Language Detection
                              │
                              ▼
               Language-specific Parsers
         (Python / JavaScript / HTML / CSS)
                              │
                              ▼
                   Repository Indexer
                              │
                              ▼
                    Dependency Graph
                              │
                              ▼
                  Relationship Builder
                              │
                              ▼
                   Repository Reasoning ⭐ NEW
                              │
                              ▼
                 Repository Intelligence ⭐ NEW
                              │
                              ▼
                     Public Query Engine
                              │
                              ▼
                     Context Builder ⭐ NEW
                              │
                              ▼
                     Prompt Builder ⭐ NEW
                              │
                              ▼
                        Model Layer ⭐ NEW
                              │
                              ▼
                     AI Orchestrator ⭐ NEW
                              │
                              ▼
                   Logging & Debug Layer ⭐ NEW
                              │
                              ▼
                      Future AI Agents
```

---

# What We Built Today

---

# 1. Upgraded Every Language Parser into a Static Analyzer ⭐⭐⭐⭐⭐

Today wasn't about adding more regex.

It was about making every parser understand relationships.

## JavaScript

We transformed the JavaScript parser into a real static analyzer.

It now detects

* Function Call Graph
* DOM References
* Event Listeners
* classList Operations
* Module Symbol Usage
* Object Method Calls

Examples

```javascript
login();
```

↓

```
CALLS_FUNCTION
```

---

```javascript
document.querySelector(".card")
```

↓

```
DOM Reference
```

---

```javascript
btn.addEventListener("click", save)
```

↓

```
EVENT_BINDS
```

---

```javascript
classList.add("active")
```

↓

```
MODIFIES_CLASS
```

---

```javascript
import { save } from "./db"
```

↓

```
Module Symbol Usage
```

The parser now resolves

* aliases
* destructuring
* namespace imports
* optional chaining
* chained method calls

instead of only extracting names.

---

## Python

The Python parser also became much smarter.

It now extracts

* Function Call Graph
* Class Inheritance
* Method Relationships
* Decorators
* Imported Symbol Usage

Instead of simply recording

```
class User
```

it now understands

```
User

↓

inherits

↓

BaseModel
```

and

```
User.login()

↓

calls

↓

User.load_profile()
```

---

## HTML

HTML now understands

* Inline Events
* Forms
* Semantic Attributes
* Assets

instead of only elements.

---

## CSS

CSS intelligence expanded with

* Variable Usage Graph
* Selector Specificity
* Pseudo Selectors
* Theme Detection

Instead of storing CSS,

it now understands CSS.

---

# 2. Repository Reasoning Layer ⭐⭐⭐⭐⭐

Until yesterday the project stored facts.

Today it started reasoning.

A completely new package was built:

```
core/reasoning/
```

Algorithms include

* Dead Code Detection
* Unused Imports
* Unused Exports
* Dependency Trees
* Reverse Dependency Trees
* Circular Dependency Detection
* Impact Analysis
* Architecture Rule Validation
* Feature Ownership
* Duplicate Utility Detection

Instead of asking

```
Where is login()?
```

the system can now answer

```
What breaks if I rename login()?
```

or

```
Which files are no longer used?
```

This is a huge architectural jump.

---

# 3. Repository Intelligence ⭐⭐⭐⭐⭐

We added another entirely new layer.

```
core/intelligence.py
```

Instead of storing graph data,

it understands the repository.

It can now detect

* MVC Architecture
* React/Vue Components
* Express Routes
* Flask/FastAPI Endpoints
* Configuration Files
* Entry Points
* Build Systems
* Package Managers
* Testing Frameworks
* Deployment Files

It also generates

```
Repository Profile
```

which summarizes

* architecture
* frameworks
* languages
* project structure
* routes
* entry points
* major features

This becomes the executive summary for AI.

---

# 4. Public Query Engine became the AI SDK ⭐⭐⭐⭐⭐

Yesterday it was mostly graph wrappers.

Today it became the official API for the AI.

New high-level queries include

```
search_symbol()

find_component()

find_references()

find_definitions()

find_owner()

dependency_tree()

impact_analysis()

find_dead_code()

build_repository_profile()

summarize_repository()

detect_project_structure()
```

The AI never touches

* graphs
* parsers
* reasoning
* intelligence

Everything flows through

```
core/queries.py
```

This abstraction is one of the most important architectural decisions so far.

---

# 5. Built the AI Pipeline ⭐⭐⭐⭐⭐

This is the biggest feature of Day 3.

We separated the AI into clean layers.

---

## Context Builder

```
core/context_builder.py
```

Uses only

```
queries.*
```

It builds request-aware context including

* repository profile
* relevant symbols
* definitions
* references
* owners
* dependency tree
* impact analysis
* related files

It also adds

* relevance scoring
* keyword extraction
* caching
* context trimming
* token budgeting

---

## Prompt Builder

```
core/prompt_builder.py
```

Instead of concatenating strings,

it builds structured prompts.

Supports modes

* Planner
* Coder
* Reviewer
* Tester

Supports output formats

* Text
* Markdown
* JSON
* Patch
* Diff

It also reports prompt statistics.

---

## Model Layer

```
core/model.py
```

A production-grade Ollama client.

Features

* Model configuration
* Streaming
* Retries
* Timeout
* Health checks
* Model listing
* Chat API
* JSON generation
* Statistics
* Latency tracking
* Retry/backoff

Most importantly,

the AI no longer knows anything about Ollama.

Only the model layer does.

---

## AI Orchestrator

```
core/ai.py
```

Contains almost no business logic.

Pipeline

```
Request

↓

Context Builder

↓

Prompt Builder

↓

Model

↓

Response
```

Exactly how it should be.

---

# 6. Added AI Debugging & Logging ⭐⭐⭐⭐

A completely new debugging layer was added.

```
core/logger.py
```

The AI now supports

```
debug=True
```

which exposes

* Context
* Prompt
* Prompt Statistics
* Model Statistics
* Response Metadata

It also supports request logging

```
logs/

↓

timestamp.json
```

Every request can now be replayed and analyzed later.

This will be invaluable when debugging future AI agents.

---

# 7. Massive Architectural Cleanup

One of today's biggest achievements wasn't new features—

it was enforcing clean boundaries.

The architecture now follows a strict separation of concerns.

```
Repository

↓

Parsers

↓

Repository Index

↓

Dependency Graph

↓

Relationship Graph

↓

Reasoning

↓

Intelligence

↓

Queries

↓

Context Builder

↓

Prompt Builder

↓

Model

↓

AI
```

Each layer has exactly one responsibility.

That makes future development significantly easier.

---

# Bugs Solved Today

We resolved a large number of architectural and parser issues.

✅ JavaScript alias resolution for destructured imports.

✅ Optional chaining support.

✅ Namespace import handling.

✅ DOM reference extraction.

✅ Event listener resolution.

✅ Object method call detection.

✅ Module symbol usage tracking.

✅ CSS variable usage graph.

✅ CSS selector specificity calculation.

✅ Theme detection.

✅ Python decorator extraction.

✅ Python inheritance graph.

✅ Python imported symbol usage.

✅ Query API expanded to hide graph internals.

✅ AI pipeline refactored into clean layers.

✅ Prompt generation redesigned.

✅ Context builder caching and trimming.

✅ Model retry/backoff handling.

✅ AI request logging and debug tracing.

---

# Current Project Status

```
Architecture              ██████████ 100%

Repository Scanner        ██████████ 100%

Repository Index          ██████████ 100%

Python Parser             ██████████ 100%

JavaScript Parser         ██████████ 100%

HTML Parser               ██████████ 100%

CSS Parser                ██████████ 100%

Dependency Graph          ██████████ 100%

Relationship Builder      ██████████ 100%

Repository Reasoning      ██████████ 100%

Repository Intelligence   ██████████ 100%

Query Engine              ██████████ 100%

Context Builder           ██████████ 100%

Prompt Builder            ██████████ 100%

Model Layer               ██████████ 100%

AI Orchestrator           ██████████ 100%

Logging & Debugging       ██████████ 100%

Planner Agent             ░░░░░░░░░░   0%

Coder Agent               ░░░░░░░░░░   0%

Reviewer Agent            ░░░░░░░░░░   0%

Tester Agent              ░░░░░░░░░░   0%

Git Automation            ░░░░░░░░░░   0%

Browser Automation        ░░░░░░░░░░   0%

Vision Analysis           ░░░░░░░░░░   0%
```

---

# Where AutoDevAI Stands After Day 3

By the end of Day 3, AutoDevAI is no longer just a repository inspector. It has evolved into a layered AI platform capable of understanding a codebase, reasoning about relationships and dependencies, summarizing architecture, retrieving only relevant context, constructing optimized prompts, interacting with a language model through a provider abstraction, and tracing every AI request through structured logging and debugging. The next milestone—**the Planner Agent**—will be the first component that uses this entire foundation to make autonomous engineering decisions rather than simply answering questions.
