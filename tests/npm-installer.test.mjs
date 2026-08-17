import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const testDirectory = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(testDirectory, "..");
const installer = path.join(repositoryRoot, "bin", "install.js");

function makeTemporaryCodexHome() {
  return mkdtempSync(path.join(os.tmpdir(), "codebase-learning-installer-"));
}

function runInstaller(...arguments_) {
  return spawnSync(process.execPath, [installer, ...arguments_], {
    cwd: repositoryRoot,
    encoding: "utf8",
  });
}

function runNpm(...arguments_) {
  const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";
  return spawnSync(npmCommand, arguments_, {
    cwd: repositoryRoot,
    encoding: "utf8",
    shell: process.platform === "win32",
  });
}

test("installs only the skill payload into a new Codex home", () => {
  const codexHome = makeTemporaryCodexHome();

  try {
    const result = runInstaller("--codex-home", codexHome);
    const destination = path.join(codexHome, "skills", "codebase-learning");

    assert.equal(result.status, 0, result.stderr);
    assert.equal(existsSync(path.join(destination, "SKILL.md")), true);
    assert.equal(existsSync(path.join(destination, "agents", "openai.yaml")), true);
    assert.equal(existsSync(path.join(destination, "references", "workflow-state.md")), true);
    assert.equal(existsSync(path.join(destination, "scripts", "validate_course.py")), true);
    assert.equal(existsSync(path.join(destination, "README.md")), false);
    assert.equal(existsSync(path.join(destination, "package.json")), false);
  } finally {
    rmSync(codexHome, { force: true, recursive: true });
  }
});

test("requires explicit force before replacing an installed skill", () => {
  const codexHome = makeTemporaryCodexHome();
  const destination = path.join(codexHome, "skills", "codebase-learning");

  try {
    mkdirSync(destination, { recursive: true });
    writeFileSync(path.join(destination, "keep.txt"), "keep this file", "utf8");

    const refused = runInstaller("--codex-home", codexHome);
    assert.equal(refused.status, 2);
    assert.equal(readFileSync(path.join(destination, "keep.txt"), "utf8"), "keep this file");

    const replaced = runInstaller("--codex-home", codexHome, "--force");
    assert.equal(replaced.status, 0, replaced.stderr);
    assert.equal(existsSync(path.join(destination, "SKILL.md")), true);
    assert.equal(existsSync(path.join(destination, "keep.txt")), false);
  } finally {
    rmSync(codexHome, { force: true, recursive: true });
  }
});

test("declares an npm package with a single installer command", () => {
  const packageJson = JSON.parse(readFileSync(path.join(repositoryRoot, "package.json"), "utf8"));

  assert.equal(packageJson.name, "@shuaibilx/codebase-learning");
  assert.equal(packageJson.bin["codebase-learning"], "bin/install.js");
  assert.equal(packageJson.scripts["test:npm-installer"], "node --test tests/npm-installer.test.mjs");
});

test("excludes Python bytecode caches from the npm package", () => {
  const result = runNpm("pack", "--dry-run", "--json");

  assert.equal(result.status, 0, result.stderr);
  const packedFiles = JSON.parse(result.stdout)[0].files.map((file) => file.path);
  assert.equal(packedFiles.some((file) => file.includes("__pycache__") || file.endsWith(".pyc")), false);
});

test("npm exec installs the Skill from the packed archive", () => {
  const packResult = runNpm("pack", "--json");
  assert.equal(packResult.status, 0, packResult.stderr);
  const archiveName = JSON.parse(packResult.stdout)[0].filename;
  const archivePath = path.join(repositoryRoot, archiveName);
  const codexHome = makeTemporaryCodexHome();

  try {
    const installResult = runNpm(
      "exec",
      "--yes",
      `--package=./${archiveName}`,
      "--",
      "codebase-learning",
      "--codex-home",
      codexHome,
    );

    assert.equal(installResult.status, 0, installResult.stderr);
    assert.equal(existsSync(path.join(codexHome, "skills", "codebase-learning", "SKILL.md")), true);
  } finally {
    rmSync(archivePath, { force: true });
    rmSync(codexHome, { force: true, recursive: true });
  }
});
