# Codebase Learning

`codebase-learning` turns a real repository into a source-grounded, resumable learning course. It maps the repository, lets the learner choose a track, creates one verified Module at a time, and keeps every explanation and Demo linked to real source evidence.

The Skill is beginner-friendly by default: it defines unfamiliar terms, explains dense syntax, and requires detailed teaching comments in generated Demo code.

## Install in Codex

### Install from npm

After the package has been published, install the Skill globally with:

```shell
npx @shuaibilx/codebase-learning
```

The installer places only the Skill payload in `~/.codex/skills/codebase-learning`; it does not copy this repository's npm metadata or README into the installed Skill.

To replace an existing installation deliberately:

```shell
npx @shuaibilx/codebase-learning -- --force
```

To target a different Codex home directory:

```shell
npx @shuaibilx/codebase-learning -- --codex-home "/path/to/.codex"
```

Restart Codex after installation. If npm reports a `404` error, the package has not yet been published under this name; use the GitHub installation method below.

### Install directly from GitHub

In Codex, ask the built-in installer to install the Skill from `shuaibilx/codebase-learning`. This route needs no npm publication and is the recommended option while developing the Skill.

## Publish the npm package

The npm installer is included in this repository but is not published automatically. Publishing changes the public npm registry, so run these commands only from an npm account that owns the `@shuaibilx` scope:

```shell
npm login
npm run test:npm-installer
npm run pack:check
npm publish --access public
```

Before the first publication, choose and add an appropriate license. If the npm account uses a different scope, change the `name` field in `package.json`, then update the commands in this README to match. npm does not allow publishing a second package with the same name and version, so increase `version` before every later release.

## Develop and verify

The repository uses no npm runtime dependencies. Run the npm installer tests with:

```shell
npm run test:npm-installer
```

Preview the exact package contents without publishing:

```shell
npm pack --dry-run
```

The Skill itself includes Python helpers and their test suite. Run the repository checks appropriate to your environment before publishing.

## Repository layout

```text
SKILL.md                 Skill instructions and state-machine workflow
agents/openai.yaml       Codex UI metadata and default prompt
references/              Detailed workflow and artifact contracts
scripts/                 Inventory and course-validation helpers
bin/install.js           npm command that installs the Skill payload
tests/                   Regression tests for helpers and the npm installer
```
