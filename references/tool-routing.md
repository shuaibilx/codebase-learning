# Tool Routing and Fallbacks

Select tools by capability, not by product-specific namespace. Treat examples as conditional preferences.

| Phase | Required capability | Preferred Codex examples | Optional accelerators | Fallback / constraint |
|---|---|---|---|---|
| Root and inventory | List project-owned files and read metadata | Local shell with `git ls-files`, `rg --files`, bundled inventory script | Semantic code index | Use the host filesystem search; disclose ignore/coverage limits |
| Source tracing | Search symbols/imports and read precise regions | Fast text search such as `rg -n`, file reader, Git history | Knowledge graph or language-server index | Trace manually; keep direct vs inferred evidence explicit |
| Parallel orientation | Analyze independent components | Read-only Codex subagents | Multiple subsystem passes | Work serially; only the main agent writes `code-analysis/` |
| Artifact editing | Create small, reviewable changes | Structured patch editing such as `apply_patch` | Safe workspace editor | Preserve user edits; never rewrite production files implicitly |
| Demo verification | Execute local commands and tests | Codex local shell in the existing project environment | Project-native test runner | If unavailable, record `not_run`/`blocked`; never claim runnable |
| User Gates | Ask one focused decision and wait | Native user-input interaction | None | Ask a concise plain-language question and stop |
| Existing visuals | Inspect checked-in diagrams/screenshots/UI assets | Image inspection such as `view_image` | Browser preview | Skip when irrelevant; do not generate an image for Mermaid |
| External context | Read primary documentation | Codex web search or in-app browser | Documentation connector | Use only when requested or needed; separate external context from source facts and cite it |
| Session progress | Track work within the current turn | A session plan tool | None | Never substitute a session plan for persisted course state |

## Required versus optional

The core workflow requires safe repository reading/search, controlled writes under `code-analysis/`, Demo execution when runnable, and user interaction at Gates. Git, Python, `rg`, structured patching, subagents, semantic indexes, browser/web access, and image inspection are optional implementations or accelerators.

Do not declare optional tools as hard dependencies in `agents/openai.yaml`. Only declare a dependency there when the Skill truly cannot operate without a specific supported MCP service; this Skill has no such dependency.

## Parallel analysis rules

- Delegate only bounded, independent, primarily read-only subsystem scans or independent quality checks.
- Give each subagent the repository scope and requested evidence format, not conclusions to reproduce.
- Require the main agent to verify findings against source and perform all course writes.
- Avoid parallel edits to shared course files and avoid leaking expected forward-test answers.

## External research rules

Keep repository source sufficient for the core workflow. Use external sources only when the user requests them, source comments link to a specification, or dependency behavior cannot be responsibly explained from local code. Prefer official or primary sources, cite links, and label the content “external background.” Never let external material define project behavior or Module boundaries.

## Safety and degradation

- Do not auto-install runtimes or dependencies, modify lockfiles, start paid services, use credentials, or perform network writes merely to verify a Demo.
- Do not fail Orientation solely because an optional accelerator is unavailable.
- When command execution is unavailable, distinguish “documented” from “verified.”
- When an image cannot be inspected, record the limitation instead of inferring its contents.
- When search coverage is incomplete, preserve `unknown` items and ask for scope or access rather than fabricating roles.
