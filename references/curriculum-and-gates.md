# Curriculum Planning and Gates

Use this reference after scope and Track selection, and when revising, skipping, or completing a roadmap.

## Derive the curriculum

1. Filter the inventory to symbols, flows, tests, configuration, and dependencies relevant to the selected Track.
2. Build a dependency DAG from actual source relations: initialization before runtime, interfaces before implementations, producers before consumers, and foundational state before orchestration.
3. Add a small prerequisite only when the learner cannot understand a source-backed Module without it. Label it as explanatory context; do not pretend it is a project component.
4. Linearize the DAG into a strict order. Explain every non-obvious ordering decision.
5. Define each Module with a stable numbered slug, positive integer `module_revision` (initially `1`), learning goal, prerequisites, source areas, critical symbols, exit criteria, and planned Lessons.
6. Prefer coherent mechanisms over arbitrary file boundaries. One Module may span files; one file may support several Modules.

Do not generate a generic technology syllabus and retrofit filenames afterward. Every Module must have enough project evidence to justify its place.

## Write the roadmap

Update canonical state and the global README only. Initialize every new Module with `module_revision: 1`, keep every Module `planned`, keep `current_module` null, and do not create Module directories.

The README must show:

- selected scope and Track;
- source revision/fingerprint summary;
- ordered Module checklist;
- dependency/progress Mermaid diagram;
- one-sentence learning goal and source area for each Module;
- current phase and exact next Gate;
- learning rules, including one-Module-only generation.

Set `phase` to `awaiting_roadmap_confirmation`, show the proposed route, ask the user to approve or revise it, and stop.

## Enforce Gates

| Gate | Required evidence | Transition authority |
|---|---|---|
| Scope | Independent repository roots are identified | User selects scope |
| Track | Dynamic Track options are source-supported | User selects Track |
| Roadmap | Dependency order, coverage, and exit criteria are written | User approves route |
| Module artifact | README, Lessons, mappings, Demos, diagrams, and checks satisfy the contract | Codex verifies artifacts |
| Learner completion | Learner has studied the current Module attempt and explicitly confirms completion | User confirmation bound to current `roadmap_version`, `module_id`, and `module_revision` |
| Advance | Current Module is completed and next is uniquely known | User permission bound to current `roadmap_version`, next `module_id`, and its current `module_revision` |
| Course completion | Every required Module is completed or explicitly skipped | State validator and user record |

Generating files never crosses the Learner completion Gate.

## Revise the route safely

- Increment `roadmap_version` when Module order, membership, or Track changes. Initialize new Modules at revision `1`; increment the prior positive `module_revision` for every retained Module before presenting the revised route.
- Keep old Module-level confirmations as history, but match `learner_completion`, `skip`, and `advance` only on the current `(roadmap_version, module_id, module_revision)` tuple. A prior route or attempt never authorizes the revised roadmap.
- Preserve completed Module history. Mark invalidated reuse as `stale` rather than deleting it.
- Explain source impact before inserting a prerequisite ahead of the current position.
- Record a user-requested skip as `skipped`, with a concise reason and consequence plus the exact current route-and-revision confirmation binding.
- If the user rejects the roadmap, revise only state and README; still do not create Module content.
- If relevant source drift changes dependencies, return to roadmap approval before building additional Modules.

## Define completion

A Module may become `verified` only when its artifacts, mappings, source references, and safe local Demo checks pass. It may become `completed` only after that verification and explicit learner confirmation. The course may become `course_complete` only when no Module remains `planned`, `building`, `verified`, or `stale`.
