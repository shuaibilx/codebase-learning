#!/usr/bin/env python3
"""Validate codebase-learning state and hard-Gate filesystem invariants."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Any, Optional


STATE_PATH = Path("code-analysis/.codebase-learning/state.json")
INVENTORY_PATH = Path("code-analysis/.codebase-learning/inventory.json")
PHASES = {
    "orienting",
    "awaiting_scope",
    "awaiting_track",
    "planning_route",
    "awaiting_roadmap_confirmation",
    "building_module",
    "verifying_module",
    "awaiting_learner_confirmation",
    "awaiting_advance",
    "course_complete",
    "stale_source",
    "needs_recovery",
    "blocked",
}
SIDE_PHASES = {"stale_source", "needs_recovery", "blocked"}
RESUMABLE_PHASES = PHASES - SIDE_PHASES
MODULE_STATUSES = {"planned", "building", "verified", "completed", "skipped", "stale"}
CONFIRMATION_GATES = {
    "scope",
    "track",
    "roadmap",
    "learner_completion",
    "advance",
    "skip",
}
COURSE_CONFIRMATION_GATES = {"scope", "track", "roadmap"}
MODULE_CONFIRMATION_GATES = {"learner_completion", "advance", "skip"}
VERIFICATION_STATUSES = {"not_run", "running", "passed", "failed", "blocked"}
MODULE_ID_PATTERN = re.compile(r"^[0-9]{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")
FINGERPRINT_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
FILE_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
INVENTORY_EXCLUSION_REASONS = {
    "sensitive_metadata_only",
    "binary_metadata_only",
    "oversized_metadata_only",
    "special_file_metadata_only",
}
DISALLOWED_SCOPE_COMPONENTS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "build",
    "code-analysis",
    "dist",
    "node_modules",
    "target",
    "vendor",
}


def has_confirmation(
    confirmations: list[Any],
    gate: str,
    *,
    module_id: Optional[str] = None,
    roadmap_version: Optional[int] = None,
    module_revision: Optional[int] = None,
    scope: Optional[str] = None,
    track: Optional[str] = None,
) -> bool:
    for confirmation in confirmations:
        if not isinstance(confirmation, dict) or confirmation.get("gate") != gate:
            continue
        if module_id is not None and confirmation.get("module_id") != module_id:
            continue
        if (
            roadmap_version is not None
            and confirmation.get("roadmap_version") != roadmap_version
        ):
            continue
        if (
            module_revision is not None
            and confirmation.get("module_revision") != module_revision
        ):
            continue
        if scope is not None and confirmation.get("scope") != scope:
            continue
        if track is not None and confirmation.get("track") != track:
            continue
        return True
    return False


def is_safe_relative_posix(value: Any, *, allow_dot: bool = False) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        return False
    if value == ".":
        return allow_dot
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value:
        return False
    if any(part in {"", ".."} for part in path.parts):
        return False
    return not path.parts or ":" not in path.parts[0]


def path_stays_within(root: Path, relative_path: str) -> bool:
    candidate = root.joinpath(*PurePosixPath(relative_path).parts)
    try:
        candidate.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def is_link_or_reparse(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(metadata, "st_file_attributes", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(file_attributes & reparse_flag)


def path_has_link_or_reparse(root: Path, relative_path: str) -> bool:
    current = root
    for part in PurePosixPath(relative_path).parts:
        current = current / part
        if is_link_or_reparse(current):
            return True
    return False


def path_belongs_to_scope(relative_path: str, scope: str) -> bool:
    if scope == ".":
        return True
    path_parts = PurePosixPath(relative_path).parts
    scope_parts = PurePosixPath(scope).parts
    return path_parts[: len(scope_parts)] == scope_parts


def compute_inventory_fingerprint(
    files: list[dict[str, Any]],
    excluded_files: list[dict[str, Any]],
    scope: str = ".",
) -> str:
    digest = hashlib.sha256()
    digest.update(b"scope\0")
    digest.update(scope.encode("utf-8", errors="surrogateescape"))
    digest.update(b"\0")
    for entry in sorted(files, key=lambda item: item["path"]):
        digest.update(entry["path"].encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
        digest.update(entry["sha256"].encode("ascii"))
        digest.update(b"\0")
    for entry in sorted(excluded_files, key=lambda item: item["path"]):
        digest.update(entry["path"].encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0metadata-only\0")
        digest.update(entry["reason"].encode("ascii"))
        digest.update(b"\0")
        if "bytes" in entry:
            digest.update(str(entry["bytes"]).encode("ascii"))
            digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def check_module_artifacts(
    analysis: Path, module_id: str, status_label: str, errors: list[str]
) -> None:
    module_dir = analysis / module_id
    notebook_dir = module_dir / "notebook"
    demo_dir = module_dir / "demo"
    if is_link_or_reparse(module_dir):
        errors.append(f"module directory must not be a symlink: {module_id}")
        return
    module_readme = module_dir / "README.md"
    if is_link_or_reparse(module_readme):
        errors.append(f"module README.md must not be a symlink: {module_id}")
    elif not module_readme.is_file():
        errors.append(f"{status_label} module requires README.md: {module_id}")
    if is_link_or_reparse(notebook_dir):
        errors.append(f"module notebook must not be a symlink: {module_id}")
        notebook_files: list[Path] = []
    else:
        notebook_files = [
            path
            for path in notebook_dir.glob("*.md")
            if path.is_file() and not is_link_or_reparse(path)
        ]
    if not notebook_files:
        errors.append(
            f"{status_label} module requires at least one notebook Markdown file: "
            f"{module_id}"
        )
    demo_readmes: list[Path] = []
    if is_link_or_reparse(demo_dir):
        errors.append(f"module demo must not be a symlink: {module_id}")
    elif demo_dir.is_dir():
        for child in demo_dir.iterdir():
            if is_link_or_reparse(child):
                errors.append(
                    f"module demo child must not be a symlink: {module_id}/{child.name}"
                )
                continue
            readme = child / "README.md"
            if is_link_or_reparse(readme):
                errors.append(
                    f"demo README.md must not be a symlink: {module_id}/{child.name}"
                )
            elif readme.is_file():
                demo_readmes.append(readme)
                implementation_files = [
                    path
                    for path in child.iterdir()
                    if path.name.lower() != "readme.md"
                    and path.is_file()
                    and not is_link_or_reparse(path)
                ]
                if not implementation_files:
                    errors.append(
                        f"{status_label} module demo requires a non-README "
                        f"implementation artifact: {module_id}/{child.name}"
                    )
    if not demo_readmes:
        errors.append(
            f"{status_label} module requires at least one demo README.md: {module_id}"
        )


def validate_course(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    analysis = root / "code-analysis"
    state_path = root / STATE_PATH
    inventory_path = root / INVENTORY_PATH
    inventory: Any = None
    inventory_scope: Any = None
    inventory_scope_valid = False

    if is_link_or_reparse(analysis):
        return {
            "valid": False,
            "errors": ["code-analysis must not be a symlink"],
            "warnings": warnings,
        }
    control_dir = analysis / ".codebase-learning"
    if is_link_or_reparse(control_dir):
        return {
            "valid": False,
            "errors": ["code-analysis/.codebase-learning must not be a symlink"],
            "warnings": warnings,
        }

    analysis_readme = analysis / "README.md"
    overview = analysis / "00-project-overview.md"
    if is_link_or_reparse(analysis_readme):
        errors.append("code-analysis/README.md must not be a symlink")
    elif not analysis_readme.is_file():
        errors.append("missing code-analysis/README.md")
    if is_link_or_reparse(overview):
        errors.append("code-analysis/00-project-overview.md must not be a symlink")
    elif not overview.is_file():
        errors.append("missing code-analysis/00-project-overview.md")
    if is_link_or_reparse(inventory_path):
        errors.append(f"{INVENTORY_PATH.as_posix()} must not be a symlink")
    elif not inventory_path.is_file():
        errors.append(f"missing {INVENTORY_PATH.as_posix()}")
    else:
        try:
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            errors.append(f"invalid inventory JSON: {error}")
        else:
            if not isinstance(inventory, dict):
                errors.append("inventory JSON root must be an object")
                inventory = None
            else:
                if inventory.get("schema_version") != 1:
                    errors.append(
                        "unsupported inventory schema_version: "
                        f"{inventory.get('schema_version')}"
                    )
                if inventory.get("root") != ".":
                    errors.append("inventory root must be '.'")
                inventory_scope = inventory.get("scope")
                if (
                    not is_safe_relative_posix(inventory_scope, allow_dot=True)
                    or any(
                        part in DISALLOWED_SCOPE_COMPONENTS
                        for part in PurePosixPath(inventory_scope).parts
                    )
                    or not path_stays_within(root, inventory_scope)
                    or path_has_link_or_reparse(root, inventory_scope)
                ):
                    errors.append(
                        "inventory scope must be a normalized repo-relative POSIX path"
                    )
                elif not root.joinpath(
                    *PurePosixPath(inventory_scope).parts
                ).is_dir():
                    errors.append("inventory scope must identify an existing directory")
                else:
                    inventory_scope_valid = True
                inventory_source = inventory.get("source")
                if not isinstance(inventory_source, dict):
                    errors.append("inventory source must be an object")
                else:
                    for key in ("kind", "revision"):
                        if (
                            not isinstance(inventory_source.get(key), str)
                            or not inventory_source.get(key)
                        ):
                            errors.append(
                                f"inventory source.{key} must be a non-empty string"
                            )
                    if inventory_source.get("kind") not in {"git", "filesystem"}:
                        errors.append(
                            "inventory source.kind must be 'git' or 'filesystem'"
                        )
                    if not isinstance(inventory_source.get("dirty"), bool):
                        errors.append("inventory source.dirty must be a boolean")
                fingerprint = inventory.get("fingerprint")
                if not isinstance(fingerprint, str) or not FINGERPRINT_PATTERN.fullmatch(
                    fingerprint
                ):
                    errors.append("inventory fingerprint must be a sha256 string")
                if not isinstance(inventory.get("summary"), dict):
                    errors.append("inventory summary must be an object")
                inventory_files = inventory.get("files")
                if not isinstance(inventory_files, list):
                    errors.append("inventory files must be an array")
                    inventory_files = []
                inventory_excluded = inventory.get("excluded_files")
                if not isinstance(inventory_excluded, list):
                    errors.append("inventory excluded_files must be an array")
                    inventory_excluded = []
                inventory_paths: set[str] = set()
                inventory_entry_error_count = len(errors)
                for index, entry in enumerate(inventory_files):
                    if not isinstance(entry, dict):
                        errors.append(
                            f"inventory file at index {index} must be an object"
                        )
                        continue
                    path_value = entry.get("path")
                    if not is_safe_relative_posix(path_value) or not path_stays_within(
                        root, path_value
                    ) or path_has_link_or_reparse(root, path_value):
                        errors.append(
                            "inventory file path must be repo-relative POSIX: "
                            f"{path_value}"
                        )
                    elif PurePosixPath(path_value).parts[:1] == ("code-analysis",):
                        errors.append(
                            "inventory file path must exclude code-analysis: "
                            f"{path_value}"
                        )
                    elif isinstance(inventory_scope, str) and not path_belongs_to_scope(
                        path_value, inventory_scope
                    ):
                        errors.append(
                            "inventory file path is outside inventory scope: "
                            f"{path_value}"
                        )
                    if isinstance(path_value, str):
                        if path_value in inventory_paths:
                            errors.append(f"duplicate inventory path: {path_value}")
                        inventory_paths.add(path_value)
                    byte_count = entry.get("bytes")
                    if (
                        not isinstance(byte_count, int)
                        or isinstance(byte_count, bool)
                        or byte_count < 0
                    ):
                        errors.append(f"inventory file bytes is invalid: {path_value}")
                    digest = entry.get("sha256")
                    if not isinstance(digest, str) or not FILE_DIGEST_PATTERN.fullmatch(
                        digest
                    ):
                        errors.append(f"inventory file sha256 is invalid: {path_value}")
                for index, entry in enumerate(inventory_excluded):
                    if not isinstance(entry, dict):
                        errors.append(
                            f"inventory excluded file at index {index} must be an object"
                        )
                        continue
                    path_value = entry.get("path")
                    if not is_safe_relative_posix(path_value) or not path_stays_within(
                        root, path_value
                    ) or path_has_link_or_reparse(root, path_value):
                        errors.append(
                            "inventory excluded path must be repo-relative POSIX: "
                            f"{path_value}"
                        )
                    elif PurePosixPath(path_value).parts[:1] == ("code-analysis",):
                        errors.append(
                            "inventory excluded path must exclude code-analysis: "
                            f"{path_value}"
                        )
                    elif isinstance(inventory_scope, str) and not path_belongs_to_scope(
                        path_value, inventory_scope
                    ):
                        errors.append(
                            "inventory excluded path is outside inventory scope: "
                            f"{path_value}"
                        )
                    if isinstance(path_value, str):
                        if path_value in inventory_paths:
                            errors.append(f"duplicate inventory path: {path_value}")
                        inventory_paths.add(path_value)
                    reason = entry.get("reason")
                    if (
                        not isinstance(reason, str)
                        or reason not in INVENTORY_EXCLUSION_REASONS
                    ):
                        errors.append(
                            "inventory excluded reason is invalid: "
                            f"{path_value} -> {reason}"
                        )
                    if "bytes" in entry:
                        byte_count = entry.get("bytes")
                        if (
                            not isinstance(byte_count, int)
                            or isinstance(byte_count, bool)
                            or byte_count < 0
                        ):
                            errors.append(
                                f"inventory excluded bytes is invalid: {path_value}"
                            )
                if (
                    inventory_scope_valid
                    and len(errors) == inventory_entry_error_count
                ):
                    expected_fingerprint = compute_inventory_fingerprint(
                        inventory_files, inventory_excluded, inventory_scope
                    )
                    if inventory.get("fingerprint") != expected_fingerprint:
                        errors.append(
                            "inventory fingerprint does not match its entries"
                        )
                summary = inventory.get("summary")
                if isinstance(summary, dict):
                    expected_summary = {
                        "included_files": len(inventory_files),
                        "metadata_only_files": len(inventory_excluded),
                        "sensitive_metadata_files": sum(
                            isinstance(entry, dict)
                            and entry.get("reason") == "sensitive_metadata_only"
                            for entry in inventory_excluded
                        ),
                    }
                    for key, expected_value in expected_summary.items():
                        if summary.get(key) != expected_value:
                            errors.append(
                                f"inventory summary.{key} does not match "
                                f"{'files' if key == 'included_files' else 'excluded_files'}"
                            )
    if is_link_or_reparse(state_path):
        errors.append(f"{STATE_PATH.as_posix()} must not be a symlink")
    elif not state_path.is_file():
        errors.append(f"missing {STATE_PATH.as_posix()}")
    else:
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            errors.append(f"invalid state JSON: {error}")
        else:
            if not isinstance(state, dict):
                errors.append("state JSON root must be an object")
                return {"valid": False, "errors": errors, "warnings": warnings}
            if state.get("schema_version") != 1:
                errors.append(f"unsupported schema_version: {state.get('schema_version')}")
            skill_version = state.get("skill_version")
            if not isinstance(skill_version, str) or not skill_version:
                errors.append("skill_version must be a non-empty string")
            if state.get("repository_root") != ".":
                errors.append("repository_root must be '.'")
            roadmap_version = state.get("roadmap_version")
            roadmap_version_valid = (
                isinstance(roadmap_version, int)
                and not isinstance(roadmap_version, bool)
                and roadmap_version >= 0
            )
            if not roadmap_version_valid:
                errors.append("roadmap_version must be a non-negative integer")
            raw_confirmations = state.get("confirmations")
            if not isinstance(raw_confirmations, list):
                errors.append("confirmations must be an array")
                confirmations: list[Any] = []
            else:
                confirmations = []
                for index, confirmation in enumerate(raw_confirmations):
                    event_valid = True
                    if not isinstance(confirmation, dict):
                        errors.append(f"confirmation at index {index} must be an object")
                        continue
                    gate = confirmation.get("gate")
                    if not isinstance(gate, str):
                        errors.append(
                            f"confirmation at index {index} requires a string gate"
                        )
                        event_valid = False
                    elif gate not in CONFIRMATION_GATES:
                        errors.append(
                            f"unknown confirmation gate at index {index}: {gate}"
                        )
                        event_valid = False
                    if (
                        not isinstance(confirmation.get("at"), str)
                        or not confirmation.get("at").strip()
                    ):
                        errors.append(
                            f"confirmation at index {index} requires a non-empty at timestamp"
                        )
                        event_valid = False
                    if (
                        not isinstance(confirmation.get("summary"), str)
                        or not confirmation.get("summary").strip()
                    ):
                        errors.append(
                            f"confirmation at index {index} requires a non-empty summary"
                        )
                        event_valid = False
                    if isinstance(gate, str) and gate in COURSE_CONFIRMATION_GATES and (
                        "module_id" not in confirmation
                        or confirmation.get("module_id") is not None
                    ):
                        errors.append(
                            f"{gate} confirmation at index {index} requires module_id=null"
                        )
                        event_valid = False
                    if isinstance(gate, str) and gate in MODULE_CONFIRMATION_GATES and (
                        not isinstance(confirmation.get("module_id"), str)
                        or not MODULE_ID_PATTERN.fullmatch(
                            confirmation.get("module_id", "")
                        )
                    ):
                        errors.append(
                            f"{gate} confirmation at index {index} requires a valid module_id"
                        )
                        event_valid = False
                    if isinstance(gate, str) and gate in MODULE_CONFIRMATION_GATES:
                        confirmed_version = confirmation.get("roadmap_version")
                        if (
                            not isinstance(confirmed_version, int)
                            or isinstance(confirmed_version, bool)
                            or confirmed_version < 0
                        ):
                            errors.append(
                                f"{gate} confirmation at index {index} requires a "
                                "non-negative roadmap_version"
                            )
                            event_valid = False
                        confirmed_revision = confirmation.get("module_revision")
                        if (
                            not isinstance(confirmed_revision, int)
                            or isinstance(confirmed_revision, bool)
                            or confirmed_revision <= 0
                        ):
                            errors.append(
                                f"{gate} confirmation at index {index} requires a "
                                "positive module_revision"
                            )
                            event_valid = False
                    if gate == "roadmap":
                        confirmed_version = confirmation.get("roadmap_version")
                        if (
                            not isinstance(confirmed_version, int)
                            or isinstance(confirmed_version, bool)
                            or confirmed_version < 0
                        ):
                            errors.append(
                                "roadmap confirmation at index "
                                f"{index} requires a non-negative roadmap_version"
                            )
                            event_valid = False
                    if gate == "scope" and (
                        not isinstance(confirmation.get("scope"), str)
                        or not confirmation.get("scope").strip()
                    ):
                        errors.append(
                            f"scope confirmation at index {index} requires a non-empty scope"
                        )
                        event_valid = False
                    if gate == "track" and (
                        not isinstance(confirmation.get("track"), str)
                        or not confirmation.get("track").strip()
                    ):
                        errors.append(
                            f"track confirmation at index {index} requires a non-empty track"
                        )
                        event_valid = False
                    if event_valid:
                        confirmations.append(confirmation)
            phase = state.get("phase")
            if not isinstance(phase, str):
                errors.append(f"phase must be a known string: {phase}")
                phase_name: Optional[str] = None
            elif phase not in PHASES:
                errors.append(f"unknown phase: {phase}")
                phase_name = None
            else:
                phase_name = phase
            source_identity_differs = False
            source = state.get("source")
            if not isinstance(source, dict):
                errors.append("source must be an object")
            else:
                for key in ("kind", "revision", "inventory_fingerprint"):
                    if not isinstance(source.get(key), str) or not source.get(key):
                        errors.append(f"source.{key} must be a non-empty string")
                if source.get("kind") not in {"git", "filesystem"}:
                    errors.append("source.kind must be 'git' or 'filesystem'")
                if not isinstance(source.get("dirty"), bool):
                    errors.append("source.dirty must be a boolean")
                if inventory is not None:
                    inventory_source = inventory.get("source")
                    if isinstance(inventory_source, dict):
                        for key in ("kind", "revision", "dirty"):
                            if source.get(key) != inventory_source.get(key):
                                source_identity_differs = True
                                message = (
                                    f"state source {key} does not match "
                                    f"inventory source {key}"
                                )
                                (
                                    warnings
                                    if phase_name == "stale_source"
                                    else errors
                                ).append(message)
                    if source.get("inventory_fingerprint") != inventory.get(
                        "fingerprint"
                    ):
                        source_identity_differs = True
                        message = (
                            "state source fingerprint does not match inventory fingerprint"
                        )
                        (
                            warnings if phase_name == "stale_source" else errors
                        ).append(message)
            if phase_name == "stale_source" and not source_identity_differs:
                errors.append("stale_source requires a source identity difference")
            selected_scope = state.get("selected_scope")
            if selected_scope is not None:
                if not is_safe_relative_posix(
                    selected_scope, allow_dot=True
                ) or any(
                    part in DISALLOWED_SCOPE_COMPONENTS
                    for part in PurePosixPath(selected_scope).parts
                ) or not path_stays_within(
                    root, selected_scope
                ) or path_has_link_or_reparse(root, selected_scope):
                    errors.append(
                        "selected_scope must be a normalized repo-relative POSIX path"
                    )
                elif not (root.joinpath(*PurePosixPath(selected_scope).parts)).is_dir():
                    errors.append("selected_scope must identify an existing directory")
                if not has_confirmation(
                    confirmations, "scope", scope=selected_scope
                ):
                    errors.append(
                        "selected scope requires a matching scope confirmation"
                    )
            expected_inventory_scope = selected_scope or "."
            if (
                isinstance(expected_inventory_scope, str)
                and inventory_scope != expected_inventory_scope
            ):
                errors.append(
                    "inventory scope does not match selected_scope: "
                    f"{inventory_scope} != {expected_inventory_scope}"
                )
            selected_track = state.get("selected_track")
            if selected_track is not None and (
                not isinstance(selected_track, str) or not selected_track.strip()
            ):
                errors.append("selected_track must be null or a non-empty string")
            current_module = state.get("current_module")
            if current_module is not None and (
                not isinstance(current_module, str)
                or not MODULE_ID_PATTERN.fullmatch(current_module)
            ):
                errors.append("current_module must be null or a valid module id")
            last_error = state.get("last_error")
            if last_error is not None and not isinstance(last_error, str):
                errors.append("last_error must be null or a string")
            resume_phase = state.get("resume_phase")
            if phase_name in SIDE_PHASES:
                if not isinstance(last_error, str) or not last_error.strip():
                    errors.append(f"{phase_name} requires a non-empty last_error")
                if not isinstance(resume_phase, str) or resume_phase not in RESUMABLE_PHASES:
                    errors.append(f"{phase_name} requires a resumable resume_phase")
            elif resume_phase is not None:
                errors.append("resume_phase must be null outside a side phase")
            effective_phase = (
                resume_phase
                if phase_name in SIDE_PHASES
                and isinstance(resume_phase, str)
                and resume_phase in RESUMABLE_PHASES
                else phase_name
            )

            if effective_phase == "awaiting_scope":
                if selected_scope is not None:
                    errors.append("awaiting_scope requires selected_scope to be null")
                if selected_track is not None:
                    errors.append("awaiting_scope requires selected_track to be null")
                if current_module is not None:
                    errors.append("awaiting_scope requires current_module to be null")
                if state.get("modules") != []:
                    errors.append("awaiting_scope requires modules to be empty")
            if effective_phase == "awaiting_track":
                if state.get("selected_track") is not None:
                    errors.append("awaiting_track requires selected_track to be null")
                if state.get("current_module") is not None:
                    errors.append("awaiting_track requires current_module to be null")
                if state.get("modules") != []:
                    errors.append("awaiting_track requires modules to be empty")
            if effective_phase == "planning_route":
                if current_module is not None:
                    errors.append("planning_route requires current_module to be null")
            if effective_phase == "awaiting_roadmap_confirmation":
                if state.get("current_module") is not None:
                    errors.append(
                        "awaiting_roadmap_confirmation requires current_module to be null"
                    )
            track_selected_phases = {
                "planning_route",
                "awaiting_roadmap_confirmation",
                "building_module",
                "verifying_module",
                "awaiting_learner_confirmation",
                "awaiting_advance",
                "course_complete",
            }
            if effective_phase in track_selected_phases:
                if not isinstance(selected_track, str) or not selected_track.strip():
                    errors.append(
                        f"{effective_phase} requires a non-empty selected_track"
                    )
                elif not has_confirmation(
                    confirmations, "track", track=selected_track
                ):
                    errors.append("selected Track requires a track confirmation")

            modules = state.get("modules")
            if not isinstance(modules, list):
                errors.append("modules must be an array")
            if isinstance(modules, list):
                if effective_phase == "planning_route" and any(
                    not isinstance(module, dict)
                    or module.get("status") != "planned"
                    for module in modules
                ):
                    errors.append("planning_route allows only planned modules")
                if effective_phase == "awaiting_roadmap_confirmation":
                    if not modules:
                        errors.append(
                            "awaiting_roadmap_confirmation requires at least one module"
                        )
                    if any(
                        not isinstance(module, dict)
                        or module.get("status") != "planned"
                        for module in modules
                    ):
                        errors.append(
                            "awaiting_roadmap_confirmation requires every module to be planned"
                        )
                if effective_phase == "course_complete" and (
                    not modules
                    or any(
                        not isinstance(module, dict)
                        or not isinstance(module.get("status"), str)
                        or module.get("status") not in {"completed", "skipped"}
                        for module in modules
                    )
                ):
                    errors.append(
                        "course_complete requires every module to be completed or skipped"
                    )
                unfinished_seen = False
                valid_module_ids: set[str] = set()
                earlier_module_ids: set[str] = set()
                ordered_modules: list[dict[str, Any]] = []
                for position, module in enumerate(modules, start=1):
                    if not isinstance(module, dict):
                        errors.append(f"module at position {position} must be an object")
                        continue
                    ordered_modules.append(module)
                    module_id = module.get("id")
                    status = module.get("status")
                    valid_module_id = isinstance(
                        module_id, str
                    ) and MODULE_ID_PATTERN.fullmatch(module_id)
                    if not valid_module_id:
                        errors.append(f"invalid module id: {module_id}")
                    else:
                        if module_id in valid_module_ids:
                            errors.append(f"duplicate module id: {module_id}")
                        valid_module_ids.add(module_id)
                    if not isinstance(module.get("title"), str) or not module.get(
                        "title"
                    ).strip():
                        errors.append(f"module requires a non-empty title: {module_id}")
                    status_valid = isinstance(status, str) and status in MODULE_STATUSES
                    if not status_valid:
                        errors.append(f"unknown module status for {module_id}: {status}")
                    module_revision = module.get("module_revision")
                    module_revision_valid = (
                        isinstance(module_revision, int)
                        and not isinstance(module_revision, bool)
                        and module_revision > 0
                    )
                    if not module_revision_valid:
                        errors.append(
                            "module_revision must be a positive integer: "
                            f"{module_id}"
                        )
                    depends_on = module.get("depends_on")
                    if not isinstance(depends_on, list):
                        errors.append(f"module depends_on must be an array: {module_id}")
                    else:
                        seen_dependencies: set[str] = set()
                        for dependency in depends_on:
                            if not isinstance(dependency, str):
                                errors.append(
                                    "module dependency must be a module id string: "
                                    f"{module_id} -> {dependency}"
                                )
                                continue
                            if dependency in seen_dependencies:
                                errors.append(
                                    f"duplicate module dependency: {module_id} -> {dependency}"
                                )
                            seen_dependencies.add(dependency)
                            if dependency not in earlier_module_ids:
                                errors.append(
                                    "module dependency must reference an earlier module: "
                                    f"{module_id} -> {dependency}"
                                )
                    source_areas = module.get("source_areas")
                    if not isinstance(source_areas, list) or not source_areas:
                        errors.append(
                            f"module source_areas must be a non-empty array: {module_id}"
                        )
                    else:
                        for source_area in source_areas:
                            if (
                                not is_safe_relative_posix(source_area)
                                or PurePosixPath(source_area).parts[:1]
                                == ("code-analysis",)
                                or not path_stays_within(root, source_area)
                                or path_has_link_or_reparse(root, source_area)
                            ):
                                errors.append(
                                    "module source_area must be repo-relative POSIX: "
                                    f"{module_id} -> {source_area}"
                                )
                                continue
                            if (
                                isinstance(inventory_scope, str)
                                and not path_belongs_to_scope(
                                    source_area, inventory_scope
                                )
                            ):
                                errors.append(
                                    "module source_area is outside inventory scope: "
                                    f"{module_id} -> {source_area}"
                                )
                                continue
                            source_path = root.joinpath(
                                *PurePosixPath(source_area).parts
                            )
                            if not source_path.exists():
                                message = (
                                    "module source_area does not exist: "
                                    f"{module_id} -> {source_area}"
                                )
                                (
                                    warnings
                                    if phase_name == "stale_source"
                                    else errors
                                ).append(message)
                    learning_goal = module.get("learning_goal")
                    if not isinstance(learning_goal, str) or not learning_goal.strip():
                        errors.append(
                            f"module learning_goal must be a non-empty string: {module_id}"
                        )
                    verification = module.get("verification")
                    if not isinstance(verification, dict):
                        errors.append(f"module verification must be an object: {module_id}")
                    else:
                        verification_status = verification.get("status")
                        if (
                            not isinstance(verification_status, str)
                            or verification_status not in VERIFICATION_STATUSES
                        ):
                            errors.append(
                                "module verification.status is invalid: "
                                f"{module_id} -> {verification_status}"
                            )
                        commands = verification.get("commands")
                        commands_valid = isinstance(commands, list) and not any(
                            not isinstance(command, str) for command in commands
                        )
                        if not commands_valid:
                            errors.append(
                                "module verification.commands must be an array of strings: "
                                f"{module_id}"
                            )
                        checked_at = verification.get("checked_at")
                        if "checked_at" not in verification:
                            errors.append(
                                f"module verification requires checked_at: {module_id}"
                            )
                        if checked_at is not None and (
                            not isinstance(checked_at, str) or not checked_at.strip()
                        ):
                            errors.append(
                                "module verification.checked_at must be null or a "
                                f"non-empty string: {module_id}"
                            )
                        notes = verification.get("notes")
                        if "notes" not in verification:
                            errors.append(
                                f"module verification requires notes: {module_id}"
                            )
                        if notes is not None and not isinstance(notes, str):
                            errors.append(
                                "module verification.notes must be null or a string: "
                                f"{module_id}"
                            )
                        if verification_status == "passed":
                            if (
                                not commands_valid
                                or not commands
                                or any(not command.strip() for command in commands)
                            ):
                                errors.append(
                                    "passed verification requires non-empty commands: "
                                    f"{module_id}"
                                )
                            if not isinstance(checked_at, str) or not checked_at.strip():
                                errors.append(
                                    f"passed verification requires checked_at: {module_id}"
                                )
                            if not isinstance(notes, str) or not notes.strip():
                                errors.append(
                                    "passed verification requires result notes: "
                                    f"{module_id}"
                                )
                    if (
                        position > 1
                        and status_valid
                        and status in {"building", "verified", "completed"}
                        and valid_module_id
                        and not has_confirmation(
                            confirmations,
                            "advance",
                            module_id=module_id,
                            roadmap_version=roadmap_version,
                            module_revision=module_revision,
                        )
                    ):
                        errors.append(
                            "later module work requires advance confirmation for "
                            f"roadmap_version {roadmap_version} and module_revision "
                            f"{module_revision}: {module_id}"
                        )
                    if status_valid and status in {"building", "verified"} and any(
                        not isinstance(previous.get("status"), str)
                        or previous.get("status") not in {"completed", "skipped"}
                        for previous in ordered_modules[:-1]
                    ):
                        errors.append(
                            "active module requires completed/skipped predecessors: "
                            f"{module_id}"
                        )
                    if status_valid and status in {"completed", "skipped"}:
                        if unfinished_seen:
                            errors.append(
                                "completed/skipped module cannot follow unfinished module: "
                                f"{module_id}"
                            )
                    elif status_valid:
                        unfinished_seen = True
                    expected_prefix = f"{position:02d}-"
                    if isinstance(module_id, str) and not module_id.startswith(expected_prefix):
                        errors.append(
                            f"module id at position {position} must start with "
                            f"{expected_prefix}: {module_id}"
                        )
                    if valid_module_id:
                        earlier_module_ids.add(module_id)
                module_work_phases = {
                    "building_module",
                    "verifying_module",
                    "awaiting_learner_confirmation",
                    "awaiting_advance",
                    "course_complete",
                }
                if (
                    effective_phase in module_work_phases
                    and roadmap_version_valid
                    and not has_confirmation(
                        confirmations,
                        "roadmap",
                        roadmap_version=roadmap_version,
                    )
                ):
                    errors.append(
                        "module work requires roadmap confirmation for version "
                        f"{roadmap_version}"
                    )

                if effective_phase in {"building_module", "verifying_module"}:
                    building = [
                        module
                        for module in modules
                        if isinstance(module, dict) and module.get("status") == "building"
                    ]
                    if len(building) != 1:
                        errors.append(
                            f"{effective_phase} requires exactly one building module"
                        )
                    elif state.get("current_module") != building[0].get("id"):
                        errors.append(
                            "current_module must match the only building module: "
                            f"{building[0].get('id')}"
                        )
                    elif effective_phase == "verifying_module":
                        module_id = building[0].get("id")
                        if isinstance(module_id, str) and module_id in valid_module_ids:
                            check_module_artifacts(
                                analysis, module_id, "verifying", errors
                            )
                if effective_phase == "awaiting_learner_confirmation":
                    verified = [
                        module
                        for module in modules
                        if isinstance(module, dict) and module.get("status") == "verified"
                    ]
                    if len(verified) != 1:
                        errors.append(
                            "awaiting_learner_confirmation requires exactly one verified module"
                        )
                    elif current_module != verified[0].get("id"):
                        errors.append(
                            "current_module must match the only verified module: "
                            f"{verified[0].get('id')}"
                        )
                if effective_phase == "awaiting_advance":
                    terminal = [
                        module
                        for module in ordered_modules
                        if isinstance(module.get("status"), str)
                        and module.get("status") in {"completed", "skipped"}
                    ]
                    if not terminal:
                        errors.append(
                            "awaiting_advance requires a completed or skipped module"
                        )
                    elif current_module != terminal[-1].get("id"):
                        errors.append(
                            "awaiting_advance current_module must be the latest completed "
                            "or skipped module"
                        )
                    current_index = next(
                        (
                            index
                            for index, module in enumerate(ordered_modules)
                            if module.get("id") == current_module
                        ),
                        None,
                    )
                    later = (
                        ordered_modules[current_index + 1 :]
                        if current_index is not None
                        else []
                    )
                    if not later or any(
                        module.get("status") != "planned" for module in later
                    ):
                        errors.append(
                            "awaiting_advance requires one or more later planned modules"
                        )
                if effective_phase == "course_complete" and ordered_modules:
                    if current_module != ordered_modules[-1].get("id"):
                        errors.append(
                            "course_complete current_module must be the final module"
                        )
                for module in modules:
                    if not isinstance(module, dict):
                        continue
                    status = module.get("status")
                    module_id = module.get("id")
                    valid_module_id = (
                        isinstance(module_id, str)
                        and module_id in valid_module_ids
                    )
                    if status == "completed" and (
                        not valid_module_id
                        or not has_confirmation(
                            confirmations,
                            "learner_completion",
                            module_id=module_id,
                            roadmap_version=roadmap_version,
                            module_revision=module.get("module_revision"),
                        )
                    ):
                        errors.append(
                            "completed module requires learner_completion confirmation "
                            f"for roadmap_version {roadmap_version} and module_revision "
                            f"{module.get('module_revision')}: {module_id}"
                        )
                    if status == "skipped" and (
                        not valid_module_id
                        or not has_confirmation(
                            confirmations,
                            "skip",
                            module_id=module_id,
                            roadmap_version=roadmap_version,
                            module_revision=module.get("module_revision"),
                        )
                    ):
                        errors.append(
                            "skipped module requires skip confirmation for "
                            f"roadmap_version {roadmap_version} and module_revision "
                            f"{module.get('module_revision')}: {module_id}"
                        )
                    if isinstance(status, str) and status in {"verified", "completed"}:
                        verification = module.get("verification")
                        if (
                            not isinstance(verification, dict)
                            or verification.get("status") != "passed"
                        ):
                            errors.append(
                                f"{status} module requires verification.status=passed: "
                                f"{module.get('id')}"
                            )
                        if valid_module_id:
                            check_module_artifacts(
                                analysis, module_id, status, errors
                            )
                    if module.get("status") != "planned":
                        continue
                    module_id = module.get("id")
                    if valid_module_id:
                        module_dir = analysis / module_id
                        if is_link_or_reparse(module_dir):
                            errors.append(
                                f"module directory must not be a symlink: {module_id}"
                            )
                        elif module_dir.exists():
                            errors.append(
                                "planned module directory exists before its Gate: "
                                f"code-analysis/{module_id}"
                            )

    return {"valid": not errors, "errors": errors, "warnings": warnings}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Repository root containing code-analysis/")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"Repository root is not a directory: {root}")
    result = validate_course(root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
