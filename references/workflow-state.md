# Workflow State and Recovery

Use this reference to create, resume, transition, repair, or invalidate a course.

## Contents

- Canonical state
- Phase and status contracts
- Safe transition protocol
- Recovery and source drift
- User-directed changes

## Canonical state

Keep machine state in `code-analysis/.codebase-learning/state.json`. Keep the global README as a readable projection; never treat checkboxes alone as authoritative.

Use this shape after Orientation:

```json
{
  "schema_version": 1,
  "skill_version": "1.0.0",
  "repository_root": ".",
  "source": {
    "kind": "git",
    "revision": "<commit-or-unborn-or-unversioned>",
    "dirty": false,
    "inventory_fingerprint": "sha256:<digest>"
  },
  "phase": "awaiting_track",
  "selected_scope": null,
  "selected_track": null,
  "roadmap_version": 0,
  "current_module": null,
  "modules": [],
  "confirmations": [],
  "resume_phase": null,
  "last_error": null
}
```

After route planning, store Modules in dependency order:

```json
{
  "id": "01-agent-runtime",
  "title": "Agent Runtime",
  "module_revision": 1,
  "status": "planned",
  "depends_on": [],
  "source_areas": ["src/agent/runtime.py"],
  "learning_goal": "Explain and trace the runtime loop",
  "verification": {
    "status": "not_run",
    "commands": [],
    "checked_at": null,
    "notes": null
  }
}
```

Summarize confirmations without copying sensitive or unnecessarily long user text. Every event requires a non-empty `at` timestamp and `summary`. Use only the gates `scope`, `track`, `roadmap`, `learner_completion`, `advance`, and `skip`; set `module_id` to `null` for course-level gates and to the affected Module ID for Module-level decisions. Bind `scope` to the selected repo-relative scope, `track` to the selected Track, and a roadmap approval to the exact `roadmap_version`:

```json
{"gate": "roadmap", "roadmap_version": 1, "module_id": null, "at": "2026-01-01T00:00:00Z", "summary": "User approved roadmap v1"}
```

Scope and Track events use the same shape plus their bound value, for example `"scope": "apps/api"` or `"track": "Agent runtime"`.

For a Module decision, bind the evidence to the exact current attempt with all three values: current `roadmap_version`, affected `module_id`, and that Module's current positive integer `module_revision`. Retain older events as history, but never treat them as a match after either version changes:

```json
{"gate": "learner_completion", "roadmap_version": 1, "module_id": "01-agent-runtime", "module_revision": 1, "at": "2026-01-02T00:00:00Z", "summary": "User confirmed Module 01 revision 1 complete"}
```

## Phase and status contracts

Use only these steady or recoverable phases:

| Phase | Required condition | Allowed next action |
|---|---|---|
| `orienting` | Scan is incomplete | Finish Orientation or enter recovery/block |
| `awaiting_scope` | Multiple independent roots remain ambiguous | Record the chosen scope, enter `orienting`, rescan it, refresh Track options, then enter `awaiting_track` |
| `awaiting_track` | Orientation is complete; no Track or Modules exist | Ask user to select a detected Track |
| `planning_route` | Track is selected; route write may be incomplete | Finish or recover route |
| `awaiting_roadmap_confirmation` | All Modules are `planned`; no Module directories exist | Ask user to approve or revise |
| `building_module` | Exactly one Module is `building` and matches `current_module` | Create only its artifacts |
| `verifying_module` | Exactly one current Module is `building`; current artifacts exist and checks are running or incomplete | Finish checks or block |
| `awaiting_learner_confirmation` | Exactly one current Module is `verified` | Teach/revise; await learner completion |
| `awaiting_advance` | Current Module is `completed` or explicitly `skipped`; later Modules remain `planned` | Ask permission for the next Module and bind it to the current route and next Module revision |
| `course_complete` | Every Module is `completed` or explicitly `skipped`; `current_module` is the final Module | Summarize or revise on request |
| `stale_source` | Saved source identity differs in a relevant area | Assess impact before resuming |
| `needs_recovery` | State and artifacts disagree or state is absent | Reconstruct without overwriting |
| `blocked` | A concrete prerequisite prevents a legal transition | Preserve the last consistent state |

Use Module statuses `planned`, `building`, `verified`, `completed`, `skipped`, or `stale`. Never jump directly from `planned` to `completed`.

Keep `module_revision` as a positive integer initialized to `1`, `depends_on` as an array of earlier Module IDs, `source_areas` as non-empty normalized repo-relative POSIX paths, `learning_goal` as a non-empty string, and `verification` in the documented shape. A `passed` verification requires at least one exact non-blank command, a `checked_at` timestamp, and non-empty result notes. Do not treat a state flag as verification evidence.

## Safe transition protocol

1. Validate the current phase and the user's authorization.
2. Write the transitional phase before lengthy work (`orienting`, `planning_route`, `building_module`, or `verifying_module`).
3. Generate artifacts idempotently. Patch existing files and preserve user-authored sections.
4. Run relevant checks and capture exact commands, exit codes, and important output.
5. Update the README projection.
6. Write the final state last so it never claims artifacts or verification that do not exist.
7. Run `validate_course.py` or its manual equivalent.

Any edit to a verified Module artifact creates a new attempt and invalidates its verification and prior Module-level confirmations. Before editing, increment `module_revision` and reset `verification` to `not_run` with empty results. If this is a Module after the first, require explicit user authority for the rebuild and record a fresh `advance` confirmation matching the incremented attempt; the old event cannot cross the Gate. Then change the status to `building`, set `phase` to `building_module`, and rerun all applicable checks before restoring `verified` and `awaiting_learner_confirmation`. Never reuse or decrement a revision, including after an interrupted rebuild.

## Recovery and source drift

- If state is missing but artifacts exist, inventory them, infer only facts that have one interpretation, set `needs_recovery`, and ask about ambiguous progress.
- If a transitional phase remains after interruption, compare declared artifacts with disk. Continue idempotently when safe; otherwise retain `needs_recovery` and explain the mismatch.
- Compare both Git revision and inventory fingerprint. A clean commit alone does not identify uncommitted or non-Git source.
- When source changes, map changed paths to Module `source_areas`. Mark affected Modules and every dependent later Module `stale`; do not delete their materials.
- Refresh Orientation facts incrementally. If the Track or route must change, increment `roadmap_version`; initialize new Modules at revision `1` and increment every retained Module's revision before requesting roadmap approval again. Old Module-level confirmations remain audit history but cannot authorize the new route or attempts.
- Keep user edits. When regeneration conflicts, show or explain the intended merge before replacing substantial learner-authored content.

For `stale_source`, `needs_recovery`, or `blocked`, set `resume_phase` to the non-side phase whose contract still governs the artifacts, and set `last_error` to a concise non-empty reason. Validate the state against that `resume_phase`; the side phase is an overlay, not a way to bypass a Gate. Keep `resume_phase` null in ordinary phases. In `stale_source`, a safely normalized source path that was deleted or renamed is a warning to resolve during impact analysis; unsafe or escaping paths remain errors.

## User-directed changes

- Record `skipped` separately from `completed` and require explicit user intent. Store a `skip` confirmation matching the current `roadmap_version`, affected `module_id`, and current `module_revision`.
- A `completed` Module requires a `learner_completion` confirmation matching the current `roadmap_version`, `module_id`, and `module_revision`; artifact verification is not learner completion.
- After completing or skipping a Module, enter `awaiting_advance` only when a later `planned` Module exists. Otherwise enter `course_complete` directly.
- Before building any Module after the first, require an `advance` confirmation matching the current `roadmap_version`, the next Module's `module_id`, and its current `module_revision`. Roadmap approval authorizes only the first Module build.
- On rewind, retain later artifacts but mark affected Modules `stale` or move the course pointer only after explaining the consequence.
- On Track change, create a new roadmap version and increment retained Module revisions. Reuse prior artifacts only when their source coverage and learning goal remain valid, and never reuse their old user confirmations.
- Treat vague “continue” as authorization only when the state admits exactly one legal transition. Otherwise ask which action the user intends.
