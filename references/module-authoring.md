# Module Authoring

Use this reference to build, teach, verify, or repair the current Module.

## Contents

- Module structure
- Beginner-first teaching contract
- README contract
- Lesson notebook contract
- Demo contract
- Evidence and mapping
- Verification Gate

## Module structure

Before creating or repairing files, confirm that the state has a positive `module_revision` for the current Module. Create only the current numbered directory:

```text
code-analysis/<NN-module-slug>/
├── README.md
├── notebook/
│   └── <NN-lesson-slug>.md
└── demo/
    └── <NN-lesson-slug>/
        ├── README.md
        ├── <minimal runnable source>
        └── <focused test when appropriate>
```

Number Lessons in learning order. Use stable `lesson_id` values such as `01-agent-loop`. Keep Notebook and Demo names aligned when the mapping is one-to-one; use an explicit mapping table for every one-to-many or many-to-one relationship.

## Beginner-first teaching contract

Unless the user asks for a compact or advanced style, assume the learner understands only basic variables, conditions, loops, and functions. Make every artifact usable without requiring them to infer hidden prerequisites.

- Introduce required background before the mechanism and define each unfamiliar project or language term on first use.
- Walk through a concrete input from entrypoint to output. Name the data or state before and after each important step.
- Break dense production excerpts into small logical blocks. Explain compact syntax and language idioms before relying on them.
- Give each non-trivial generated Demo function a learner-facing docstring covering its purpose, parameters, return value, side effects, and expected exceptions when applicable.
- Add comments before every non-obvious block to explain why it exists, what decision it makes, and what changes afterward. Add a short inline comment when a single expression contains syntax a beginner may not recognize.
- Explain common entry guards, context managers, comprehensions, callbacks, decorators, asynchronous control flow, generics, or framework lifecycle hooks the first time they appear.
- Include at least one likely error or edge case and show the learner where to inspect intermediate values when debugging.
- Write all teaching prose and code comments in English.
- Keep comments synchronized with the executable code. Do not inflate comment count by restating obvious assignments or punctuation; move long conceptual explanations into the Notebook or Demo README when that keeps the source easier to follow.

## README contract

Answer all of these with project evidence:

- What problem does this Module solve, and why does this project need it?
- Where are its entrypoints, boundaries, critical symbols, and tests?
- Who calls it, what does it call, and how do data/control/errors flow?
- Why does it appear at this point in the roadmap?
- Which Lessons and Demos teach its mechanisms?
- What must the learner be able to explain or change to finish?

Use [visualization-routing.md](visualization-routing.md) to select a Module-level visual model plus prose. For example, use a control/data-flow diagram, a swimlane diagram, an annotated call trace, or a responsibility table according to the relationship being taught. Add a Lesson mapping table with columns `lesson_id`, Notebook, Demo(s), source evidence, and relationship notes.

## Lesson notebook contract

Teach a concept extracted from the Module, not a paraphrase of a whole source file. Include:

1. learning objective and prerequisite;
2. a short glossary for unfamiliar terms;
3. the mechanism and why it exists;
4. a traced project flow with source evidence;
5. a small-block walkthrough of important code, including input, state change, and output;
6. the main branch plus important error/edge paths and a beginner-friendly debugging hint;
7. common misconception or design tradeoff;
8. a compact source excerpt only when it materially helps;
9. a comparison to the linked Demo;
10. one or more self-check questions or exercises;
11. an exit criterion.

Add a visual only when it makes this single Lesson clearer. Select the representation through `visualization-routing.md`; a state diagram, comparison table, annotated tree, step trace, or source image may be more useful than Mermaid.

## Demo contract

Extract a minimal reproducible teaching model from real source. Preserve the core mechanism and explicitly document simplifications.

Every Demo must:

- name its `lesson_id` and source symbols;
- retain the project's decisive control/data flow;
- remove tracing, retry, middleware, persistence, or integration detail only when incidental to the Lesson;
- follow the beginner-first contract for docstrings and comments, including non-obvious syntax, input/output flow, state changes, entrypoints, and likely failures;
- avoid credentials, private data, network writes, destructive side effects, and implicit package installation;
- run independently with the smallest existing dependency set, or state the exact unavoidable dependency;
- include expected output or assertions and a safe local run command;
- list what was retained, removed, substituted, or mocked and how the Demo differs from production;
- avoid changing the project's dependency files or lockfiles merely to run the Demo.

Treat 50–150 lines as a teaching heuristic, not a rule. Mechanism fidelity takes precedence over line count.

## Evidence and mapping

Use repository-relative POSIX paths and record:

```text
path: src/agent/runtime.py
symbol: AgentRuntime.run
lines: 120-188
evidence: direct
revision: <commit-or-fingerprint>
```

Label a relationship `inferred` when dynamic dispatch, reflection, dependency injection, or missing runtime evidence prevents a direct conclusion. Never silently convert inference into fact.

For each Lesson, map all linked Notebooks and Demos. For each Demo, map all source symbols it compresses. A matching filename alone is not sufficient evidence for a many-to-many mapping.

## Verification Gate

Before setting the Module to `verified`:

1. Confirm the Module README, at least one Notebook Markdown file, and at least one Demo README exist.
2. Check every declared source path and symbol against the current source snapshot.
3. Check each visual for consistency with prose: Mermaid fences parse, tables and trees remain readable, and image or SVG paths, alt text, captions, and source references are valid.
4. Run each safe Demo command and focused test in the project's existing environment.
5. Record exact commands, exit codes, date/time, and relevant results in state and the Demo README.
6. Run `validate_course.py` or the manual equivalent.

If a runtime, dependency, credential, network service, or upstream test failure blocks execution, record `verification.status` as `blocked` or `failed`. Do not claim the Demo is runnable or the Module verified.

If any artifact covered by a passed verification must change, start a new Module attempt first: increment `module_revision` and reset verification evidence. For a Module after the first, record fresh explicit `advance` authority for the new tuple before returning it to `building`. Re-run the full Gate for that revision. Any `learner_completion`, `skip`, or `advance` event bound to an earlier revision or roadmap version is historical only.
