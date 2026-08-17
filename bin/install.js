#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const SKILL_NAME = "codebase-learning";
const PAYLOAD_ENTRIES = ["SKILL.md", "agents", "references", "scripts"];
const PACKAGE_ROOT = path.resolve(__dirname, "..");

function printUsage() {
  console.log(`Usage: codebase-learning [--codex-home <directory>] [--force]\n\nInstalls the Codebase Learning skill into <codex-home>/skills/${SKILL_NAME}.\n\nOptions:\n  --codex-home <directory>  Override CODEX_HOME (default: ~/.codex).\n  --force                   Replace an existing installed skill.\n  --help                    Show this help message.`);
}

function parseArguments(arguments_) {
  const options = {
    codexHome: path.resolve(process.env.CODEX_HOME || path.join(os.homedir(), ".codex")),
    force: false,
  };

  for (let index = 0; index < arguments_.length; index += 1) {
    const argument = arguments_[index];
    if (argument === "--help") {
      options.help = true;
    } else if (argument === "--force") {
      options.force = true;
    } else if (argument === "--codex-home") {
      const value = arguments_[index + 1];
      if (!value || value.startsWith("--")) {
        throw new Error("--codex-home requires a directory path.");
      }
      options.codexHome = path.resolve(value);
      index += 1;
    } else {
      throw new Error(`Unknown option: ${argument}`);
    }
  }

  return options;
}

function assertExistingComponentsAreNotLinks(targetPath) {
  const absolutePath = path.resolve(targetPath);
  const parsedPath = path.parse(absolutePath);
  const components = path.relative(parsedPath.root, absolutePath)
    .split(path.sep)
    .filter(Boolean);
  let currentPath = parsedPath.root;

  for (const component of components) {
    currentPath = path.join(currentPath, component);
    if (!fs.existsSync(currentPath)) {
      continue;
    }
    if (fs.lstatSync(currentPath).isSymbolicLink()) {
      throw new Error(`Refusing to use symbolic-link path component: ${currentPath}`);
    }
  }
}

function copyPayloadEntry(sourcePath, destinationPath) {
  const metadata = fs.lstatSync(sourcePath);
  if (metadata.isSymbolicLink()) {
    throw new Error(`The packaged skill must not contain symbolic links: ${sourcePath}`);
  }

  if (metadata.isFile()) {
    fs.copyFileSync(sourcePath, destinationPath);
    return;
  }

  if (!metadata.isDirectory()) {
    throw new Error(`The packaged skill contains an unsupported file type: ${sourcePath}`);
  }

  fs.mkdirSync(destinationPath);
  for (const childName of fs.readdirSync(sourcePath)) {
    copyPayloadEntry(path.join(sourcePath, childName), path.join(destinationPath, childName));
  }
}

function replaceDestination(stagedSkillPath, destinationPath, force) {
  if (!fs.existsSync(destinationPath)) {
    fs.renameSync(stagedSkillPath, destinationPath);
    return;
  }

  if (!force) {
    throw new Error(`A skill already exists at ${destinationPath}. Re-run with --force to replace it.`);
  }

  const backupPath = path.join(
    path.dirname(destinationPath),
    `.${SKILL_NAME}-backup-${process.pid}-${Date.now()}`,
  );
  fs.renameSync(destinationPath, backupPath);
  try {
    fs.renameSync(stagedSkillPath, destinationPath);
  } catch (error) {
    fs.renameSync(backupPath, destinationPath);
    throw error;
  }
  fs.rmSync(backupPath, { force: true, recursive: true });
}

function installSkill(options) {
  const skillsDirectory = path.join(options.codexHome, "skills");
  const destinationPath = path.join(skillsDirectory, SKILL_NAME);
  const relativeDestination = path.relative(options.codexHome, destinationPath);
  if (relativeDestination.startsWith(`..${path.sep}`) || path.isAbsolute(relativeDestination)) {
    throw new Error("The installation target escapes the requested Codex home.");
  }

  fs.mkdirSync(skillsDirectory, { recursive: true });
  assertExistingComponentsAreNotLinks(options.codexHome);
  assertExistingComponentsAreNotLinks(skillsDirectory);
  assertExistingComponentsAreNotLinks(destinationPath);

  const stagingDirectory = fs.mkdtempSync(path.join(skillsDirectory, `.${SKILL_NAME}-staging-`));
  const stagedSkillPath = path.join(stagingDirectory, SKILL_NAME);
  try {
    fs.mkdirSync(stagedSkillPath);
    for (const entry of PAYLOAD_ENTRIES) {
      const sourcePath = path.join(PACKAGE_ROOT, entry);
      if (!fs.existsSync(sourcePath)) {
        throw new Error(`The packaged skill is missing required entry: ${entry}`);
      }
      copyPayloadEntry(sourcePath, path.join(stagedSkillPath, entry));
    }
    replaceDestination(stagedSkillPath, destinationPath, options.force);
  } finally {
    fs.rmSync(stagingDirectory, { force: true, recursive: true });
  }

  console.log(`Installed ${SKILL_NAME} at ${destinationPath}. Restart Codex to load the skill.`);
}

function main() {
  try {
    const options = parseArguments(process.argv.slice(2));
    if (options.help) {
      printUsage();
      return;
    }
    installSkill(options);
  } catch (error) {
    console.error(`Installation failed: ${error.message}`);
    process.exitCode = 2;
  }
}

main();
