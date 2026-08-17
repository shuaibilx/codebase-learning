# Codebase Learning

`codebase-learning` turns a real repository into a source-grounded, resumable learning course for Codex.

It is beginner-friendly by default. It defines unfamiliar terms, explains dense syntax, and creates detailed teaching comments in generated Demo code.

## What It Does

- Maps the repository into a source-linked learning course under `code-analysis/`.
- Lets you choose a learning track based on the actual codebase.
- Creates and verifies one Module at a time, so the course can be resumed safely.
- Links explanations, notebooks, and minimal Demos back to real source files and symbols.
- Preserves production source code: course artifacts are written only under `code-analysis/`.

## Install

Install the Skill globally for Codex:

```shell
npx @shuaibilx/codebase-learning
```

To update an existing installation:

```shell
npx @shuaibilx/codebase-learning -- --force
```

Restart Codex after installation.

## Use It in Codex

Open the repository you want to learn, then ask Codex:

```text
Use $codebase-learning to create a source-grounded learning course for this repository.
```

Codex will first map the project and present source-derived learning tracks. It will wait for your approval before creating a roadmap or advancing to the next Module.

## What Codex Creates

Course artifacts are created at `code-analysis/` in the root of the repository being studied. The Skill does not modify production source code, dependencies, lockfiles, or project configuration.

Creation is deliberately staged: Orientation creates the shared course files first. After you approve a roadmap, Codex creates only the current Module. Future Modules remain roadmap entries until you explicitly choose to advance.

```mermaid
flowchart TD
    R["Repository being studied"] --> C["code-analysis/"]
    C --> O["Orientation artifacts\nstate, inventory, overview"]
    C --> M["Current Module only\nREADME, notebooks, and Demos"]
    O --> T["Choose a learning track"]
    T --> G["Approve the roadmap"]
    G --> M
```

### Example Output

For this `codebase-learning` repository, one possible source-derived course could look like this. The actual Module and Lesson names always come from the repository and selected learning track.

```text
codebase-learning/                     # The repository being studied
└── code-analysis/                     # Generated course artifacts
    ├── .codebase-learning/            # Machine-readable course state
    ├── README.md                      # Course home, progress, and navigation
    ├── 01-course-workflow-and-gates/  # Example: the current Module
        ├── README.md                  # Module guide and source evidence
        ├── notebook/
        └── demo/
    └── 02-.../                        # Created only after you choose to advance
```

The `01-course-workflow-and-gates/` directory above is only an example. It appears only after roadmap approval, and its exact name and contents depend on the selected learning path and the source code.

### Visual Guides in the Course

The generated course chooses the clearest Markdown-friendly visual for the relationship being taught. Mermaid is one option, not the default for every topic:

- An annotated directory tree explains hierarchy and file ownership.
- A Markdown table compares responsibilities or maps Lessons, Demos, and source symbols.
- A Mermaid flowchart, sequence, state, class, or ER diagram explains a relationship that is easier to follow visually.
- A Mermaid flowchart with labelled subgraphs can show swimlanes when responsibilities cross people, services, or system layers.
- A repository image or small accessible SVG is used only when text-based visuals cannot explain the source-grounded concept clearly.

Every visual has one teaching purpose and is accompanied by explanation and source evidence. The course uses a visual only when it improves understanding.

## License

This project is licensed under the [MIT License](LICENSE).
