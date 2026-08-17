# Visualization Routing

Use this reference whenever a course artifact could be clearer with a visual. Choose the smallest Markdown-friendly representation that answers the learner's question. Do not add a visual merely because the artifact has a section for one.

## Selection guide

| Learner needs to understand | Prefer | Notes |
|---|---|---|
| Directory or component hierarchy | Annotated text tree | Show only learning-relevant paths and responsibilities. |
| Exact mappings, comparisons, or many-to-many links | Markdown table | Use source paths and symbols in the table when relevant. |
| A short linear execution trace | Numbered trace or compact table | Prefer this over a diagram when there is no branching. |
| Branching control flow or component topology | Mermaid flowchart | Keep labels short and put detail in surrounding prose. |
| Request/response, callbacks, or asynchronous ordering | Mermaid sequence diagram | Name participants from source evidence. |
| Legal states and transitions | Mermaid state diagram | Include only states that affect the Lesson. |
| Ownership across users, services, layers, or processes | Swimlane diagram | Use a Mermaid flowchart with labelled `subgraph` lanes, or a table when the handoffs are simple. |
| Classes, interfaces, or inheritance | Mermaid class diagram | Do not reproduce every class; show the relationship being taught. |
| Entities, schemas, and cardinality | Mermaid ER diagram or schema table | Prefer a table when field-level detail matters more than relationships. |
| Time-bound phases or milestones | Timeline, Gantt diagram, or milestone table | Use a table if the renderer may not support the Mermaid diagram type. |
| A visual already present in the repository | Source image, screenshot, or checked-in diagram | Inspect it first, cite its relative source path, and include meaningful alt text. |
| A spatial relationship that text-based forms cannot convey | Small accessible SVG | Write it under the current course artifact directory, add alt text and a caption, and keep it source-grounded. |

## Shared rules

1. Start with the learner question, not the preferred syntax. Use prose alone for a single fact or simple one-step action.
2. Give each visual one job. Do not repeat the same relationship in a global README, project overview, Module README, and Lesson notebook.
3. Place a concise caption or explanation immediately before or after the visual. State what the learner should notice.
4. Support every project-specific claim with repository-relative source paths and symbols. Label inferred relationships as `inferred`.
5. Keep diagrams small. Split an overloaded diagram into two focused visuals or replace it with a table and prose.
6. Use accessible labels and alt text. Do not encode meaning with color alone.
7. Use only course-owned generated SVG files under `code-analysis/`. Never write visual assets into production source trees.
8. Do not generate decorative raster images, logos, avatars, or stock art. They do not establish source evidence.

## Artifact responsibilities

| Artifact | Primary visual purpose | Do not duplicate |
|---|---|---|
| Global `code-analysis/README.md` | Course sequence, dependencies, and progress | Runtime architecture |
| `00-project-overview.md` | System boundaries, runtime architecture, and core call chains | Every Module's internal flow |
| Module `README.md` | The current Module's control flow, ownership, or data flow | The global course roadmap |
| Lesson notebook | One focused mechanism or state transition | The full Module architecture |
| Demo `README.md` | Inputs, outputs, retained mechanism, or a short execution trace | Production architecture omitted from the Demo |

## Mermaid-specific guidance

- Use Mermaid only when its syntax matches the relationship. Mermaid is suitable for flowcharts, sequences, states, classes, ER relationships, and swimlanes built with labelled subgraphs.
- Keep every Mermaid code fence paired and labels consistent with the surrounding prose.
- Prefer a Markdown table or text tree when the reader needs precise labels, dense attributes, or easy copy-and-search behavior.
- If a renderer cannot support a Mermaid diagram type, fall back to a Markdown table, numbered trace, or accessible SVG rather than leaving an unreadable fence.
