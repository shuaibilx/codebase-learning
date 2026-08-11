# Module Authoring

Use this reference to build, teach, verify, or repair the current Module.

## Contents

- Module structure
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

## README contract

Answer all of these with project evidence:

- What problem does this Module solve, and why does this project need it?
- Where are its entrypoints, boundaries, critical symbols, and tests?
- Who calls it, what does it call, and how do data/control/errors flow?
- Why does it appear at this point in the roadmap?
- Which Lessons and Demos teach its mechanisms?
- What must the learner be able to explain or change to finish?

Include a Module-level Mermaid control/data-flow diagram plus prose. Add a Lesson mapping table with columns `lesson_id`, Notebook, Demo(s), source evidence, and relationship notes.

## Lesson notebook contract

Teach a concept extracted from the Module, not a paraphrase of a whole source file. Include:

1. learning objective and prerequisite;
2. the mechanism and why it exists;
3. a traced project flow with source evidence;
4. the main branch plus important error/edge paths;
5. common misconception or design tradeoff;
6. a compact source excerpt only when it materially helps;
7. a comparison to the linked Demo;
8. one or more self-check questions or exercises;
9. an exit criterion.

Use Mermaid only when a diagram makes this single Lesson clearer.

## Demo contract

Extract a minimal reproducible teaching model from real source. Preserve the core mechanism and explicitly document simplifications.

Every Demo must:

- name its `lesson_id` and source symbols;
- retain the project's decisive control/data flow;
- remove tracing, retry, middleware, persistence, or integration detail only when incidental to the Lesson;
- explain why important lines exist using clear Chinese comments unless the user asks for another language;
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
3. Check Mermaid fences and diagram labels for consistency with prose.
4. Run each safe Demo command and focused test in the project's existing environment.
5. Record exact commands, exit codes, date/time, and relevant results in state and the Demo README.
6. Run `validate_course.py` or the manual equivalent.

If a runtime, dependency, credential, network service, or upstream test failure blocks execution, record `verification.status` as `blocked` or `failed`. Do not claim the Demo is runnable or the Module verified.

If any artifact covered by a passed verification must change, start a new Module attempt first: increment `module_revision` and reset verification evidence. For a Module after the first, record fresh explicit `advance` authority for the new tuple before returning it to `building`. Re-run the full Gate for that revision. Any `learner_completion`, `skip`, or `advance` event bound to an earlier revision or roadmap version is historical only.
