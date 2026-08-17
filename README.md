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

## License

This project is licensed under the [MIT License](LICENSE).
