import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "repo_inventory.py"


def load_inventory_module():
    spec = importlib.util.spec_from_file_location("repo_inventory_under_test", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load inventory script: {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RepoInventoryCliTests(unittest.TestCase):
    def test_excludes_generated_trees_and_reports_project_files(self):
        """Removing directory pruning would make generated files leak into the inventory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
            (root / "README.md").write_text("# Demo\n", encoding="utf-8")
            (root / ".git").mkdir()
            (root / ".git" / "config").write_text("ignored\n", encoding="utf-8")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "package.js").write_text("ignored\n", encoding="utf-8")
            (root / "code-analysis").mkdir()
            (root / "code-analysis" / "README.md").write_text("ignored\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            paths = [item["path"] for item in payload["files"]]
            self.assertEqual(paths, ["README.md", "src/main.py"])
            self.assertEqual(payload["summary"]["included_files"], 2)
            self.assertEqual(payload["scope"], ".")
            self.assertEqual(
                payload["source"],
                {"kind": "filesystem", "revision": "unversioned", "dirty": False},
            )

    def test_falls_back_to_filesystem_inventory_when_git_is_unavailable(self):
        """A missing Git executable must not prevent inventorying an ordinary directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "app.py").write_text("print('fallback')\n", encoding="utf-8")
            environment = os.environ.copy()
            environment["PATH"] = str(root / "definitely-no-executables-here")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
                env=environment,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual([item["path"] for item in payload["files"]], ["app.py"])
            self.assertEqual(
                payload["source"],
                {"kind": "filesystem", "revision": "unversioned", "dirty": False},
            )

    def test_git_inventory_respects_gitignore_for_untracked_files(self):
        """Falling back to a raw walk would include files Git marks as ignored."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            subprocess.run(
                ["git", "init", "--quiet", str(root)],
                check=True,
                capture_output=True,
                text=True,
            )
            (root / ".gitignore").write_text("ignored.log\n", encoding="utf-8")
            (root / "app.py").write_text("print('app')\n", encoding="utf-8")
            (root / "ignored.log").write_text("secret-ish output\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(root), "add", ".gitignore", "app.py"],
                check=True,
                capture_output=True,
                text=True,
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            paths = [item["path"] for item in payload["files"]]
            self.assertEqual(paths, [".gitignore", "app.py"])
            self.assertEqual(payload["source"]["kind"], "git")
            self.assertEqual(payload["source"]["revision"], "unborn")
            self.assertTrue(payload["source"]["dirty"])

    def test_git_inventory_preserves_monorepo_context_for_selected_subdirectory(self):
        """A scoped scan must retain Git ignores/revision without inheriting sibling dirtiness."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            selected = repo / "packages" / "selected"
            sibling = repo / "packages" / "sibling"
            selected.mkdir(parents=True)
            sibling.mkdir(parents=True)
            subprocess.run(
                ["git", "init", "--quiet", str(repo)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "-C", str(repo), "config", "user.name", "Inventory Test"],
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "config",
                    "user.email",
                    "inventory@example.invalid",
                ],
                check=True,
            )
            (repo / ".gitignore").write_text("*.ignored\n", encoding="utf-8")
            (selected / "app.py").write_text("print('selected')\n", encoding="utf-8")
            (sibling / "app.py").write_text("print('sibling')\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(repo), "add", "."],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "-C", str(repo), "commit", "--quiet", "-m", "Initial"],
                check=True,
                capture_output=True,
                text=True,
            )
            revision = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            ).stdout.strip()

            (sibling / "app.py").write_text("print('dirty sibling')\n", encoding="utf-8")
            (selected / "private.ignored").write_text("ignored\n", encoding="utf-8")
            first = subprocess.run(
                [sys.executable, str(SCRIPT), str(selected)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(first.returncode, 0, first.stderr)
            first_payload = json.loads(first.stdout)
            self.assertEqual([item["path"] for item in first_payload["files"]], ["app.py"])
            self.assertEqual(first_payload["source"]["kind"], "git")
            self.assertEqual(first_payload["source"]["revision"], revision)
            self.assertFalse(first_payload["source"]["dirty"])
            self.assertEqual(first_payload["scope"], ".")

            (selected / "notes.txt").write_text("scoped untracked\n", encoding="utf-8")
            second = subprocess.run(
                [sys.executable, str(SCRIPT), str(selected)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(second.returncode, 0, second.stderr)
            second_payload = json.loads(second.stdout)
            self.assertEqual(
                [item["path"] for item in second_payload["files"]],
                ["app.py", "notes.txt"],
            )
            self.assertTrue(second_payload["source"]["dirty"])

    def test_root_scope_writes_canonical_inventory_with_repository_relative_paths(self):
        """Course output stays top-level while a monorepo scope limits source coverage."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            selected = root / "packages" / "selected"
            sibling = root / "packages" / "sibling"
            selected.mkdir(parents=True)
            sibling.mkdir(parents=True)
            subprocess.run(
                ["git", "init", "--quiet", str(root)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "-C", str(root), "config", "user.name", "Inventory Test"],
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "config",
                    "user.email",
                    "inventory@example.invalid",
                ],
                check=True,
            )
            (root / ".gitignore").write_text("*.ignored\n", encoding="utf-8")
            (selected / "app.py").write_text("print('selected')\n", encoding="utf-8")
            (selected / "private.ignored").write_text("ignored\n", encoding="utf-8")
            (sibling / "app.py").write_text("print('sibling')\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(root), "add", ".gitignore", "packages"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "-C", str(root), "commit", "--quiet", "-m", "Initial"],
                check=True,
                capture_output=True,
                text=True,
            )
            revision = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            ).stdout.strip()
            (sibling / "app.py").write_text("print('dirty sibling')\n", encoding="utf-8")
            output = root / "code-analysis" / ".codebase-learning" / "inventory.json"

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(root),
                    "--scope",
                    "packages/./selected",
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["root"], ".")
            self.assertEqual(payload["scope"], "packages/selected")
            self.assertEqual(
                [item["path"] for item in payload["files"]],
                ["packages/selected/app.py"],
            )
            self.assertEqual(payload["source"]["kind"], "git")
            self.assertEqual(payload["source"]["revision"], revision)
            self.assertFalse(payload["source"]["dirty"])

    def test_scope_rejects_non_posix_absolute_traversal_and_missing_directories(self):
        """Scope parsing must not reinterpret unsafe or nonexistent paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("pass\n", encoding="utf-8")
            cases = (
                ("../outside", "unsafe_scope"),
                ("/outside", "unsafe_scope"),
                ("C:/outside", "unsafe_scope"),
                ("src\\nested", "unsafe_scope"),
                ("missing", "invalid_scope"),
            )
            for raw_scope, expected_error in cases:
                with self.subTest(scope=raw_scope):
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(SCRIPT),
                            str(root),
                            "--scope",
                            raw_scope,
                        ],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        check=False,
                    )

                    self.assertEqual(result.returncode, 2)
                    self.assertIn(expected_error, result.stderr)
                    self.assertEqual(result.stdout, "")

    def test_scope_rejects_hard_excluded_directory_components(self):
        """An explicit scope must not bypass generated, vendor, dependency, or cache pruning."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            excluded_scopes = (
                "code-analysis",
                "packages/vendor/service",
                "apps/node_modules/library",
                "src/.pytest_cache/results",
            )
            for raw_scope in excluded_scopes:
                (root / Path(*PurePosixPath(raw_scope).parts)).mkdir(parents=True)

            for raw_scope in excluded_scopes:
                with self.subTest(scope=raw_scope):
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(SCRIPT),
                            str(root),
                            "--scope",
                            raw_scope,
                        ],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        check=False,
                    )

                    self.assertEqual(result.returncode, 2)
                    self.assertIn("invalid_scope", result.stderr)
                    self.assertEqual(result.stdout, "")

    def test_scope_rejects_directory_symlink_escape(self):
        """A scope may not cross a directory symlink even when its target is readable."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root = base / "repo"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            (outside / "main.py").write_text("pass\n", encoding="utf-8")
            link = root / "linked-source"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"directory symlinks unavailable: {error}")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(root),
                    "--scope",
                    "linked-source",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("unsafe_scope", result.stderr)
            self.assertEqual(result.stdout, "")

    @unittest.skipUnless(os.name == "nt", "Windows directory junction test")
    def test_scope_rejects_windows_junction_escape(self):
        """A Windows junction cannot be selected as the source scope."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root = base / "repo"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            (outside / "main.py").write_text("pass\n", encoding="utf-8")
            junction = root / "junction-source"
            creation = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(outside)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if creation.returncode != 0:
                self.skipTest(f"directory junctions unavailable: {creation.stderr}")
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        str(root),
                        "--scope",
                        "junction-source",
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )

                self.assertEqual(result.returncode, 2)
                self.assertIn("unsafe_scope", result.stderr)
                self.assertEqual(result.stdout, "")
            finally:
                if junction.exists():
                    junction.rmdir()

    def test_operational_git_failure_is_explicit_instead_of_raw_walk_fallback(self):
        """A working-tree Git error must not silently discard ignore and revision semantics."""
        module = load_inventory_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            successful_probe = subprocess.CompletedProcess(
                ["git"], 0, stdout=(str(root) + "\n").encode("utf-8"), stderr=b""
            )
            failed_listing = subprocess.CompletedProcess(
                ["git"], 74, stdout=b"", stderr=b"simulated operational failure"
            )

            with mock.patch.object(
                module,
                "run_git",
                side_effect=[successful_probe, failed_listing],
            ):
                with self.assertRaisesRegex(
                    module.InventoryError,
                    "git_operation_failed",
                ):
                    module.git_files(root)

    def test_filesystem_walk_errors_are_explicit(self):
        """Permission or I/O failures must not produce a plausible but incomplete inventory."""
        module = load_inventory_module()

        def failing_walk(*args, **kwargs):
            kwargs["onerror"](PermissionError("simulated unreadable directory"))
            return []

        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch.object(module.os, "walk", side_effect=failing_walk):
                with self.assertRaisesRegex(
                    module.InventoryError,
                    "filesystem_walk_failed",
                ):
                    module.filesystem_files(Path(temp_dir))

    def test_output_option_writes_utf8_json_to_the_requested_path(self):
        """Ignoring --output would prevent the skill from persisting its inventory artifact."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "source.py").write_text("value = 1\n", encoding="utf-8")
            output = root / "inventory.json"

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root), "--output", str(output)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["files"][0]["path"], "source.py")

    def test_output_option_creates_missing_parent_directories(self):
        """A fresh code-analysis tree should not need to be pre-created by the caller."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "main.py").write_text("value = 1\n", encoding="utf-8")
            output = root / "code-analysis" / ".codebase-learning" / "inventory.json"

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root), "--output", str(output)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.is_file())
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual([item["path"] for item in payload["files"]], ["main.py"])

    def test_output_rejects_absolute_path_outside_repository(self):
        """An absolute output path may be used only when it remains inside the explicit root."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root = base / "repo"
            root.mkdir()
            (root / "main.py").write_text("pass\n", encoding="utf-8")
            output = base / "escaped-inventory.json"

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root), "--output", str(output)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("unsafe_output_path", result.stderr)
            self.assertFalse(output.exists())

    def test_output_rejects_directory_symlink_escape(self):
        """A lexically in-root output must not traverse a symlink into another directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root = base / "repo"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            (root / "main.py").write_text("pass\n", encoding="utf-8")
            link = root / "linked-output"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"directory symlinks unavailable: {error}")
            output = link / "inventory.json"

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root), "--output", str(output)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("unsafe_output_path", result.stderr)
            self.assertFalse((outside / "inventory.json").exists())

    @unittest.skipUnless(os.name == "nt", "Windows directory junction test")
    def test_output_rejects_windows_junction_escape(self):
        """Windows reparse-point junctions must not bypass output containment."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root = base / "repo"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            (root / "main.py").write_text("pass\n", encoding="utf-8")
            junction = root / "junction-output"
            creation = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(outside)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if creation.returncode != 0:
                self.skipTest(f"directory junctions unavailable: {creation.stderr}")
            try:
                output = junction / "inventory.json"
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), str(root), "--output", str(output)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )

                self.assertEqual(result.returncode, 2)
                self.assertIn("unsafe_output_path", result.stderr)
                self.assertFalse((outside / "inventory.json").exists())
            finally:
                if junction.exists():
                    junction.rmdir()

    def test_output_uses_same_directory_temp_file_and_atomic_replace(self):
        """A completed inventory should appear through os.replace without partial writes."""
        module = load_inventory_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            output = root / "code-analysis" / "inventory.json"
            with mock.patch.object(module.os, "replace", wraps=os.replace) as replace:
                module.write_output_atomically(root, output, '{"ok": true}\n')

            replace.assert_called_once()
            source, destination = replace.call_args.args
            self.assertEqual(Path(source).parent, output.parent)
            self.assertEqual(Path(destination), output)
            self.assertEqual(output.read_text(encoding="utf-8"), '{"ok": true}\n')
            self.assertEqual(list(output.parent.glob("*.tmp")), [])

    def test_fingerprint_changes_when_small_file_content_changes(self):
        """Hashing only names and sizes would miss same-size source edits between sessions."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "app.py"
            source.write_text("x=1\n", encoding="utf-8")

            first = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            first_payload = json.loads(first.stdout)

            source.write_text("x=2\n", encoding="utf-8")
            second = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            second_payload = json.loads(second.stdout)

            self.assertIn("fingerprint", first_payload)
            self.assertIn("fingerprint", second_payload)
            self.assertNotEqual(first_payload["fingerprint"], second_payload["fingerprint"])

    def test_file_limit_fails_explicitly_instead_of_silently_truncating(self):
        """Silent truncation would let orientation claim coverage it never achieved."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "one.py").write_text("one = 1\n", encoding="utf-8")
            (root / "two.py").write_text("two = 2\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root), "--max-files", "1"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 2)
            self.assertTrue(result.stdout, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["error"], "file_limit_exceeded")
            self.assertEqual(payload["summary"]["candidate_files"], 2)
            self.assertEqual(payload["summary"]["max_files"], 1)

    def test_failed_inventory_preserves_existing_output_snapshot(self):
        """A recoverable prior snapshot must survive a failed refresh attempt."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "one.py").write_text("one = 1\n", encoding="utf-8")
            (root / "two.py").write_text("two = 2\n", encoding="utf-8")
            output = root / "code-analysis" / ".codebase-learning" / "inventory.json"
            output.parent.mkdir(parents=True)
            prior_snapshot = '{"prior": true}\n'
            output.write_text(prior_snapshot, encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(root),
                    "--max-files",
                    "1",
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 2)
            self.assertEqual(output.read_text(encoding="utf-8"), prior_snapshot)
            failure = json.loads(result.stdout)
            self.assertEqual(failure["error"], "file_limit_exceeded")

    def test_inventory_does_not_persist_the_machine_absolute_root(self):
        """Leaking an absolute path would make committed course metadata non-portable."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "main.py").write_text("print('portable')\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )

            payload = json.loads(result.stdout)
            self.assertEqual(payload["root"], ".")
            self.assertNotIn(str(root), result.stdout)

    def test_course_artifact_changes_do_not_mark_project_source_dirty(self):
        """Including code-analysis Git status would trigger source drift on every course update."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            subprocess.run(
                ["git", "init", "--quiet", str(root)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "-C", str(root), "config", "user.name", "Inventory Test"],
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "config",
                    "user.email",
                    "inventory@example.invalid",
                ],
                check=True,
            )
            (root / "app.py").write_text("print('clean')\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(root), "add", "app.py"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "-C", str(root), "commit", "--quiet", "-m", "Add source"],
                check=True,
                capture_output=True,
                text=True,
            )
            course = root / "code-analysis"
            course.mkdir()
            (course / "README.md").write_text("course output\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )

            payload = json.loads(result.stdout)
            self.assertFalse(payload["source"]["dirty"])

    def test_sensitive_files_are_metadata_only_and_never_content_hashed(self):
        """Hashing secret-bearing files would persist derived credential material."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".env").write_text("API_TOKEN=secret-value\n", encoding="utf-8")
            (root / "main.py").write_text("print('safe')\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )

            payload = json.loads(result.stdout)
            self.assertEqual([item["path"] for item in payload["files"]], ["main.py"])
            self.assertEqual(
                payload["excluded_files"],
                [{"path": ".env", "reason": "sensitive_metadata_only"}],
            )
            self.assertNotIn("secret-value", result.stdout)

    def test_obvious_credential_name_patterns_are_metadata_only(self):
        """Credential conventions beyond .env must not be content-hashed."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            credential_paths = [
                Path("prod.env"),
                Path(".envrc"),
                Path(".git-credentials"),
                Path("client_secret.json"),
                Path("service-account-prod.json"),
                Path("deploy.jks"),
                Path("prod.tfvars"),
                Path("prod.tfvars.json"),
                Path("secrets.yaml"),
                Path("secrets.yml"),
                Path(".aws") / "credentials",
            ]
            for index, relative_path in enumerate(credential_paths):
                path = root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"credential-value-{index}\n", encoding="utf-8")
            (root / "main.py").write_text("print('safe')\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )

            payload = json.loads(result.stdout)
            self.assertEqual([item["path"] for item in payload["files"]], ["main.py"])
            excluded = {item["path"]: item["reason"] for item in payload["excluded_files"]}
            self.assertEqual(
                excluded,
                {
                    path.as_posix(): "sensitive_metadata_only"
                    for path in credential_paths
                },
            )
            self.assertNotIn("credential-value", result.stdout)

    def test_binary_files_are_metadata_only_and_never_content_hashed(self):
        """Binary payloads should not be read in full or represented by content digests."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "asset.data").write_bytes(b"binary-secret\x00payload")
            (root / "main.py").write_text("print('safe')\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )

            payload = json.loads(result.stdout)
            self.assertEqual([item["path"] for item in payload["files"]], ["main.py"])
            self.assertEqual(
                payload["excluded_files"],
                [{"path": "asset.data", "reason": "binary_metadata_only", "bytes": 21}],
            )
            self.assertNotIn("binary-secret", result.stdout)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO files are unavailable")
    def test_special_files_are_metadata_only_and_never_opened(self):
        """A FIFO would hang if the inventory attempted to hash it like a regular file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fifo = root / "events.pipe"
            os.mkfifo(str(fifo))
            (root / "main.py").write_text("print('safe')\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
                timeout=10,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual([item["path"] for item in payload["files"]], ["main.py"])
            self.assertEqual(
                payload["excluded_files"],
                [{"path": "events.pipe", "reason": "special_file_metadata_only", "bytes": 0}],
            )

    def test_nonregular_classification_never_calls_binary_probe_or_hasher(self):
        """The regular-file gate is enforced even where the OS cannot create a FIFO fixture."""
        module = load_inventory_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            special = root / "device-like-entry"
            special.write_bytes(b"placeholder")
            source = {
                "kind": "filesystem",
                "revision": "unversioned",
                "dirty": False,
            }
            with mock.patch.object(
                module,
                "git_files",
                return_value=([special], source),
            ):
                with mock.patch.object(module.stat, "S_ISREG", return_value=False):
                    with mock.patch.object(
                        module,
                        "is_probably_binary",
                    ) as binary_probe:
                        with mock.patch.object(module, "sha256_file") as hasher:
                            payload = module.build_inventory(root, max_files=10)

            binary_probe.assert_not_called()
            hasher.assert_not_called()
            self.assertEqual(
                payload["excluded_files"],
                [
                    {
                        "path": "device-like-entry",
                        "reason": "special_file_metadata_only",
                        "bytes": 11,
                    }
                ],
            )

    @unittest.skipUnless(os.name == "nt", "Windows directory junction test")
    def test_source_junction_is_metadata_only_and_not_traversed(self):
        """Repository scanning must not follow a reparse-point directory outside its root."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root = base / "repo"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            (root / "main.py").write_text("pass\n", encoding="utf-8")
            (outside / "external-secret.txt").write_text(
                "external-secret-value\n",
                encoding="utf-8",
            )
            junction = root / "external-tree"
            creation = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(outside)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if creation.returncode != 0:
                self.skipTest(f"directory junctions unavailable: {creation.stderr}")
            try:
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), str(root)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual([item["path"] for item in payload["files"]], ["main.py"])
                excluded = {item["path"]: item["reason"] for item in payload["excluded_files"]}
                self.assertEqual(
                    excluded,
                    {"external-tree": "special_file_metadata_only"},
                )
                self.assertNotIn("external-tree/external-secret.txt", result.stdout)
            finally:
                if junction.exists():
                    junction.rmdir()

    @unittest.skipUnless(os.name == "nt", "Windows directory junction test")
    def test_git_candidates_below_junction_are_collapsed_to_metadata(self):
        """Git-reported descendants must not make a reparse-point target hashable."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root = base / "repo"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            subprocess.run(
                ["git", "init", "--quiet", str(root)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "-C", str(root), "config", "user.name", "Inventory Test"],
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "config",
                    "user.email",
                    "inventory@example.invalid",
                ],
                check=True,
            )
            (root / "main.py").write_text("pass\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(root), "add", "main.py"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "-C", str(root), "commit", "--quiet", "-m", "Initial"],
                check=True,
                capture_output=True,
                text=True,
            )
            (outside / "external-secret.txt").write_text(
                "external-secret-value\n",
                encoding="utf-8",
            )
            junction = root / "external-tree"
            creation = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(outside)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if creation.returncode != 0:
                self.skipTest(f"directory junctions unavailable: {creation.stderr}")
            try:
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), str(root)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual([item["path"] for item in payload["files"]], ["main.py"])
                excluded = {item["path"]: item["reason"] for item in payload["excluded_files"]}
                self.assertEqual(
                    excluded,
                    {"external-tree": "special_file_metadata_only"},
                )
                self.assertNotIn("external-tree/external-secret.txt", result.stdout)
            finally:
                if junction.exists():
                    junction.rmdir()

    def test_oversized_files_are_metadata_only_with_configurable_threshold(self):
        """The hashing byte ceiling must be deterministic and configurable for small tests."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "large.txt").write_text("0123456789", encoding="utf-8")
            (root / "small.txt").write_text("1234", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(root),
                    "--max-hash-bytes",
                    "4",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )

            payload = json.loads(result.stdout)
            self.assertEqual([item["path"] for item in payload["files"]], ["small.txt"])
            self.assertEqual(
                payload["excluded_files"],
                [{"path": "large.txt", "reason": "oversized_metadata_only", "bytes": 10}],
            )
            self.assertEqual(payload["summary"]["metadata_only_files"], 1)

    def test_max_hash_bytes_must_be_positive(self):
        """A zero byte limit is almost certainly a caller error and should fail clearly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "main.py").write_text("pass\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root), "--max-hash-bytes", "0"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--max-hash-bytes must be at least 1", result.stderr)


if __name__ == "__main__":
    unittest.main()
