#!/usr/bin/env python3
"""Create a read-only, machine-readable inventory of a source repository."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath


EXCLUDED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "code-analysis",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "vendor",
}
SAFE_ENV_TEMPLATES = {".env.example", ".env.sample", ".env.template"}
SENSITIVE_FILENAMES = {
    ".envrc",
    ".git-credentials",
    ".my.cnf",
    ".netrc",
    ".npmrc",
    ".pgpass",
    ".pypirc",
    "application_default_credentials.json",
    "auth.json",
    "credentials",
    "credentials.json",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
    "kubeconfig",
    "secrets.json",
    "secrets.yaml",
    "secrets.yml",
}
SENSITIVE_PATTERNS = {
    "*.tfvars.json",
    "client-secret*.json",
    "client_secret*.json",
    "service-account*.json",
    "service_account*.json",
}
SENSITIVE_SUFFIXES = {
    ".credentials",
    ".jks",
    ".key",
    ".keystore",
    ".p12",
    ".pem",
    ".pfx",
    ".tfstate",
    ".tfvars",
    ".token",
}
BINARY_SUFFIXES = {
    ".7z",
    ".a",
    ".avi",
    ".bin",
    ".bmp",
    ".class",
    ".db",
    ".dll",
    ".dylib",
    ".eot",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".mp3",
    ".mp4",
    ".o",
    ".pdf",
    ".png",
    ".pyc",
    ".rar",
    ".so",
    ".sqlite",
    ".sqlite3",
    ".tar",
    ".tiff",
    ".ttf",
    ".wav",
    ".webm",
    ".webp",
    ".woff",
    ".woff2",
    ".xz",
    ".zip",
}
DEFAULT_MAX_HASH_BYTES = 8 * 1024 * 1024
BINARY_SNIFF_BYTES = 8192


class InventoryError(RuntimeError):
    """An explicit failure that prevents a complete, trustworthy inventory."""

    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


class GitUnavailable(RuntimeError):
    """The Git executable is not installed or not visible on PATH."""


def filesystem_files(root: Path) -> list[Path]:
    def raise_walk_error(error: OSError) -> None:
        raise InventoryError(
            "filesystem_walk_failed",
            f"{type(error).__name__}: unable to enumerate a repository directory",
        ) from error

    files: list[Path] = []
    for current, directories, filenames in os.walk(
        root,
        followlinks=False,
        onerror=raise_walk_error,
    ):
        retained_directories: list[str] = []
        for name in sorted(directories):
            if name.lower() in EXCLUDED_DIRECTORIES:
                continue
            path = Path(current) / name
            if is_symlink_or_reparse_point(path):
                files.append(path)
            else:
                retained_directories.append(name)
        directories[:] = retained_directories
        for filename in sorted(filenames):
            path = Path(current) / filename
            files.append(path)
    return files


def is_excluded(relative_path: Path) -> bool:
    return any(part.lower() in EXCLUDED_DIRECTORIES for part in relative_path.parts)


def is_sensitive(relative_path: Path) -> bool:
    name = relative_path.name.lower()
    if name == ".env" or name.endswith(".env"):
        return True
    if name.startswith(".env.") and name not in SAFE_ENV_TEMPLATES:
        return True
    return (
        name in SENSITIVE_FILENAMES
        or relative_path.suffix.lower() in SENSITIVE_SUFFIXES
        or any(fnmatch.fnmatchcase(name, pattern) for pattern in SENSITIVE_PATTERNS)
    )


def is_probably_binary(path: Path) -> bool:
    if path.suffix.lower() in BINARY_SUFFIXES:
        return True
    with path.open("rb") as source:
        sample = source.read(BINARY_SNIFF_BYTES)
    if b"\0" in sample:
        return True
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def run_git(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    command = ["git", "-C", str(root), *arguments]
    environment = os.environ.copy()
    environment["LC_ALL"] = "C"
    environment["LANG"] = "C"
    try:
        return subprocess.run(
            command,
            capture_output=True,
            check=False,
            env=environment,
        )
    except FileNotFoundError as error:
        raise GitUnavailable("git executable unavailable") from error
    except OSError as error:
        raise InventoryError(
            "git_launch_failed",
            f"{type(error).__name__}: unable to launch Git",
        ) from error


def nul_paths(result: subprocess.CompletedProcess[bytes]) -> list[Path]:
    if result.returncode != 0:
        return []
    return [
        Path(item.decode("utf-8", errors="surrogateescape"))
        for item in result.stdout.split(b"\0")
        if item
    ]


def require_git_success(
    root: Path,
    operation: str,
    *arguments: str,
) -> subprocess.CompletedProcess[bytes]:
    try:
        result = run_git(root, *arguments)
    except GitUnavailable as error:
        raise InventoryError(
            "git_operation_failed",
            f"Git became unavailable during {operation}",
        ) from error
    if result.returncode != 0:
        raise InventoryError(
            "git_operation_failed",
            f"{operation} exited with status {result.returncode}",
        )
    return result


def paths_relative_to_base(
    result: subprocess.CompletedProcess[bytes],
    base: Path,
) -> list[Path]:
    relative_paths: list[Path] = []
    for repository_path in nul_paths(result):
        if base == Path("."):
            relative_path = repository_path
        else:
            try:
                relative_path = repository_path.relative_to(base)
            except ValueError:
                continue
        if relative_path != Path("."):
            relative_paths.append(relative_path)
    return relative_paths


def collapse_reparse_candidate(root: Path, relative_path: Path) -> Path:
    candidate = root
    for component in relative_path.parts:
        candidate = candidate / component
        if is_symlink_or_reparse_point(candidate):
            break
    return candidate


def git_files(
    root: Path,
    scan_root: Path | None = None,
) -> tuple[list[Path], dict[str, object]] | None:
    if scan_root is None:
        scan_root = root
    try:
        probe = run_git(scan_root, "rev-parse", "--show-toplevel")
    except GitUnavailable:
        return None
    if probe.returncode != 0:
        diagnostic = probe.stderr.decode("utf-8", errors="replace").lower()
        if probe.returncode == 128 and "not a git repository" in diagnostic:
            return None
        raise InventoryError(
            "git_probe_failed",
            f"Git repository detection exited with status {probe.returncode}",
        )
    top_level = probe.stdout.decode("utf-8", errors="surrogateescape").strip()
    if not top_level:
        raise InventoryError("git_probe_failed", "Git returned an empty repository root")
    git_root = Path(top_level).resolve()
    try:
        repository_base = root.relative_to(git_root)
        git_scope = scan_root.relative_to(git_root)
    except ValueError as error:
        raise InventoryError(
            "git_probe_failed",
            "repository root or selected scope is outside the Git top-level directory",
        ) from error
    pathspec = (
        "."
        if git_scope == Path(".")
        else f":(top,literal){git_scope.as_posix()}"
    )

    listing = require_git_success(
        git_root,
        "file listing",
        "ls-files",
        "-z",
        "--full-name",
        "--cached",
        "--others",
        "--exclude-standard",
        "--",
        pathspec,
    )
    relative_paths = paths_relative_to_base(listing, repository_base)
    candidate_files: dict[str, Path] = {}
    for relative_path in relative_paths:
        if is_excluded(relative_path):
            continue
        candidate = collapse_reparse_candidate(root, relative_path)
        if not os.path.lexists(candidate):
            continue
        candidate_relative = candidate.relative_to(root)
        if is_excluded(candidate_relative):
            continue
        candidate_files[candidate_relative.as_posix()] = candidate
    files = [candidate_files[key] for key in sorted(candidate_files)]

    try:
        revision_result = run_git(git_root, "rev-parse", "--verify", "HEAD")
    except GitUnavailable as error:
        raise InventoryError(
            "git_operation_failed",
            "Git became unavailable during revision detection",
        ) from error
    if revision_result.returncode == 0:
        revision = revision_result.stdout.decode("ascii", errors="replace").strip()
        if not revision:
            raise InventoryError("git_operation_failed", "Git returned an empty revision")
    else:
        symbolic_head = require_git_success(
            git_root,
            "unborn HEAD detection",
            "symbolic-ref",
            "-q",
            "HEAD",
        )
        if not symbolic_head.stdout.strip():
            raise InventoryError(
                "git_operation_failed",
                "Git could not identify the current revision",
            )
        revision = "unborn"

    dirty_results = (
        require_git_success(
            git_root,
            "unstaged change listing",
            "diff",
            "--name-only",
            "-z",
            "--",
            pathspec,
        ),
        require_git_success(
            git_root,
            "staged change listing",
            "diff",
            "--cached",
            "--name-only",
            "-z",
            "--",
            pathspec,
        ),
        require_git_success(
            git_root,
            "untracked file listing",
            "ls-files",
            "-z",
            "--full-name",
            "--others",
            "--exclude-standard",
            "--",
            pathspec,
        ),
    )
    dirty_paths = {
        path
        for result in dirty_results
        for path in paths_relative_to_base(result, repository_base)
        if not is_excluded(path)
    }
    dirty = bool(dirty_paths)
    return files, {"kind": "git", "revision": revision, "dirty": dirty}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_inventory(
    root: Path,
    max_files: int,
    max_hash_bytes: int = DEFAULT_MAX_HASH_BYTES,
    scan_root: Path | None = None,
    scope: str = ".",
) -> dict[str, object]:
    if scan_root is None:
        scan_root = root
    git_result = git_files(root, scan_root)
    if git_result is None:
        files = filesystem_files(scan_root)
        source: dict[str, object] = {
            "kind": "filesystem",
            "revision": "unversioned",
            "dirty": False,
        }
    else:
        files, source = git_result
    if len(files) > max_files:
        return {
            "schema_version": 1,
            "root": ".",
            "scope": scope,
            "source": source,
            "error": "file_limit_exceeded",
            "summary": {
                "candidate_files": len(files),
                "max_files": max_files,
            },
        }
    entries: list[dict[str, object]] = []
    metadata_entries: list[dict[str, object]] = []
    for path in files:
        relative_path = path.relative_to(root)
        relative_posix = relative_path.as_posix()
        if is_sensitive(relative_path):
            metadata_entries.append(
                {"path": relative_posix, "reason": "sensitive_metadata_only"}
            )
            continue
        try:
            file_status = path.lstat()
        except OSError as error:
            raise InventoryError(
                "file_inspection_failed",
                f"{type(error).__name__}: unable to inspect {relative_posix}",
            ) from error
        size = file_status.st_size
        if not stat.S_ISREG(file_status.st_mode):
            metadata_entries.append(
                {
                    "path": relative_posix,
                    "reason": "special_file_metadata_only",
                    "bytes": size,
                }
            )
            continue
        if size > max_hash_bytes:
            metadata_entries.append(
                {
                    "path": relative_posix,
                    "reason": "oversized_metadata_only",
                    "bytes": size,
                }
            )
            continue
        if is_probably_binary(path):
            metadata_entries.append(
                {
                    "path": relative_posix,
                    "reason": "binary_metadata_only",
                    "bytes": size,
                }
            )
            continue
        entries.append(
            {
                "path": relative_posix,
                "bytes": size,
                "sha256": sha256_file(path),
            }
        )
    entries.sort(key=lambda item: item["path"])
    metadata_entries.sort(key=lambda item: item["path"])
    fingerprint = hashlib.sha256()
    fingerprint.update(b"scope\0")
    fingerprint.update(scope.encode("utf-8", errors="surrogateescape"))
    fingerprint.update(b"\0")
    for entry in entries:
        fingerprint.update(entry["path"].encode("utf-8", errors="surrogateescape"))
        fingerprint.update(b"\0")
        fingerprint.update(entry["sha256"].encode("ascii"))
        fingerprint.update(b"\0")
    for entry in metadata_entries:
        fingerprint.update(entry["path"].encode("utf-8", errors="surrogateescape"))
        fingerprint.update(b"\0metadata-only\0")
        fingerprint.update(entry["reason"].encode("ascii"))
        fingerprint.update(b"\0")
        if "bytes" in entry:
            fingerprint.update(str(entry["bytes"]).encode("ascii"))
            fingerprint.update(b"\0")
    return {
        "schema_version": 1,
        "root": ".",
        "scope": scope,
        "source": source,
        "fingerprint": f"sha256:{fingerprint.hexdigest()}",
        "summary": {
            "included_files": len(entries),
            "metadata_only_files": len(metadata_entries),
            "sensitive_metadata_files": sum(
                entry["reason"] == "sensitive_metadata_only"
                for entry in metadata_entries
            ),
        },
        "files": entries,
        "excluded_files": metadata_entries,
    }


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def is_symlink_or_reparse_point(path: Path) -> bool:
    try:
        path_status = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as error:
        raise InventoryError(
            "path_inspection_failed",
            f"{type(error).__name__}: unable to inspect a path component",
        ) from error
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(path_status, "st_file_attributes", 0)
    return stat.S_ISLNK(path_status.st_mode) or bool(file_attributes & reparse_flag)


def resolve_scope(root: Path, raw_scope: str) -> tuple[Path, str]:
    if (
        not raw_scope
        or "\0" in raw_scope
        or "\\" in raw_scope
        or (len(raw_scope) >= 2 and raw_scope[0].isalpha() and raw_scope[1] == ":")
    ):
        raise InventoryError(
            "unsafe_scope",
            "scope must be a repository-relative POSIX directory",
        )
    parsed = PurePosixPath(raw_scope)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise InventoryError(
            "unsafe_scope",
            "scope must remain inside the explicit repository root",
        )
    if any(part.lower() in EXCLUDED_DIRECTORIES for part in parsed.parts):
        raise InventoryError(
            "invalid_scope",
            "scope includes a directory that is excluded from source inventories",
        )
    normalized = parsed.as_posix()
    if normalized in {"", "/"}:
        normalized = "."
    scope_path = root.joinpath(*parsed.parts)
    if not path_is_within(scope_path, root):
        raise InventoryError(
            "unsafe_scope",
            "scope must remain inside the explicit repository root",
        )
    cursor = root
    for component in scope_path.relative_to(root).parts:
        cursor = cursor / component
        if is_symlink_or_reparse_point(cursor):
            raise InventoryError(
                "unsafe_scope",
                "scope must not traverse a symlink or reparse point",
            )
    try:
        scope_status = scope_path.lstat()
    except FileNotFoundError as error:
        raise InventoryError(
            "invalid_scope",
            "scope directory does not exist",
        ) from error
    except OSError as error:
        raise InventoryError(
            "invalid_scope",
            f"{type(error).__name__}: unable to inspect the scope directory",
        ) from error
    if not stat.S_ISDIR(scope_status.st_mode):
        raise InventoryError("invalid_scope", "scope must identify a directory")
    return scope_path, normalized


def validate_output_components(root: Path, output: Path) -> None:
    if not path_is_within(output, root):
        raise InventoryError(
            "unsafe_output_path",
            "output must remain inside the explicit repository root",
        )
    cursor = root
    for component in output.relative_to(root).parts:
        cursor = cursor / component
        if is_symlink_or_reparse_point(cursor):
            raise InventoryError(
                "unsafe_output_path",
                "output must not traverse a symlink or reparse point",
            )


def write_output_atomically(root: Path, requested_output: Path, rendered: str) -> None:
    if requested_output.is_absolute():
        output = Path(os.path.abspath(str(requested_output)))
    else:
        output = Path(os.path.abspath(str(root / requested_output)))
    validate_output_components(root, output)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise InventoryError(
            "output_prepare_failed",
            f"{type(error).__name__}: unable to create the output directory",
        ) from error
    validate_output_components(root, output)
    if output.exists():
        try:
            output_status = output.stat()
        except OSError as error:
            raise InventoryError(
                "output_prepare_failed",
                f"{type(error).__name__}: unable to inspect the output file",
            ) from error
        if not stat.S_ISREG(output_status.st_mode):
            raise InventoryError(
                "unsafe_output_path",
                "an existing output target must be a regular file",
            )

    descriptor = -1
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{output.name}.",
            suffix=".tmp",
            dir=str(output.parent),
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as destination:
            descriptor = -1
            destination.write(rendered)
            destination.flush()
            os.fsync(destination.fileno())
        validate_output_components(root, output)
        os.replace(temporary_path, output)
        temporary_path = None
    except InventoryError:
        raise
    except OSError as error:
        raise InventoryError(
            "output_write_failed",
            f"{type(error).__name__}: unable to atomically write the inventory",
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Repository root to inventory")
    parser.add_argument(
        "--scope",
        default=".",
        help="Scan only this repository-relative POSIX directory (default: .)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Atomically write JSON to a path inside the repository root",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=50_000,
        help="Fail explicitly when the inventory exceeds this count (default: 50000)",
    )
    parser.add_argument(
        "--max-hash-bytes",
        type=int,
        default=DEFAULT_MAX_HASH_BYTES,
        help=(
            "Store only metadata for files larger than this many bytes "
            f"(default: {DEFAULT_MAX_HASH_BYTES})"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"Repository root is not a directory: {root}")
    if args.max_files < 1:
        raise SystemExit("--max-files must be at least 1")
    if args.max_hash_bytes < 1:
        raise SystemExit("--max-hash-bytes must be at least 1")
    try:
        scan_root, normalized_scope = resolve_scope(root, args.scope)
        payload = build_inventory(
            root,
            args.max_files,
            args.max_hash_bytes,
            scan_root=scan_root,
            scope=normalized_scope,
        )
        rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        if "error" in payload:
            print(rendered, end="")
            return 2
        if args.output:
            write_output_atomically(root, args.output, rendered)
        else:
            print(rendered, end="")
    except InventoryError as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
