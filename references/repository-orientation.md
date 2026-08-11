# Repository Orientation

Use this reference for first-run mapping, monorepo scoping, and source refreshes.

## Contents

- Establish scope
- Build the inventory
- Perform layered semantic analysis
- Write the overview
- Complete the Orientation Gate

## Establish scope

1. Resolve the repository root from Git metadata, workspace context, or the nearest project manifests.
2. Read applicable instruction files before other work.
3. Identify workspaces, applications, packages, generated trees, vendored code, binaries, fixtures, and external submodules.
4. If several independent applications make “the project” ambiguous, inventory their top-level boundaries, set `awaiting_scope`, ask the user to select scope, and stop.
5. Exclude `code-analysis/` from every scan to prevent recursive self-analysis.

Never read or reproduce secret values. The inventory helper records recognized secret-bearing paths as metadata-only exclusions; safe `.env` templates remain eligible for inventory. Treat unrecognized credentials, dumps, and personal data the same way during manual analysis: record only safe path, size/category, and exclusion reason.

## Build the inventory

Prefer the bundled helper:

```text
python <skill-dir>/scripts/repo_inventory.py <repo-root> --output <repo-root>/code-analysis/.codebase-learning/inventory.json
```

For a confirmed monorepo scope, keep the positional root at the course/repository root, add `--scope <repo-relative-path>`, and keep the canonical output at the top level:

```text
python <skill-dir>/scripts/repo_inventory.py <repo-root> --scope apps/api --output <repo-root>/code-analysis/.codebase-learning/inventory.json
```

The helper prefers Git's tracked-plus-untracked, ignore-aware file set and falls back to a pruned filesystem walk only when Git is unavailable or the root is not a Git repository. It records the normalized `scope`, keeps every file path relative to the repository root, excludes common generated/vendor trees, and never follows symlink, junction, or reparse-point directories. It content-fingerprints ordinary included files; recognized sensitive, binary, oversized, or special files are represented with safe metadata and an exclusion reason rather than read as source text. Do not infer semantics from a content hash or metadata-only entry.

`--scope` must be an existing, normalized repo-relative POSIX directory that does not cross an excluded tree or link/reparse boundary. The output must remain inside the explicit repository root; the helper writes it atomically. Operational Git/filesystem failures and file-limit failures are explicit and must not overwrite a previous good inventory. Require inventory `scope` to equal `selected_scope`, or `.` when no scope is selected.

If it exits with `file_limit_exceeded`, do not silently accept a partial inventory. Narrow an ambiguous scope or intentionally raise `--max-files` after estimating cost. If Python is unavailable, reproduce these rules with Git-aware listing and fast filesystem search, and document the fallback. The canonical inventory includes `schema_version`, root `.`, `scope`, source identity, a scope-bound aggregate fingerprint, summary counts, ordinary file records, and metadata-only exclusions.

Separate these coverage concepts:

- `inventoried`: safely enumerated project-owned files.
- `semantically_inspected`: files actually read enough to support a responsibility or behavior claim.
- `excluded`: generated, vendored, recognized sensitive, binary, oversized, or out-of-scope paths with reasons; metadata-only entries are not semantically inspected.
- `unknown`: files whose role cannot yet be supported by evidence.

Never claim every inventoried file was deeply understood.

## Perform layered semantic analysis

Use three passes:

1. **System map:** read manifests, official project README files, entrypoints, workspace definitions, dependency/config files, test layout, CI, and deployment definitions.
2. **Component map:** identify maintained source domains, public boundaries, data stores, external integrations, and cross-component imports or calls.
3. **Critical paths:** trace representative runtime paths from entrypoint to core behavior, including important branches, errors, persistence, and tests.

Support each behavior claim with evidence containing:

- repository-relative path;
- symbol, route, schema, or configuration key;
- line range when useful;
- evidence type `direct` or `inferred`;
- confidence or unresolved question when inference is non-trivial.

Use relative POSIX paths. Prefer symbol plus line range because line numbers alone drift.

## Write the overview

Use the exact headings in [artifact-templates.md](artifact-templates.md). Keep diagram roles distinct:

- Global README: curriculum dependency and progress diagram.
- `00-project-overview.md`: system runtime architecture and major call chains.
- Module README: internal control/data flow for that Module.
- Notebook: a diagram only when it materially clarifies one Lesson.

For at most 400 project-owned files, include an annotated learning tree and a concise responsibility table in the overview. Above that threshold:

- keep an annotated component-level tree in the overview;
- create `00-file-index.md` for the exhaustive human-readable path inventory;
- assign detailed responsibilities only to semantically inspected files;
- group repetitive fixtures/generated families and label them accurately instead of fabricating per-file meaning.

Generate Track options dynamically from evidence. Examples such as frontend, backend, Agent, data, or DevOps are categories, not a fixed menu. Include a Track only when the repository contains meaningful learning material for it.

## Complete the Orientation Gate

Require all of the following before setting `awaiting_track`:

- scope and source identity recorded;
- inventory completed without silent truncation;
- exclusions, unknowns, and coverage counts disclosed;
- project purpose and technology composition supported by source evidence;
- important directories/files explained at the appropriate scale;
- runtime architecture and one or more core call chains explained with Mermaid and prose;
- entrypoints, tests, configuration, and external boundaries identified;
- repository-derived Track options listed;
- README projection synchronized with canonical state.

Then ask the user which detected Track to learn and stop. Do not plan Modules during Orientation.
