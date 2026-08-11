import copy
import hashlib
import importlib.util
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_course.py"


def empty_inventory_fingerprint(scope: str = ".") -> str:
    digest = hashlib.sha256()
    digest.update(b"scope\0")
    digest.update(scope.encode("utf-8"))
    digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


FINGERPRINT = empty_inventory_fingerprint()
OTHER_FINGERPRINT = "sha256:" + ("b" * 64)
SPEC = importlib.util.spec_from_file_location("codebase_learning_validator", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR_MODULE)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if path.name == "state.json":
        source = payload.get("source", {}) if isinstance(payload, dict) else {}
        scope = (payload.get("selected_scope") or ".") if isinstance(payload, dict) else "."
        inventory = {
            "schema_version": 1,
            "root": ".",
            "scope": scope,
            "source": {
                "kind": source.get("kind", "filesystem"),
                "revision": source.get("revision", "unversioned"),
                "dirty": source.get("dirty", False),
            },
            "fingerprint": empty_inventory_fingerprint(scope),
            "summary": {
                "included_files": 0,
                "metadata_only_files": 0,
                "sensitive_metadata_files": 0,
            },
            "files": [],
            "excluded_files": [],
        }
        (path.parent / "inventory.json").write_text(
            json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def awaiting_track_state() -> dict:
    return {
        "schema_version": 1,
        "skill_version": "1.0.0",
        "repository_root": ".",
        "source": {
            "kind": "filesystem",
            "revision": "unversioned",
            "dirty": False,
            "inventory_fingerprint": FINGERPRINT,
        },
        "phase": "awaiting_track",
        "selected_scope": None,
        "selected_track": None,
        "roadmap_version": 0,
        "current_module": None,
        "modules": [],
        "confirmations": [],
        "resume_phase": None,
        "last_error": None,
    }


def confirmation(
    gate: str,
    *,
    module_id: Any = None,
    roadmap_version: Any = None,
    module_revision: Any = None,
    scope: Any = None,
    track: Any = None,
) -> dict:
    event = {
        "gate": gate,
        "module_id": module_id,
        "at": "2026-01-01T00:00:00Z",
        "summary": f"User confirmed {gate}",
    }
    if gate in {"learner_completion", "advance", "skip"}:
        roadmap_version = 1 if roadmap_version is None else roadmap_version
        module_revision = 1 if module_revision is None else module_revision
    if roadmap_version is not None:
        event["roadmap_version"] = roadmap_version
    if module_revision is not None:
        event["module_revision"] = module_revision
    if scope is not None:
        event["scope"] = scope
    if track is not None:
        event["track"] = track
    return event


def verification(status: str = "not_run", commands: Any = None) -> dict:
    if commands is None:
        commands = [] if status != "passed" else ["python demo.py"]
    return {
        "status": status,
        "commands": commands,
        "checked_at": "2026-01-01T00:00:00Z" if status == "passed" else None,
        "notes": "exit 0" if status == "passed" else None,
    }


def roadmap_state() -> dict:
    state = awaiting_track_state()
    state.update(
        {
            "phase": "awaiting_roadmap_confirmation",
            "selected_track": "Agent",
            "roadmap_version": 1,
            "modules": [
                {
                    "id": "01-agent-runtime",
                    "title": "Agent Runtime",
                    "module_revision": 1,
                    "status": "planned",
                    "depends_on": [],
                    "source_areas": ["src/agent/runtime.py"],
                    "learning_goal": "Trace the agent runtime loop",
                    "verification": verification(),
                },
                {
                    "id": "02-tool-execution",
                    "title": "Tool Execution",
                    "module_revision": 1,
                    "status": "planned",
                    "depends_on": ["01-agent-runtime"],
                    "source_areas": ["src/tools.py"],
                    "learning_goal": "Explain local tool dispatch",
                    "verification": verification(),
                },
            ],
            "confirmations": [confirmation("track", track="Agent")],
        }
    )
    return state


def add_module_artifacts(analysis: Path, module_id: str) -> None:
    module_dir = analysis / module_id
    (module_dir / "notebook").mkdir(parents=True)
    (module_dir / "notebook" / "01-lesson.md").write_text(
        "# Lesson\n", encoding="utf-8"
    )
    demo_dir = module_dir / "demo" / "01-lesson"
    demo_dir.mkdir(parents=True)
    (demo_dir / "README.md").write_text("# Demo\n", encoding="utf-8")
    (demo_dir / "main.py").write_text("print('demo')\n", encoding="utf-8")
    (module_dir / "README.md").write_text("# Module\n", encoding="utf-8")


def write_course(root: Path, state: dict) -> Path:
    for relative_path in ("src/agent/runtime.py", "src/tools.py"):
        source_path = root.joinpath(*relative_path.split("/"))
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text("# source fixture\n", encoding="utf-8")
    analysis = root / "code-analysis"
    analysis.mkdir()
    (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
    (analysis / "00-project-overview.md").write_text(
        "# Project Overview\n", encoding="utf-8"
    )
    write_json(analysis / ".codebase-learning" / "state.json", state)
    return analysis


def run_validator(root: Path) -> tuple[subprocess.CompletedProcess[str], dict]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return result, json.loads(result.stdout)


def refresh_inventory_with_source(root: Path, analysis: Path) -> None:
    inventory_path = analysis / ".codebase-learning" / "inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    source_path = root / "src" / "tools.py"
    content = source_path.read_bytes()
    inventory["files"] = [
        {
            "path": "src/tools.py",
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    ]
    inventory["summary"]["included_files"] = 1
    inventory["fingerprint"] = VALIDATOR_MODULE.compute_inventory_fingerprint(
        inventory["files"], inventory["excluded_files"]
    )
    inventory_path.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


class ValidateCourseCliTests(unittest.TestCase):
    def test_accepts_completed_orientation_waiting_for_track_selection(self):
        """Rejecting the initial Gate would make every new course unrecoverable."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = root / "code-analysis"
            analysis.mkdir()
            (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
            (analysis / "00-project-overview.md").write_text("# Project Overview\n", encoding="utf-8")
            write_json(analysis / ".codebase-learning" / "state.json", awaiting_track_state())

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["valid"])
            self.assertEqual(payload["errors"], [])

    def test_rejects_track_data_before_the_track_gate_is_crossed(self):
        """Permitting a selected track in awaiting_track would erase the user-choice Gate."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = root / "code-analysis"
            analysis.mkdir()
            (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
            (analysis / "00-project-overview.md").write_text("# Project Overview\n", encoding="utf-8")
            state = awaiting_track_state()
            state["selected_track"] = "backend"
            write_json(analysis / ".codebase-learning" / "state.json", state)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["valid"])
            self.assertIn("awaiting_track requires selected_track to be null", payload["errors"])

    def test_historical_track_confirmation_cannot_authorize_later_phases(self):
        """Clearing selected_track must close every post-roadmap Track Gate."""
        base = roadmap_state()
        base["confirmations"].append(confirmation("roadmap", roadmap_version=1))
        cases = []

        building = copy.deepcopy(base)
        building.update(
            {"phase": "building_module", "current_module": "01-agent-runtime"}
        )
        building["modules"][0]["status"] = "building"
        cases.append(("building_module", building, []))

        verifying = copy.deepcopy(building)
        verifying["phase"] = "verifying_module"
        verifying["modules"][0]["verification"] = verification(
            "running", ["python demo.py"]
        )
        cases.append(("verifying_module", verifying, ["01-agent-runtime"]))

        learner = copy.deepcopy(base)
        learner.update(
            {
                "phase": "awaiting_learner_confirmation",
                "current_module": "01-agent-runtime",
            }
        )
        learner["modules"][0].update(
            {"status": "verified", "verification": verification("passed")}
        )
        cases.append(
            ("awaiting_learner_confirmation", learner, ["01-agent-runtime"])
        )

        advance = copy.deepcopy(base)
        advance.update(
            {"phase": "awaiting_advance", "current_module": "01-agent-runtime"}
        )
        advance["modules"][0].update(
            {"status": "completed", "verification": verification("passed")}
        )
        advance["confirmations"].append(
            confirmation("learner_completion", module_id="01-agent-runtime")
        )
        cases.append(("awaiting_advance", advance, ["01-agent-runtime"]))

        complete = copy.deepcopy(base)
        complete.update(
            {"phase": "course_complete", "current_module": "02-tool-execution"}
        )
        for module in complete["modules"]:
            module.update(
                {"status": "completed", "verification": verification("passed")}
            )
            complete["confirmations"].append(
                confirmation("learner_completion", module_id=module["id"])
            )
        complete["confirmations"].append(
            confirmation("advance", module_id="02-tool-execution")
        )
        cases.append(
            (
                "course_complete",
                complete,
                ["01-agent-runtime", "02-tool-execution"],
            )
        )

        for phase, state, artifact_ids in cases:
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                state["selected_track"] = None
                analysis = write_course(root, state)
                for module_id in artifact_ids:
                    add_module_artifacts(analysis, module_id)

                result, payload = run_validator(root)

                self.assertEqual(result.returncode, 1)
                self.assertIn(
                    f"{phase} requires a non-empty selected_track",
                    payload["errors"],
                )

    def test_rejects_module_directories_before_the_roadmap_gate_is_approved(self):
        """Allowing planned directories would generate future lessons before user approval."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = root / "code-analysis"
            analysis.mkdir()
            (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
            (analysis / "00-project-overview.md").write_text("# Project Overview\n", encoding="utf-8")
            premature = analysis / "01-agent-runtime"
            premature.mkdir()
            (premature / "README.md").write_text("too early\n", encoding="utf-8")
            write_json(analysis / ".codebase-learning" / "state.json", roadmap_state())

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertIn(
                "planned module directory exists before its Gate: code-analysis/01-agent-runtime",
                payload["errors"],
            )

    def test_rejects_more_than_one_building_module(self):
        """Allowing two active modules would break the one-module-at-a-time invariant."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = root / "code-analysis"
            analysis.mkdir()
            (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
            (analysis / "00-project-overview.md").write_text("# Project Overview\n", encoding="utf-8")
            state = roadmap_state()
            state.update({"phase": "building_module", "current_module": "01-agent-runtime"})
            state["modules"][0]["status"] = "building"
            state["modules"][1]["status"] = "building"
            for module in state["modules"]:
                module_dir = analysis / module["id"]
                module_dir.mkdir()
                (module_dir / "README.md").write_text("# Module\n", encoding="utf-8")
            write_json(analysis / ".codebase-learning" / "state.json", state)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertIn("building_module requires exactly one building module", payload["errors"])

    def test_rejects_current_module_that_does_not_match_the_active_module(self):
        """A mismatched pointer would resume the course in the wrong module."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = root / "code-analysis"
            analysis.mkdir()
            (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
            (analysis / "00-project-overview.md").write_text("# Project Overview\n", encoding="utf-8")
            state = roadmap_state()
            state.update({"phase": "building_module", "current_module": "02-tool-execution"})
            state["modules"][0]["status"] = "building"
            current_dir = analysis / "01-agent-runtime"
            current_dir.mkdir()
            (current_dir / "README.md").write_text("# Module\n", encoding="utf-8")
            write_json(analysis / ".codebase-learning" / "state.json", state)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertIn(
                "current_module must match the only building module: 01-agent-runtime",
                payload["errors"],
            )

    def test_rejects_verified_module_without_passing_artifact_verification(self):
        """A failed demo check must not be presented to the learner as verified."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = root / "code-analysis"
            analysis.mkdir()
            (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
            (analysis / "00-project-overview.md").write_text("# Project Overview\n", encoding="utf-8")
            state = roadmap_state()
            state.update(
                {
                    "phase": "awaiting_learner_confirmation",
                    "current_module": "01-agent-runtime",
                }
            )
            state["modules"][0].update(
                {
                    "status": "verified",
                    "verification": verification(
                        "failed", ["python demo/main.py"]
                    ),
                }
            )
            module_dir = analysis / "01-agent-runtime"
            module_dir.mkdir()
            (module_dir / "README.md").write_text("# Module\n", encoding="utf-8")
            write_json(analysis / ".codebase-learning" / "state.json", state)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertIn(
                "verified module requires verification.status=passed: 01-agent-runtime",
                payload["errors"],
            )

    def test_rejects_verified_module_without_notebook_and_demo_artifacts(self):
        """A state-only verification must not bypass the module artifact contract."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = root / "code-analysis"
            analysis.mkdir()
            (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
            (analysis / "00-project-overview.md").write_text("# Project Overview\n", encoding="utf-8")
            state = roadmap_state()
            state.update(
                {
                    "phase": "awaiting_learner_confirmation",
                    "current_module": "01-agent-runtime",
                }
            )
            state["modules"][0].update(
                {
                    "status": "verified",
                    "verification": verification(
                        "passed", ["python demo/main.py"]
                    ),
                }
            )
            module_dir = analysis / "01-agent-runtime"
            module_dir.mkdir()
            (module_dir / "README.md").write_text("# Module\n", encoding="utf-8")
            write_json(analysis / ".codebase-learning" / "state.json", state)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertIn(
                "verified module requires at least one notebook Markdown file: 01-agent-runtime",
                payload["errors"],
            )
            self.assertIn(
                "verified module requires at least one demo README.md: 01-agent-runtime",
                payload["errors"],
            )

    def test_rejects_non_sequential_module_numbers(self):
        """A numbering gap would make the persisted learning order ambiguous."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = root / "code-analysis"
            analysis.mkdir()
            (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
            (analysis / "00-project-overview.md").write_text("# Project Overview\n", encoding="utf-8")
            state = roadmap_state()
            state["modules"][1]["id"] = "03-tool-execution"
            write_json(analysis / ".codebase-learning" / "state.json", state)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertIn(
                "module id at position 2 must start with 02-: 03-tool-execution",
                payload["errors"],
            )

    def test_rejects_unknown_course_phase(self):
        """Accepting an unknown phase would make resume behavior undefined."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = root / "code-analysis"
            analysis.mkdir()
            (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
            (analysis / "00-project-overview.md").write_text("# Project Overview\n", encoding="utf-8")
            state = awaiting_track_state()
            state["phase"] = "invented_phase"
            write_json(analysis / ".codebase-learning" / "state.json", state)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertIn("unknown phase: invented_phase", payload["errors"])

    def test_rejects_unknown_module_status(self):
        """An unknown module status would bypass ordered transition checks."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = root / "code-analysis"
            analysis.mkdir()
            (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
            (analysis / "00-project-overview.md").write_text("# Project Overview\n", encoding="utf-8")
            state = roadmap_state()
            state["modules"][0]["status"] = "magically_done"
            write_json(analysis / ".codebase-learning" / "state.json", state)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertIn(
                "unknown module status for 01-agent-runtime: magically_done",
                payload["errors"],
            )

    def test_rejects_completed_module_after_an_unfinished_predecessor(self):
        """Out-of-order completion would violate the dependency-ordered curriculum."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = root / "code-analysis"
            analysis.mkdir()
            (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
            (analysis / "00-project-overview.md").write_text("# Project Overview\n", encoding="utf-8")
            state = roadmap_state()
            state["phase"] = "awaiting_advance"
            state["current_module"] = "02-tool-execution"
            state["modules"][1]["status"] = "completed"
            write_json(analysis / ".codebase-learning" / "state.json", state)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertIn(
                "completed/skipped module cannot follow unfinished module: 02-tool-execution",
                payload["errors"],
            )

    def test_rejects_completed_module_without_passing_verification(self):
        """User confirmation cannot convert a failed artifact check into completion."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = root / "code-analysis"
            analysis.mkdir()
            (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
            (analysis / "00-project-overview.md").write_text("# Project Overview\n", encoding="utf-8")
            state = roadmap_state()
            state.update({"phase": "awaiting_advance", "current_module": "01-agent-runtime"})
            state["modules"][0].update(
                {
                    "status": "completed",
                    "verification": verification(
                        "failed", ["python demo/main.py"]
                    ),
                }
            )
            module_dir = analysis / "01-agent-runtime"
            (module_dir / "notebook").mkdir(parents=True)
            (module_dir / "notebook" / "01-loop.md").write_text("# Loop\n", encoding="utf-8")
            demo_dir = module_dir / "demo" / "01-loop"
            demo_dir.mkdir(parents=True)
            (demo_dir / "README.md").write_text("# Demo\n", encoding="utf-8")
            (module_dir / "README.md").write_text("# Module\n", encoding="utf-8")
            write_json(analysis / ".codebase-learning" / "state.json", state)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertIn(
                "completed module requires verification.status=passed: 01-agent-runtime",
                payload["errors"],
            )

    def test_reports_non_object_state_without_crashing(self):
        """Calling object methods on a JSON list would hide the recovery diagnosis."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = root / "code-analysis"
            analysis.mkdir()
            (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
            (analysis / "00-project-overview.md").write_text("# Project Overview\n", encoding="utf-8")
            write_json(analysis / ".codebase-learning" / "state.json", [])

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertTrue(result.stdout, result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("state JSON root must be an object", payload["errors"])

    def test_rejects_unsupported_state_schema_version(self):
        """Accepting an unknown schema could misinterpret Gate semantics after upgrades."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = root / "code-analysis"
            analysis.mkdir()
            (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
            (analysis / "00-project-overview.md").write_text("# Project Overview\n", encoding="utf-8")
            state = awaiting_track_state()
            state["schema_version"] = 2
            write_json(analysis / ".codebase-learning" / "state.json", state)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertIn("unsupported schema_version: 2", payload["errors"])

    def test_rejects_machine_specific_repository_root(self):
        """Persisting an absolute repository root would break portability and leak local paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = root / "code-analysis"
            analysis.mkdir()
            (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
            (analysis / "00-project-overview.md").write_text("# Project Overview\n", encoding="utf-8")
            state = awaiting_track_state()
            state["repository_root"] = str(root)
            write_json(analysis / ".codebase-learning" / "state.json", state)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertIn("repository_root must be '.'", payload["errors"])

    def test_rejects_roadmap_phase_without_a_selected_track(self):
        """Planning without an explicit Track would bypass the user's Track Gate."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = root / "code-analysis"
            analysis.mkdir()
            (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
            (analysis / "00-project-overview.md").write_text("# Project Overview\n", encoding="utf-8")
            state = roadmap_state()
            state["selected_track"] = None
            write_json(analysis / ".codebase-learning" / "state.json", state)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertIn(
                "awaiting_roadmap_confirmation requires a non-empty selected_track",
                payload["errors"],
            )

    def test_rejects_current_module_before_roadmap_approval(self):
        """Selecting a current Module early would bypass the roadmap approval Gate."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = root / "code-analysis"
            analysis.mkdir()
            (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
            (analysis / "00-project-overview.md").write_text("# Project Overview\n", encoding="utf-8")
            state = roadmap_state()
            state["current_module"] = "01-agent-runtime"
            write_json(analysis / ".codebase-learning" / "state.json", state)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertIn(
                "awaiting_roadmap_confirmation requires current_module to be null",
                payload["errors"],
            )

    def test_rejects_learner_gate_without_one_verified_module(self):
        """Entering the learner Gate without verified artifacts would create false progress."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = root / "code-analysis"
            analysis.mkdir()
            (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
            (analysis / "00-project-overview.md").write_text("# Project Overview\n", encoding="utf-8")
            state = roadmap_state()
            state["phase"] = "awaiting_learner_confirmation"
            write_json(analysis / ".codebase-learning" / "state.json", state)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertIn(
                "awaiting_learner_confirmation requires exactly one verified module",
                payload["errors"],
            )

    def test_rejects_course_complete_while_modules_are_still_planned(self):
        """A premature course_complete phase would hide unfinished curriculum work."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = root / "code-analysis"
            analysis.mkdir()
            (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
            (analysis / "00-project-overview.md").write_text("# Project Overview\n", encoding="utf-8")
            state = roadmap_state()
            state["phase"] = "course_complete"
            write_json(analysis / ".codebase-learning" / "state.json", state)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertIn(
                "course_complete requires every module to be completed or skipped",
                payload["errors"],
            )

    def test_rejects_verified_module_without_its_module_readme(self):
        """Lesson files alone cannot satisfy the Module-level teaching contract."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = root / "code-analysis"
            analysis.mkdir()
            (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
            (analysis / "00-project-overview.md").write_text("# Project Overview\n", encoding="utf-8")
            state = roadmap_state()
            state.update(
                {
                    "phase": "awaiting_learner_confirmation",
                    "current_module": "01-agent-runtime",
                }
            )
            state["modules"][0].update(
                {
                    "status": "verified",
                    "verification": verification(
                        "passed", ["python demo/main.py"]
                    ),
                }
            )
            module_dir = analysis / "01-agent-runtime"
            (module_dir / "notebook").mkdir(parents=True)
            (module_dir / "notebook" / "01-loop.md").write_text("# Loop\n", encoding="utf-8")
            demo_dir = module_dir / "demo" / "01-loop"
            demo_dir.mkdir(parents=True)
            (demo_dir / "README.md").write_text("# Demo\n", encoding="utf-8")
            write_json(analysis / ".codebase-learning" / "state.json", state)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertIn(
                "verified module requires README.md: 01-agent-runtime",
                payload["errors"],
            )

    def test_rejects_non_array_modules_state(self):
        """Skipping validation for a malformed modules object would bypass all Module Gates."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = root / "code-analysis"
            analysis.mkdir()
            (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
            (analysis / "00-project-overview.md").write_text("# Project Overview\n", encoding="utf-8")
            state = awaiting_track_state()
            state["phase"] = "blocked"
            state["modules"] = {}
            write_json(analysis / ".codebase-learning" / "state.json", state)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertIn("modules must be an array", payload["errors"])

    def test_rejects_module_id_with_path_traversal(self):
        """Using an untrusted Module ID as a path could escape code-analysis/."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = root / "code-analysis"
            analysis.mkdir()
            (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
            (analysis / "00-project-overview.md").write_text("# Project Overview\n", encoding="utf-8")
            state = roadmap_state()
            state["modules"][0]["id"] = "01-../outside"
            write_json(analysis / ".codebase-learning" / "state.json", state)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertIn("invalid module id: 01-../outside", payload["errors"])

    def test_rejects_state_without_canonical_inventory(self):
        """A missing inventory would make source identity and drift checks unverifiable."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = root / "code-analysis"
            analysis.mkdir()
            (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
            (analysis / "00-project-overview.md").write_text("# Project Overview\n", encoding="utf-8")
            state_path = analysis / ".codebase-learning" / "state.json"
            write_json(state_path, awaiting_track_state())
            (state_path.parent / "inventory.json").unlink()

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertIn(
                "missing code-analysis/.codebase-learning/inventory.json",
                payload["errors"],
            )

    def test_rejects_state_inventory_fingerprint_mismatch(self):
        """A stale state fingerprint must not pass source-drift validation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = root / "code-analysis"
            analysis.mkdir()
            (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
            (analysis / "00-project-overview.md").write_text("# Project Overview\n", encoding="utf-8")
            state_path = analysis / ".codebase-learning" / "state.json"
            write_json(state_path, awaiting_track_state())
            inventory_path = state_path.parent / "inventory.json"
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            inventory["fingerprint"] = OTHER_FINGERPRINT
            inventory_path.write_text(
                json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertIn(
                "state source fingerprint does not match inventory fingerprint",
                payload["errors"],
            )

    def test_rejects_malformed_required_state_fields(self):
        """Malformed required fields must not bypass resume and Gate decisions."""
        cases = [
            (
                "skill_version",
                lambda state: state.update({"skill_version": None}),
                "skill_version must be a non-empty string",
            ),
            (
                "roadmap_version",
                lambda state: state.update({"roadmap_version": -1}),
                "roadmap_version must be a non-negative integer",
            ),
            (
                "confirmations",
                lambda state: state.update({"confirmations": {}}),
                "confirmations must be an array",
            ),
            (
                "source_dirty",
                lambda state: state["source"].update({"dirty": "false"}),
                "source.dirty must be a boolean",
            ),
            (
                "source_kind",
                lambda state: state["source"].update({"kind": "mystery"}),
                "source.kind must be 'git' or 'filesystem'",
            ),
        ]

        for label, mutate, expected_error in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                analysis = root / "code-analysis"
                analysis.mkdir()
                (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
                (analysis / "00-project-overview.md").write_text(
                    "# Project Overview\n", encoding="utf-8"
                )
                state = awaiting_track_state()
                mutate(state)
                write_json(analysis / ".codebase-learning" / "state.json", state)

                result = subprocess.run(
                    [sys.executable, str(SCRIPT), str(root)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )

                self.assertEqual(result.returncode, 1)
                payload = json.loads(result.stdout)
                self.assertIn(expected_error, payload["errors"])

    def test_rejects_malformed_or_mismatched_inventory_identity(self):
        """Invalid inventory identity must not be accepted as the course source snapshot."""
        cases = [
            (
                "schema",
                lambda inventory: inventory.update({"schema_version": 2}),
                "unsupported inventory schema_version: 2",
            ),
            (
                "root",
                lambda inventory: inventory.update({"root": "C:/private/project"}),
                "inventory root must be '.'",
            ),
            (
                "revision",
                lambda inventory: inventory["source"].update({"revision": "other"}),
                "state source revision does not match inventory source revision",
            ),
        ]

        for label, mutate, expected_error in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                analysis = root / "code-analysis"
                analysis.mkdir()
                (analysis / "README.md").write_text("# Codebase Learning\n", encoding="utf-8")
                (analysis / "00-project-overview.md").write_text(
                    "# Project Overview\n", encoding="utf-8"
                )
                state_path = analysis / ".codebase-learning" / "state.json"
                write_json(state_path, awaiting_track_state())
                inventory_path = state_path.parent / "inventory.json"
                inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
                mutate(inventory)
                inventory_path.write_text(
                    json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )

                result = subprocess.run(
                    [sys.executable, str(SCRIPT), str(root)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )

                self.assertEqual(result.returncode, 1)
                payload = json.loads(result.stdout)
                self.assertIn(expected_error, payload["errors"])

    def test_rejects_malformed_inventory_collections_and_source_fields(self):
        """A parseable inventory still needs the schema used by drift and coverage checks."""
        cases = [
            (
                "files",
                lambda inventory: inventory.update({"files": {}}),
                "inventory files must be an array",
            ),
            (
                "excluded_files",
                lambda inventory: inventory.update({"excluded_files": {}}),
                "inventory excluded_files must be an array",
            ),
            (
                "summary",
                lambda inventory: inventory.update({"summary": []}),
                "inventory summary must be an object",
            ),
            (
                "source_dirty",
                lambda inventory: inventory["source"].update({"dirty": "false"}),
                "inventory source.dirty must be a boolean",
            ),
            (
                "source_kind",
                lambda inventory: inventory["source"].update({"kind": "mystery"}),
                "inventory source.kind must be 'git' or 'filesystem'",
            ),
        ]

        for label, mutate, expected_error in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                analysis = write_course(root, awaiting_track_state())
                inventory_path = analysis / ".codebase-learning" / "inventory.json"
                inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
                mutate(inventory)
                inventory_path.write_text(
                    json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )

                result, payload = run_validator(root)

                self.assertEqual(result.returncode, 1)
                self.assertIn(expected_error, payload["errors"])

    def test_rejects_roadmap_gate_without_a_nonempty_all_planned_route(self):
        """Roadmap approval must never target an empty or already-active route."""
        cases = [
            (
                "empty",
                lambda state: state.update({"modules": []}),
                "awaiting_roadmap_confirmation requires at least one module",
            ),
            (
                "active",
                lambda state: state["modules"][0].update({"status": "building"}),
                "awaiting_roadmap_confirmation requires every module to be planned",
            ),
        ]

        for label, mutate, expected_error in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                state = roadmap_state()
                mutate(state)
                write_course(root, state)

                result, payload = run_validator(root)

                self.assertEqual(result.returncode, 1)
                self.assertIn(expected_error, payload["errors"])

    def test_rejects_phase_specific_current_module_mismatches(self):
        """Each resumable phase needs one unambiguous current Module."""
        cases = []

        verifying = roadmap_state()
        verifying.update(
            {"phase": "verifying_module", "current_module": "01-agent-runtime"}
        )
        cases.append(
            (
                "verifying_without_building",
                verifying,
                "verifying_module requires exactly one building module",
            )
        )

        learner = roadmap_state()
        learner.update(
            {
                "phase": "awaiting_learner_confirmation",
                "current_module": "02-tool-execution",
            }
        )
        learner["modules"][0].update(
            {
                "status": "verified",
                "verification": verification("passed"),
            }
        )
        cases.append(
            (
                "learner_pointer",
                learner,
                "current_module must match the only verified module: 01-agent-runtime",
            )
        )

        advance = roadmap_state()
        advance.update(
            {"phase": "awaiting_advance", "current_module": "02-tool-execution"}
        )
        advance["modules"][0].update(
            {
                "status": "completed",
                "verification": verification("passed"),
            }
        )
        advance["confirmations"].extend(
            [
                confirmation("roadmap", roadmap_version=1),
                confirmation(
                    "learner_completion", module_id="01-agent-runtime"
                ),
            ]
        )
        cases.append(
            (
                "advance_pointer",
                advance,
                "awaiting_advance current_module must be the latest completed or skipped module",
            )
        )

        for label, state, expected_error in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                analysis = write_course(root, state)
                for module in state["modules"]:
                    if module["status"] in {"verified", "completed"}:
                        add_module_artifacts(analysis, module["id"])

                result, payload = run_validator(root)

                self.assertEqual(result.returncode, 1)
                self.assertIn(expected_error, payload["errors"])

    def test_rejects_terminal_module_without_matching_user_confirmation(self):
        """Artifact state alone cannot prove that the learner completed or skipped work."""
        cases = [
            (
                "completed",
                "completed",
                "completed module requires learner_completion confirmation for roadmap_version 1 and module_revision 1: 01-agent-runtime",
            ),
            (
                "skipped",
                "skipped",
                "skipped module requires skip confirmation for roadmap_version 1 and module_revision 1: 01-agent-runtime",
            ),
        ]

        for label, status, expected_error in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                state = roadmap_state()
                state.update(
                    {"phase": "awaiting_advance", "current_module": "01-agent-runtime"}
                )
                state["modules"][0]["status"] = status
                if status == "completed":
                    state["modules"][0]["verification"] = verification("passed")
                state["confirmations"].append(
                    confirmation("roadmap", roadmap_version=1)
                )
                analysis = write_course(root, state)
                if status == "completed":
                    add_module_artifacts(analysis, "01-agent-runtime")

                result, payload = run_validator(root)

                self.assertEqual(result.returncode, 1)
                self.assertIn(expected_error, payload["errors"])

    def test_rejects_missing_or_invalid_module_revision(self):
        """Every Module needs a positive attempt identity before confirmations can bind it."""
        cases = [
            ("missing", lambda module: module.pop("module_revision")),
            ("zero", lambda module: module.update({"module_revision": 0})),
            ("boolean", lambda module: module.update({"module_revision": True})),
            ("string", lambda module: module.update({"module_revision": "1"})),
        ]

        for label, mutate in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                state = roadmap_state()
                for module in state["modules"]:
                    module["module_revision"] = 1
                mutate(state["modules"][0])
                write_course(root, state)

                result, payload = run_validator(root)

                self.assertEqual(result.returncode, 1)
                self.assertIn(
                    "module_revision must be a positive integer: 01-agent-runtime",
                    payload["errors"],
                )

    def test_rejects_unbound_module_confirmation_attempt(self):
        """A Module-level decision must name both the route and exact Module attempt."""
        cases = [
            (
                "missing_roadmap_version",
                {
                    "gate": "advance",
                    "module_id": "02-tool-execution",
                    "module_revision": 1,
                    "at": "2026-01-01T00:00:00Z",
                    "summary": "User confirmed advance",
                },
                "advance confirmation at index 0 requires a non-negative roadmap_version",
            ),
            (
                "missing_module_revision",
                {
                    "gate": "advance",
                    "module_id": "02-tool-execution",
                    "roadmap_version": 1,
                    "at": "2026-01-01T00:00:00Z",
                    "summary": "User confirmed advance",
                },
                "advance confirmation at index 0 requires a positive module_revision",
            ),
        ]

        for label, event, expected_error in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                state = awaiting_track_state()
                state["confirmations"] = [event]
                write_course(root, state)

                result, payload = run_validator(root)

                self.assertEqual(result.returncode, 1)
                self.assertIn(expected_error, payload["errors"])

    def test_rejects_replayed_module_confirmations(self):
        """Old learner, skip, and advance decisions cannot authorize a new route or attempt."""
        cases = []

        for gate, status in (
            ("learner_completion", "completed"),
            ("skip", "skipped"),
        ):
            state = roadmap_state()
            state.update(
                {
                    "phase": "awaiting_advance",
                    "current_module": "01-agent-runtime",
                    "roadmap_version": 2,
                }
            )
            for module in state["modules"]:
                module["module_revision"] = 2
            state["modules"][0]["status"] = status
            if status == "completed":
                state["modules"][0]["verification"] = verification("passed")
            state["confirmations"].extend(
                [
                    confirmation("roadmap", roadmap_version=2),
                    confirmation(
                        gate,
                        module_id="01-agent-runtime",
                        roadmap_version=1,
                        module_revision=1,
                    ),
                ]
            )
            cases.append(
                (
                    gate,
                    state,
                    f"{status} module requires {gate} confirmation for roadmap_version 2 and module_revision 2: 01-agent-runtime",
                    ["01-agent-runtime"] if status == "completed" else [],
                )
            )

        advance = roadmap_state()
        advance.update(
            {
                "phase": "building_module",
                "current_module": "02-tool-execution",
                "roadmap_version": 2,
            }
        )
        advance["modules"][0].update(
            {
                "module_revision": 1,
                "status": "completed",
                "verification": verification("passed"),
            }
        )
        advance["modules"][1].update(
            {"module_revision": 2, "status": "building"}
        )
        advance["confirmations"].extend(
            [
                confirmation("roadmap", roadmap_version=2),
                confirmation(
                    "learner_completion",
                    module_id="01-agent-runtime",
                    roadmap_version=2,
                    module_revision=1,
                ),
                confirmation(
                    "advance",
                    module_id="02-tool-execution",
                    roadmap_version=1,
                    module_revision=1,
                ),
            ]
        )
        cases.append(
            (
                "advance",
                advance,
                "later module work requires advance confirmation for roadmap_version 2 and module_revision 2: 02-tool-execution",
                ["01-agent-runtime"],
            )
        )

        for label, state, expected_error, artifact_ids in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                analysis = write_course(root, state)
                for module_id in artifact_ids:
                    add_module_artifacts(analysis, module_id)

                result, payload = run_validator(root)

                self.assertEqual(result.returncode, 1)
                self.assertIn(expected_error, payload["errors"])

    def test_rejects_module_work_without_current_roadmap_approval(self):
        """A selected Track is not authorization to create Module artifacts."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state = roadmap_state()
            state.update(
                {"phase": "building_module", "current_module": "01-agent-runtime"}
            )
            state["modules"][0]["status"] = "building"
            write_course(root, state)

            result, payload = run_validator(root)

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "module work requires roadmap confirmation for version 1",
                payload["errors"],
            )

    def test_accepts_consistent_states_at_every_steady_gate(self):
        """Strict phase checks must still admit every documented legal pause point."""
        base = roadmap_state()
        base["confirmations"].append(confirmation("roadmap", roadmap_version=1))

        states = []

        roadmap = roadmap_state()
        states.append(("roadmap", roadmap, []))

        building = copy.deepcopy(base)
        building.update(
            {"phase": "building_module", "current_module": "01-agent-runtime"}
        )
        building["modules"][0]["status"] = "building"
        states.append(("building", building, []))

        verifying = copy.deepcopy(building)
        verifying["phase"] = "verifying_module"
        verifying["modules"][0]["verification"] = verification(
            "running", ["python demo.py"]
        )
        states.append(("verifying", verifying, ["01-agent-runtime"]))

        learner = copy.deepcopy(base)
        learner.update(
            {
                "phase": "awaiting_learner_confirmation",
                "current_module": "01-agent-runtime",
            }
        )
        learner["modules"][0].update(
            {
                "status": "verified",
                "verification": verification("passed"),
            }
        )
        states.append(("learner", learner, ["01-agent-runtime"]))

        advance = copy.deepcopy(base)
        advance.update(
            {"phase": "awaiting_advance", "current_module": "01-agent-runtime"}
        )
        advance["modules"][0].update(
            {
                "status": "completed",
                "verification": verification("passed"),
            }
        )
        advance["confirmations"].append(
            confirmation("learner_completion", module_id="01-agent-runtime")
        )
        states.append(("advance", advance, ["01-agent-runtime"]))

        complete = copy.deepcopy(base)
        complete.update(
            {"phase": "course_complete", "current_module": "02-tool-execution"}
        )
        for module in complete["modules"]:
            module.update(
                {
                    "status": "completed",
                    "verification": verification("passed"),
                }
            )
            complete["confirmations"].append(
                confirmation("learner_completion", module_id=module["id"])
            )
        complete["confirmations"].append(
            confirmation("advance", module_id="02-tool-execution")
        )
        states.append(
            (
                "complete",
                complete,
                ["01-agent-runtime", "02-tool-execution"],
            )
        )

        for label, state, artifact_ids in states:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                analysis = write_course(root, state)
                for module_id in artifact_ids:
                    add_module_artifacts(analysis, module_id)

                result, payload = run_validator(root)

                self.assertEqual(result.returncode, 0, payload["errors"])
                self.assertTrue(payload["valid"])

    def test_stale_source_requires_and_reports_a_source_identity_difference(self):
        """The drift phase should preserve a detected mismatch without treating it as corruption."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state = awaiting_track_state()
            state["phase"] = "stale_source"
            state["resume_phase"] = "awaiting_track"
            state["last_error"] = "Source snapshot changed"
            analysis = write_course(root, state)
            refresh_inventory_with_source(root, analysis)

            result, payload = run_validator(root)

            self.assertEqual(result.returncode, 0, payload["errors"])
            self.assertTrue(payload["valid"])
            self.assertIn(
                "state source fingerprint does not match inventory fingerprint",
                payload["warnings"],
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state = awaiting_track_state()
            state["phase"] = "stale_source"
            state["resume_phase"] = "awaiting_track"
            state["last_error"] = "Source snapshot changed"
            write_course(root, state)

            result, payload = run_validator(root)

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "stale_source requires a source identity difference",
                payload["errors"],
            )

    def test_rejects_later_module_work_without_advance_confirmation(self):
        """Roadmap approval must not silently authorize every future Module build."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state = roadmap_state()
            state.update(
                {"phase": "building_module", "current_module": "02-tool-execution"}
            )
            state["modules"][0].update(
                {
                    "status": "completed",
                    "verification": verification("passed"),
                }
            )
            state["modules"][1]["status"] = "building"
            state["confirmations"].extend(
                [
                    confirmation("roadmap", roadmap_version=1),
                    confirmation(
                        "learner_completion", module_id="01-agent-runtime"
                    ),
                ]
            )
            analysis = write_course(root, state)
            add_module_artifacts(analysis, "01-agent-runtime")

            result, payload = run_validator(root)

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "later module work requires advance confirmation for roadmap_version 1 and module_revision 1: 02-tool-execution",
                payload["errors"],
            )

    def test_selected_scope_requires_its_own_confirmation(self):
        """A scoped monorepo rescan must remain traceable to the user's scope choice."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "apps" / "api").mkdir(parents=True)
            state = awaiting_track_state()
            state["selected_scope"] = "apps/api"
            state["source"]["inventory_fingerprint"] = empty_inventory_fingerprint(
                "apps/api"
            )
            write_course(root, state)

            result, payload = run_validator(root)

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "selected scope requires a matching scope confirmation", payload["errors"]
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "apps" / "api").mkdir(parents=True)
            state = awaiting_track_state()
            state["selected_scope"] = "apps/api"
            state["source"]["inventory_fingerprint"] = empty_inventory_fingerprint(
                "apps/api"
            )
            state["confirmations"].append(
                confirmation("scope", scope="apps/api")
            )
            write_course(root, state)

            result, payload = run_validator(root)

            self.assertEqual(result.returncode, 0, payload["errors"])

    def test_rejects_active_module_with_unfinished_predecessor(self):
        """An advance confirmation cannot bypass the dependency-ordered Module sequence."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state = roadmap_state()
            state.update(
                {"phase": "building_module", "current_module": "02-tool-execution"}
            )
            state["modules"][1]["status"] = "building"
            state["confirmations"].extend(
                [
                    confirmation("roadmap", roadmap_version=1),
                    confirmation("advance", module_id="02-tool-execution"),
                ]
            )
            write_course(root, state)

            result, payload = run_validator(root)

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "active module requires completed/skipped predecessors: 02-tool-execution",
                payload["errors"],
            )

    def test_rejects_evidence_free_or_forward_dependent_roadmap_modules(self):
        """A route must encode source evidence, goals, verification, and earlier dependencies."""
        cases = [
            (
                "depends_on",
                lambda module: module.pop("depends_on"),
                "module depends_on must be an array: 01-agent-runtime",
            ),
            (
                "forward_dependency",
                lambda module: module.update({"depends_on": ["02-tool-execution"]}),
                "module dependency must reference an earlier module: 01-agent-runtime -> 02-tool-execution",
            ),
            (
                "source_areas",
                lambda module: module.update({"source_areas": []}),
                "module source_areas must be a non-empty array: 01-agent-runtime",
            ),
            (
                "learning_goal",
                lambda module: module.update({"learning_goal": ""}),
                "module learning_goal must be a non-empty string: 01-agent-runtime",
            ),
            (
                "verification",
                lambda module: module.update({"verification": None}),
                "module verification must be an object: 01-agent-runtime",
            ),
        ]

        for label, mutate, expected_error in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                state = roadmap_state()
                mutate(state["modules"][0])
                write_course(root, state)

                result, payload = run_validator(root)

                self.assertEqual(result.returncode, 1)
                self.assertIn(expected_error, payload["errors"])

    def test_malformed_unhashable_state_values_return_json_diagnostics(self):
        """Recovery validation must diagnose JSON arrays instead of crashing on set lookup."""
        cases = [
            (
                "phase",
                lambda state: state.update({"phase": []}),
                "phase must be a known string: []",
            ),
            (
                "status",
                lambda state: state["modules"][0].update({"status": []}),
                "unknown module status for 01-agent-runtime: []",
            ),
            (
                "module_id",
                lambda state: state["modules"][0].update({"id": []}),
                "invalid module id: []",
            ),
        ]

        for label, mutate, expected_error in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                state = roadmap_state()
                mutate(state)
                write_course(root, state)

                result = subprocess.run(
                    [sys.executable, str(SCRIPT), str(root)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )

                self.assertEqual(result.returncode, 1, result.stderr)
                payload = json.loads(result.stdout)
                self.assertIn(expected_error, payload["errors"])

    def test_rejects_malformed_or_unbound_confirmation_events(self):
        """Authorization evidence must identify a real Gate, decision, and target."""
        cases = [
            (
                "unhashable_gate",
                {"gate": [], "module_id": None, "at": "now", "summary": "x"},
                "confirmation at index 0 requires a string gate",
            ),
            (
                "unknown_gate",
                {"gate": "magic", "module_id": None, "at": "now", "summary": "x"},
                "unknown confirmation gate at index 0: magic",
            ),
            (
                "missing_at",
                {"gate": "track", "module_id": None, "summary": "x", "track": "Agent"},
                "confirmation at index 0 requires a non-empty at timestamp",
            ),
            (
                "missing_summary",
                {"gate": "track", "module_id": None, "at": "now", "track": "Agent"},
                "confirmation at index 0 requires a non-empty summary",
            ),
            (
                "course_module_binding",
                {
                    "gate": "track",
                    "module_id": "01-agent-runtime",
                    "at": "now",
                    "summary": "x",
                    "track": "Agent",
                },
                "track confirmation at index 0 requires module_id=null",
            ),
            (
                "module_binding",
                {"gate": "advance", "module_id": None, "at": "now", "summary": "x"},
                "advance confirmation at index 0 requires a valid module_id",
            ),
            (
                "roadmap_version",
                {"gate": "roadmap", "module_id": None, "at": "now", "summary": "x"},
                "roadmap confirmation at index 0 requires a non-negative roadmap_version",
            ),
        ]

        for label, event, expected_error in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                state = awaiting_track_state()
                state["confirmations"] = [event]
                write_course(root, state)

                result, payload = run_validator(root)

                self.assertEqual(result.returncode, 1)
                self.assertIn(expected_error, payload["errors"])

    def test_rejects_unsafe_or_unbound_selected_scope(self):
        """A persisted scope must remain inside the repository and match its confirmation."""
        cases = [
            (
                "traversal",
                "../outside",
                confirmation("scope", scope="../outside"),
                "selected_scope must be a normalized repo-relative POSIX path",
            ),
            (
                "absolute",
                "C:/outside",
                confirmation("scope", scope="C:/outside"),
                "selected_scope must be a normalized repo-relative POSIX path",
            ),
            (
                "generated_tree",
                "code-analysis",
                confirmation("scope", scope="code-analysis"),
                "selected_scope must be a normalized repo-relative POSIX path",
            ),
            (
                "mismatch",
                "apps/api",
                confirmation("scope", scope="apps/web"),
                "selected scope requires a matching scope confirmation",
            ),
        ]

        for label, scope, event, expected_error in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                (root / "apps" / "api").mkdir(parents=True)
                state = awaiting_track_state()
                state["selected_scope"] = scope
                state["source"]["inventory_fingerprint"] = empty_inventory_fingerprint(
                    scope
                )
                state["confirmations"] = [event]
                write_course(root, state)

                result, payload = run_validator(root)

                self.assertEqual(result.returncode, 1)
                self.assertIn(expected_error, payload["errors"])

    def test_side_phases_require_reason_and_resumable_context(self):
        """A side phase without recovery context cannot be resumed deterministically."""
        for phase in ("blocked", "needs_recovery"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                state = awaiting_track_state()
                state["phase"] = phase
                write_course(root, state)

                result, payload = run_validator(root)

                self.assertEqual(result.returncode, 1)
                self.assertIn(
                    f"{phase} requires a non-empty last_error", payload["errors"]
                )
                self.assertIn(
                    f"{phase} requires a resumable resume_phase", payload["errors"]
                )

    def test_rejects_missing_or_unsafe_source_areas(self):
        """Roadmap source evidence must resolve to an existing path inside the repository."""
        cases = [
            (
                "missing",
                "src/missing.py",
                "module source_area does not exist: 01-agent-runtime -> src/missing.py",
            ),
            (
                "traversal",
                "../outside.py",
                "module source_area must be repo-relative POSIX: 01-agent-runtime -> ../outside.py",
            ),
        ]

        for label, source_area, expected_error in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                state = roadmap_state()
                state["modules"][0]["source_areas"] = [source_area]
                write_course(root, state)

                result, payload = run_validator(root)

                self.assertEqual(result.returncode, 1)
                self.assertIn(expected_error, payload["errors"])

    def test_rejects_symlinked_course_artifact_tree(self):
        """Course writes must never escape code-analysis through a symlinked directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            outside = root / "outside"
            outside.mkdir()
            analysis = root / "code-analysis"
            try:
                analysis.symlink_to(outside, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"symlink creation unavailable: {error}")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 1, result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("code-analysis must not be a symlink", payload["errors"])

    def test_detects_windows_reparse_points_even_when_not_symlinks(self):
        """NTFS junctions must receive the same write-boundary treatment as symlinks."""
        reparse_flag = 0x400
        metadata = SimpleNamespace(
            st_mode=stat.S_IFDIR,
            st_file_attributes=reparse_flag,
        )
        with mock.patch.object(Path, "lstat", return_value=metadata), mock.patch.object(
            VALIDATOR_MODULE.stat,
            "FILE_ATTRIBUTE_REPARSE_POINT",
            reparse_flag,
            create=True,
        ):
            self.assertTrue(VALIDATOR_MODULE.is_link_or_reparse(Path("junction")))

    def test_passed_verification_requires_commands_timestamp_and_result_notes(self):
        """A passed flag without reproducible evidence must not unlock the learner Gate."""
        cases = [
            (
                "commands",
                lambda proof: proof.update({"commands": []}),
                "passed verification requires non-empty commands: 01-agent-runtime",
            ),
            (
                "checked_at",
                lambda proof: proof.update({"checked_at": None}),
                "passed verification requires checked_at: 01-agent-runtime",
            ),
            (
                "notes",
                lambda proof: proof.update({"notes": None}),
                "passed verification requires result notes: 01-agent-runtime",
            ),
        ]

        for label, mutate, expected_error in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                state = roadmap_state()
                state.update(
                    {
                        "phase": "awaiting_learner_confirmation",
                        "current_module": "01-agent-runtime",
                    }
                )
                state["modules"][0].update(
                    {"status": "verified", "verification": verification("passed")}
                )
                mutate(state["modules"][0]["verification"])
                state["confirmations"].append(
                    confirmation("roadmap", roadmap_version=1)
                )
                analysis = write_course(root, state)
                add_module_artifacts(analysis, "01-agent-runtime")

                result, payload = run_validator(root)

                self.assertEqual(result.returncode, 1)
                self.assertIn(expected_error, payload["errors"])

    def test_planning_route_cannot_contain_active_module_work(self):
        """The transitional route phase must not bypass roadmap approval."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state = roadmap_state()
            state["phase"] = "planning_route"
            state["modules"][0]["status"] = "building"
            write_course(root, state)

            result, payload = run_validator(root)

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "planning_route allows only planned modules", payload["errors"]
            )

    def test_side_phase_applies_the_resume_phase_contract(self):
        """A side-state label must not hide a structurally impossible resume target."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state = roadmap_state()
            state.update(
                {
                    "phase": "blocked",
                    "resume_phase": "awaiting_track",
                    "last_error": "Interrupted",
                }
            )
            write_course(root, state)

            result, payload = run_validator(root)

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "awaiting_track requires selected_track to be null", payload["errors"]
            )
            self.assertIn("awaiting_track requires modules to be empty", payload["errors"])

    def test_rejects_unsafe_or_malformed_inventory_entries(self):
        """Persisted inventory paths and hashes must not become a path-traversal input."""
        digest = "a" * 64
        cases = [
            (
                "path",
                [{"path": "../../secret", "bytes": 1, "sha256": digest}],
                [],
                "inventory file path must be repo-relative POSIX: ../../secret",
            ),
            (
                "analysis_path",
                [{"path": "code-analysis/README.md", "bytes": 1, "sha256": digest}],
                [],
                "inventory file path must exclude code-analysis: code-analysis/README.md",
            ),
            (
                "digest",
                [{"path": "src/tools.py", "bytes": 1, "sha256": "x"}],
                [],
                "inventory file sha256 is invalid: src/tools.py",
            ),
            (
                "duplicate",
                [
                    {"path": "src/tools.py", "bytes": 1, "sha256": digest},
                    {"path": "src/tools.py", "bytes": 1, "sha256": digest},
                ],
                [],
                "duplicate inventory path: src/tools.py",
            ),
            (
                "reason",
                [],
                [{"path": "src/tools.py", "reason": "invented"}],
                "inventory excluded reason is invalid: src/tools.py -> invented",
            ),
        ]

        for label, files, excluded, expected_error in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                analysis = write_course(root, awaiting_track_state())
                inventory_path = analysis / ".codebase-learning" / "inventory.json"
                inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
                inventory["files"] = files
                inventory["excluded_files"] = excluded
                inventory_path.write_text(
                    json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )

                result, payload = run_validator(root)

                self.assertEqual(result.returncode, 1)
                self.assertIn(expected_error, payload["errors"])

    def test_stale_source_allows_missing_saved_source_area_as_a_warning(self):
        """A deleted source path is drift evidence, not corruption of an otherwise safe state."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state = roadmap_state()
            state.update(
                {
                    "phase": "stale_source",
                    "resume_phase": "awaiting_roadmap_confirmation",
                    "last_error": "A source path was deleted",
                }
            )
            state["modules"][0]["source_areas"] = ["src/deleted.py"]
            analysis = write_course(root, state)
            refresh_inventory_with_source(root, analysis)

            result, payload = run_validator(root)

            self.assertEqual(result.returncode, 0, payload["errors"])
            self.assertIn(
                "module source_area does not exist: 01-agent-runtime -> src/deleted.py",
                payload["warnings"],
            )

    def test_inventory_fingerprint_and_summary_must_match_entries(self):
        """Coverage metadata must be derived from, not merely adjacent to, inventory entries."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analysis = write_course(root, awaiting_track_state())
            inventory_path = analysis / ".codebase-learning" / "inventory.json"
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            inventory["files"] = [
                {"path": "src/tools.py", "bytes": 17, "sha256": "a" * 64}
            ]
            inventory_path.write_text(
                json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            result, payload = run_validator(root)

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "inventory fingerprint does not match its entries", payload["errors"]
            )
            self.assertIn(
                "inventory summary.included_files does not match files", payload["errors"]
            )

    def test_verified_demo_requires_a_non_readme_implementation_artifact(self):
        """A README-only directory is documentation, not a runnable teaching Demo."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state = roadmap_state()
            state.update(
                {
                    "phase": "awaiting_learner_confirmation",
                    "current_module": "01-agent-runtime",
                }
            )
            state["modules"][0].update(
                {"status": "verified", "verification": verification("passed")}
            )
            state["confirmations"].append(
                confirmation("roadmap", roadmap_version=1)
            )
            analysis = write_course(root, state)
            module_dir = analysis / "01-agent-runtime"
            (module_dir / "notebook").mkdir(parents=True)
            (module_dir / "notebook" / "01-loop.md").write_text(
                "# Lesson\n", encoding="utf-8"
            )
            demo = module_dir / "demo" / "01-loop"
            demo.mkdir(parents=True)
            (demo / "README.md").write_text("# Demo\n", encoding="utf-8")
            (module_dir / "README.md").write_text("# Module\n", encoding="utf-8")

            result, payload = run_validator(root)

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "verified module demo requires a non-README implementation artifact: "
                "01-agent-runtime/01-loop",
                payload["errors"],
            )

    def test_inventory_scope_must_match_state_and_contain_every_entry(self):
        """A confirmed monorepo scope must be bound to the exact inventory coverage."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "apps" / "api").mkdir(parents=True)
            (root / "apps" / "web").mkdir(parents=True)
            state = awaiting_track_state()
            state["selected_scope"] = "apps/api"
            state["source"]["inventory_fingerprint"] = empty_inventory_fingerprint(
                "apps/api"
            )
            state["confirmations"] = [confirmation("scope", scope="apps/api")]
            analysis = write_course(root, state)
            inventory_path = analysis / ".codebase-learning" / "inventory.json"
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            inventory["scope"] = "apps/web"
            inventory["fingerprint"] = empty_inventory_fingerprint("apps/web")
            inventory_path.write_text(
                json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            result, payload = run_validator(root)

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "inventory scope does not match selected_scope: apps/web != apps/api",
                payload["errors"],
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "apps" / "api").mkdir(parents=True)
            outside_file = root / "apps" / "web.py"
            outside_file.write_text("print('web')\n", encoding="utf-8")
            state = awaiting_track_state()
            state["selected_scope"] = "apps/api"
            state["source"]["inventory_fingerprint"] = empty_inventory_fingerprint(
                "apps/api"
            )
            state["confirmations"] = [confirmation("scope", scope="apps/api")]
            analysis = write_course(root, state)
            inventory_path = analysis / ".codebase-learning" / "inventory.json"
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            content = outside_file.read_bytes()
            inventory["files"] = [
                {
                    "path": "apps/web.py",
                    "bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            ]
            inventory["summary"]["included_files"] = 1
            inventory["fingerprint"] = VALIDATOR_MODULE.compute_inventory_fingerprint(
                inventory["files"], inventory["excluded_files"], "apps/api"
            )
            inventory_path.write_text(
                json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            result, payload = run_validator(root)

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "inventory file path is outside inventory scope: apps/web.py",
                payload["errors"],
            )


if __name__ == "__main__":
    unittest.main()
