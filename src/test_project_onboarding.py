"""Onboarding must preserve existing ownership and keep private data outside account internals."""
import importlib.util
import json
from pathlib import Path
import unittest

import local_workflow as w
import test_local_workflow as fixture

spec = importlib.util.spec_from_file_location("project_onboarding",
    Path(__file__).resolve().parents[1] / "scripts/configure_project.py")
onboarding = importlib.util.module_from_spec(spec)
spec.loader.exec_module(onboarding)


class OnboardingTests(unittest.TestCase):
    setUp, tearDown, make_receipt = fixture.LocalTests.setUp, fixture.LocalTests.tearDown, fixture.LocalTests.make_receipt

    def test_new_design_and_read_only_source_preserve_original_registry(self):
        config = self.root / "onshape-project.json"
        onboarding.configure(config, self.root, "new-part", "e" * 24, "f" * 24)
        onboarding.configure(config, self.root, "library", "1" * 24, reference=True, element_ids=["2" * 24])
        current = w.registry()
        self.assertIn("demo", current["designs"])
        self.assertEqual(w.design_record("new-part")["onshape"]["document_id"], "e" * 24)
        self.assertEqual(current["shared_references"]["library"]["element_ids"], ["2" * 24])
        self.assertTrue(list(self.root.glob("onshape-project.json.ares-backup-*")))

    def test_conflicting_ownership_is_not_overwritten(self):
        config = self.root / "onshape-project.json"
        before = config.read_bytes()
        with self.assertRaisesRegex(ValueError, "already differs"):
            onboarding.configure(config, self.root, "demo", "e" * 24, "f" * 24)
        self.assertEqual(config.read_bytes(), before)

    def test_onboarding_cannot_write_account_or_outside_workspace_paths(self):
        for path in (self.root / ".claude/onshape-project.json", self.root.parent / "outside-project.json"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                onboarding.configure(path, self.root, "part", "e" * 24, "f" * 24)


if __name__ == "__main__":
    unittest.main()
