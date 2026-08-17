---
name: codebase-learning
description: Create and advance a source-grounded, resumable learning curriculum for an existing codebase. Use for course-style whole-repository learning, analysis, or explanation, including continuing an existing curriculum. Do not use for routine reviews, fixes, feature work, one-file explanations, or generic tutorials.
---

# Codebase Learning

Turn a real repository into a gated course whose scope, order, explanations, and demos remain traceable to that repository.

## Preserve these invariants

- Treat project source as the authority for project behavior and curriculum boundaries. Use general knowledge only to explain concepts; never use it to invent project behavior.
- Use these terms consistently: **Track** is the user-selected learning direction, **Module** is an ordered course unit, **Lesson** is a knowledge point inside a module, and **Demo** is a lesson-linked minimal implementation.
- Default to beginner-friendly teaching unless the user asks for a compact or advanced style. Define unfamiliar terms before using them, unpack dense syntax, and give generated Demo code detailed teaching comments that explain intent, inputs, outputs, control flow, state changes, and important failure cases. Write all course artifacts, teaching prose, and generated code comments in English.
- Write course artifacts only under `code-analysis/`. Do not modify production source, dependencies, lockfiles, or project configuration unless the user separately asks.
- Keep exactly one canonical machine state at `code-analysis/.codebase-learning/state.json`. Keep `code-analysis/README.md` as its human-readable projection and navigation entry.
- Generate content for only the current Module. Keep future Modules as roadmap entries; do not create their directories or lesson content.
- Distinguish artifact completion from learning completion. Codex may mark artifacts verified; only the user's explicit confirmation may mark a Module completed.
- Give every Module a positive integer `module_revision`, starting at `1`. Treat `(roadmap_version, module_id, module_revision)` as the exact Module-attempt identity; never let a confirmation for an older route or attempt authorize the current one.
- Require explicit user approval for the Track, roadmap, learner completion, and next-Module transition. Treat an unambiguous request to continue as approval only when exactly one legal transition exists.
- Use repository-relative POSIX paths in artifacts. Never persist machine-specific absolute paths, credentials, tokens, `.env` contents, or private data.
- Treat `code-analysis/` as a hard write boundary. Reject symlink, junction, or other reparse-point components in that artifact tree; never follow one to read or write outside the repository.
- Preserve user edits in an existing `code-analysis/`; patch or merge them instead of silently regenerating files.
- Support non-Git projects and missing optional tools through documented fallbacks.

## Start or resume safely

1. Locate the repository root and read all applicable repository instructions such as `AGENTS.md` before scanning or writing.
2. Read [workflow-state.md](references/workflow-state.md) completely.
3. Before reading or inspecting anything under `code-analysis/`, use non-following metadata checks on that directory, `.codebase-learning/`, and the intended state/README paths. If any component is a symlink, junction, or reparse point, do not follow it; enter `blocked` outside that unsafe tree and report the boundary violation.
4. If `code-analysis/.codebase-learning/state.json` exists and the path checks pass, run the course validator first, then read the state and `code-analysis/README.md` and reconcile the reported Gate before doing anything else.
5. If a path-safe `code-analysis/` exists without valid state, do not overwrite it. Inspect its artifacts, record `needs_recovery`, and reconstruct only unambiguous state. Ask the user when more than one recovery is plausible.
6. Compare the saved source revision and inventory fingerprint with the current repository. Enter `stale_source` before advancing if relevant source changed.
7. Select the phase below. Do not combine phases across a Stop boundary in one turn.

## Follow the state machine

```text
orienting
  -> awaiting_scope (only for ambiguous monorepos) | awaiting_track
awaiting_scope
  -> orienting (after scope choice; rescan the selected scope)
awaiting_track
  -> planning_route
  -> awaiting_roadmap_confirmation
  -> building_module
  -> verifying_module
  -> awaiting_learner_confirmation
  -> awaiting_advance
  -> building_module | course_complete

side states: stale_source | needs_recovery | blocked
```

### Orient the repository

Read [repository-orientation.md](references/repository-orientation.md) completely.

Create or refresh only:

- `code-analysis/.codebase-learning/state.json`
- `code-analysis/.codebase-learning/inventory.json`
- `code-analysis/README.md`
- `code-analysis/00-project-overview.md`
- `code-analysis/00-file-index.md` only when the human-readable inventory would overwhelm the overview

Complete the Orientation Gate, set `phase` to `awaiting_scope` or `awaiting_track`, present only tracks found in the actual repository, ask the corresponding question, and stop. Do not create a roadmap or Module directory.

If the course is in `awaiting_scope`, treat the user's scope choice as its own Gate. Record a `scope` confirmation bound to the normalized repo-relative `selected_scope`, set `phase` back to `orienting`, rescan only that scope, refresh the inventory, overview, and source-derived Track options, then set `phase` to `awaiting_track`, ask the user to choose a Track, and stop. Reject absolute, escaping, symlinked, or reparse-point scopes. Do not reuse pre-scope Track options or plan the route during this transition.

### Plan the route

After an explicit Track selection, record a `track` confirmation bound to the selected Track and read [curriculum-and-gates.md](references/curriculum-and-gates.md) completely. Derive a dependency graph from source evidence, linearize it into numbered Modules, initialize each new Module with `module_revision: 1`, update only the state and global README, set `phase` to `awaiting_roadmap_confirmation`, ask for approval, and stop. Do not create Module directories yet. Record a `roadmap` confirmation bound to `roadmap_version` only after the user approves that version. On any Track or roadmap replan, increment `roadmap_version` and the revision of every retained Module before requesting approval again; old Module-level confirmations remain history but authorize nothing in the new route.

### Build the current Module

After explicit roadmap approval or a legal next-Module transition, read [module-authoring.md](references/module-authoring.md) completely. Read [artifact-templates.md](references/artifact-templates.md) when creating or repairing files.

1. Set the selected Module to `building` and `phase` to `building_module` before lengthy generation so interrupted work is recoverable.
2. Create only that Module's `README.md`, `notebook/`, and `demo/` artifacts.
3. Preserve the production mechanism while simplifying incidental engineering detail.
4. Run every safe, local Demo verification command. Do not install dependencies or contact external services without user authorization.
5. Set `phase` to `verifying_module`, run the course validator, then record the exact commands, check time, and non-empty result notes.
6. If verification passes, set the Module to `verified`, set `phase` to `awaiting_learner_confirmation`, invite the user to study or ask questions, and stop.
7. If verification cannot pass, keep the Module uncompleted, set `blocked` or retain `building_module` with the reason, report the exact gap, and stop.

### Complete and advance

- In `awaiting_learner_confirmation`, answer questions and revise only the current Module. Before changing any verified artifact, increment that Module's `module_revision`, reset its verification to `not_run`, and re-enter the build-and-verify sequence. For a Module after the first, treat the user's explicit revision request as transition authority and record a fresh `advance` event for the incremented attempt before setting it to `building`; never copy the old event. Return to `awaiting_learner_confirmation` only after the checks pass again. The increment invalidates every earlier completion, skip, or advance event for that attempt. Do not mark it completed until the user explicitly says they finished the current revision.
- On learner confirmation, record a `learner_completion` confirmation bound to the current `roadmap_version`, `module_id`, and `module_revision`, mark the Module `completed`, and update the README projection. If a planned Module remains, set `phase` to `awaiting_advance`, ask whether to enter it, and stop; otherwise set `phase` directly to `course_complete`.
- In `awaiting_advance`, create the next Module only after explicit permission. Record an `advance` confirmation bound to the current `roadmap_version`, the next `module_id`, and that Module's current `module_revision` before changing it to `building`.
- On an explicit skip, record a `skip` confirmation bound to the current `roadmap_version`, that `module_id`, and its current `module_revision`, then mark it `skipped`. Continue to `awaiting_advance` only when a later planned Module remains; otherwise set `phase` directly to `course_complete`.
- Handle rewind, Track change, source drift, and recovery using [workflow-state.md](references/workflow-state.md); never disguise skipped or stale content as completed.

## Select tools by capability

Read [tool-routing.md](references/tool-routing.md) whenever tool availability, repository scale, external research, images, or parallel analysis affects execution. Tool examples are preferences, not dependencies. Keep the main agent as the only writer to `code-analysis/`.

Use the bundled helpers when Python is available:

```text
python <skill-dir>/scripts/repo_inventory.py <repo-root> --output <repo-root>/code-analysis/.codebase-learning/inventory.json
python <skill-dir>/scripts/validate_course.py <repo-root>
```

For a confirmed monorepo scope, keep `<repo-root>` unchanged and add `--scope <repo-relative-path>` to the inventory command. Resolve `<skill-dir>` from this loaded Skill's location; never hardcode an installation path. If a helper is unavailable, perform the same checks manually and record the limitation.

## Finish each turn at a Gate

Before stopping or advancing:

1. Validate artifacts and state.
2. Update the human README projection to match canonical state.
3. Report the current phase, files changed, verification evidence, unresolved uncertainty, and the one user decision required next.
4. Stop. Never cross the next Gate implicitly.
