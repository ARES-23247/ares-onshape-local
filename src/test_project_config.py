"""Portable configuration boundaries and credential-free project data."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import project_config as project


class ProjectConfigTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parent / ".test-runs"
        base.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {"project": "Synthetic project", "designs": {"demo": {
            "onshape": {"document_id": "a" * 24, "workspace_id": "b" * 24}}},
            "shared_references": {}, "runtime_dir": ".ares-onshape", "snapshot_dirs": ["receipts"]}

    def save(self, data=None):
        (self.root / "onshape-project.json").write_text(json.dumps(data or self.config))

    def test_unconfigured_workspace_has_no_guessed_target(self):
        self.assertEqual(project.read_registry(self.root)["designs"], {})
        self.assertEqual(project.runtime_path("native-requests", self.root), self.root / ".ares-onshape/native-requests")

    def test_configured_workspace_with_arbitrary_design_name(self):
        self.config["designs"]["test-fixture"] = self.config["designs"].pop("demo")
        self.save()
        with patch("socket.socket", side_effect=AssertionError("No network")):
            self.assertIn("test-fixture", project.read_registry(self.root)["designs"])

    def test_sibling_paths_and_account_internals_are_rejected(self):
        for value in ("../outside", ".claude/settings.json", ".git/native-requests", ".gemini/events"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                project.workspace_path(value, self.root)

    def test_invalid_targets_and_reserved_owner_are_rejected(self):
        for change in ("document", "workspace", "reserved"):
            altered = copy.deepcopy(self.config)
            if change == "reserved":
                altered["designs"]["shared"] = altered["designs"].pop("demo")
            else:
                altered["designs"]["demo"]["onshape"][change + "_id"] = "placeholder"
            self.save(altered)
            with self.subTest(change=change), self.assertRaises(ValueError):
                project.read_registry(self.root)

    def test_credentials_are_rejected_at_any_depth(self):
        for name in ("api_key", "Authorization", "Cookie", "client_secret", "access_token"):
            altered = copy.deepcopy(self.config)
            altered["designs"]["demo"]["nested"] = {name: "synthetic-secret"}
            self.save(altered)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "credentials"):
                project.read_registry(self.root)

    def test_runtime_and_plan_paths_cannot_escape_workspace(self):
        for name in ("runtime_dir", "event_dir"):
            altered = {**self.config, name: "../outside"}
            self.save(altered)
            with self.subTest(name=name), self.assertRaises(ValueError):
                project.read_registry(self.root)
        self.config["designs"]["demo"]["plan"] = "../outside.md"
        self.save()
        with self.assertRaises(ValueError):
            project.read_registry(self.root)

    def test_path_lists_require_correct_types(self):
        self.save({**self.config, "snapshot_dirs": "receipts"})
        with self.assertRaisesRegex(ValueError, "array"):
            project.read_registry(self.root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
