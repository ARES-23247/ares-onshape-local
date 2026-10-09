"""Regression cases from uncertain browser submissions and successful no-op responses."""
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import local_workflow as w
import native_operations as j
import test_local_workflow as fixture
from test_local_workflow import DID, WID, EID, MID, URL, FEATURE


class OperationTests(unittest.TestCase):
    setUp, tearDown, make_receipt = fixture.LocalTests.setUp, fixture.LocalTests.tearDown, fixture.LocalTests.make_receipt

    def prepare(self, feature=None, operation="create", fid=""):
        return w.prepare_native_change("demo", EID, "head.json", feature or FEATURE, operation, fid)

    def after(self, manifest, mutate=None):
        data = self.make_receipt(name="after.json")
        r = data["response"]
        r["sourceMicroversion"] = "e" * 24
        feature = json.loads(Path(manifest["body_path"]).read_text())["feature"]
        if manifest["operation"] == "create":
            feature["featureId"] = "new/feature"
            r["features"].append(feature)
        else:
            r["features"][0] = feature
        if mutate:
            mutate(data)
        (self.root / "after.json").write_text(json.dumps(data))

    def test_pending_across_processes_and_observed_create(self):
        m = self.prepare()
        with self.assertRaisesRegex(ValueError, "pending"):
            self.prepare()
        j.record_native_submission(m["manifest"])
        j.record_native_submission(m["manifest"], "result_unobserved")
        with self.assertRaisesRegex(ValueError, "already recorded"):
            j.record_native_submission(m["manifest"])
        self.after(m)
        result = j.reconcile_native_change(m["manifest"], "after.json")
        self.assertEqual(result["bound_feature_ids"], ["new/feature"])
        self.assertEqual(result["state"], "RESULT_OBSERVED")
        self.assertFalse(result["live_geometry_verified"])
        with self.assertRaisesRegex(ValueError, "already reconciled"):
            j.reconcile_native_change(m["manifest"], "after.json")

    def test_successful_unchanged_update_does_not_bind(self):
        feature = {**FEATURE, "name": "Changed"}
        m = self.prepare(feature, "update", "test/feature+id")
        self.after(m, lambda d: d["response"]["features"][0].update(name="Test"))
        with self.assertRaisesRegex(ValueError, "unchanged"):
            j.reconcile_native_change(m["manifest"], "after.json")
        self.assertEqual(j.native_change_status(m["manifest"])["bound_feature_ids"], [])

    def test_duplicate_create_and_unchanged_head_remain_pending(self):
        m = self.prepare()
        with self.assertRaisesRegex(ValueError, "predates|not advanced"):
            j.reconcile_native_change(m["manifest"], "head.json")
        self.after(m, lambda d: d["response"]["features"].append(
            {**d["response"]["features"][-1], "featureId": "duplicate"}))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            j.reconcile_native_change(m["manifest"], "after.json")
        with self.assertRaisesRegex(ValueError, "pending"):
            self.prepare()

    def test_parameter_mismatch_body_tampering_and_foreign_readback(self):
        f = {**FEATURE, "parameters": [{"parameterId": "depth", "expression": "12 mm"}]}
        m = self.prepare(f)
        self.after(m, lambda d: d["response"]["features"][-1]["parameters"][0].update(expression="10 mm"))
        with self.assertRaisesRegex(ValueError, "matching"):
            j.reconcile_native_change(m["manifest"], "after.json")
        self.after(m, lambda d: d.update(requestUrl=URL.replace(DID, "f" * 24)))
        with self.assertRaisesRegex(ValueError, "selected design"):
            j.reconcile_native_change(m["manifest"], "after.json")
        Path(m["body_path"]).write_text("{}")
        with self.assertRaisesRegex(ValueError, "changed"):
            j.native_change_status(m["manifest"])

    def test_cancel_only_unsubmitted(self):
        m = self.prepare()
        j.record_native_submission(m["manifest"], "cancel_unsubmitted")
        other = self.prepare()
        j.record_native_submission(other["manifest"])
        with self.assertRaisesRegex(ValueError, "cannot cancel"):
            j.record_native_submission(other["manifest"], "cancel_unsubmitted")

    def test_already_observed_intent_is_not_recreated(self):
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.prepare({**FEATURE, "name": "Existing"})

    def test_nested_native_feature_references_are_part_of_intent(self):
        feature = {**FEATURE, "parameters": [{"parameterId": "entities", "queries": [
            {"featureId": "intended-sketch", "queryString": "native region query"}]}]}
        m = self.prepare(feature)
        self.after(m, lambda d: d["response"]["features"][-1]["parameters"][0]["queries"][0].update(featureId="wrong-sketch"))
        with self.assertRaisesRegex(ValueError, "matching"):
            j.reconcile_native_change(m["manifest"], "after.json")
        self.after(m)
        self.assertEqual(j.reconcile_native_change(m["manifest"], "after.json")["bound_feature_ids"], ["new/feature"])

    def test_transient_file_lock_retry_and_permanent_failure_preserve_prior_record(self):
        path = self.root / "record.json"
        path.write_text('{"prior": true}')
        original = Path.replace
        attempts = 0
        def transient(source, target):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise PermissionError("Simulated Windows file lock")
            return original(source, target)
        with patch.object(Path, "replace", transient), patch.object(j.time, "sleep"):
            j.atomic(path, {"changed": True})
        self.assertEqual(attempts, 3)
        self.assertEqual(json.loads(path.read_text()), {"changed": True})
        before = path.read_bytes()
        with patch.object(Path, "replace", side_effect=PermissionError("Persistent lock")), patch.object(j.time, "sleep"):
            with self.assertRaises(PermissionError):
                j.atomic(path, {"lost": True})
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(list(self.root.glob("*.ares-tmp")))

    def test_rejection_honors_retry_after_and_ambiguous_failure(self):
        m = self.prepare()
        data = {"method": "POST", "requestUrl": m["requestUrl"], "httpStatus": 500,
                "transport": w.SESSION, "observedAt": datetime.now(timezone.utc).isoformat(), "response": {}}
        (self.root / "rejected.json").write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            j.record_native_submission(m["manifest"], "rejected", "rejected.json")
        data.update(httpStatus=429, retryAfter=120)
        (self.root / "rejected.json").write_text(json.dumps(data))
        j.record_native_submission(m["manifest"], "rejected", "rejected.json")
        with self.assertRaisesRegex(ValueError, "Retry-After"):
            self.prepare()

    def test_new_standard_types_are_local_and_filter_guard(self):
        for feature_type in ("cPlane", "circularPattern", "linearPattern", "loft"):
            with self.subTest(feature_type=feature_type), patch("socket.socket", side_effect=AssertionError("No network")):
                m = self.prepare({**FEATURE, "featureType": feature_type})
                j.record_native_submission(m["manifest"], "cancel_unsubmitted")
        self.make_receipt(url=URL + "?rollbackBarIndex=2")
        with self.assertRaisesRegex(ValueError, "unfiltered"):
            self.prepare()
        d = self.make_receipt()
        d["response"]["isComplete"] = False
        (self.root / "head.json").write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError, "complete"):
            self.prepare()

    def test_read_only_library_cache_keeps_edit_guard(self):
        config_path = self.root / "onshape-project.json"
        config = json.loads(config_path.read_text())
        config["shared_references"]["library"] = {"document_id": "f" * 24, "element_ids": [EID]}
        config_path.write_text(json.dumps(config))
        url = URL.replace(DID, "f" * 24).replace("/w/" + WID, "/m/" + MID) + "?configuration=Exact%20variant"
        self.make_receipt(url=url, name="foreign.json")
        result = w.register_reference_snapshot("foreign.json", "library", True)
        self.assertFalse(result["editable_target"])
        self.assertTrue(w.lookup_snapshot(url)["hit"])
        self.assertFalse(w.lookup_snapshot(url.replace("Exact", "Other"))["hit"])
        self.assertEqual(w.search_snapshots("", "demo")["total_matches"], 1)
        with self.assertRaisesRegex(ValueError, "selected design"):
            w.prepare_native_change("demo", EID, "foreign.json", FEATURE)
        with self.assertRaisesRegex(ValueError, "configured"):
            w.register_reference_snapshot("foreign.json", "unknown", True)
        self.make_receipt(url=url.replace(EID, "e" * 24), name="foreign.json")
        with self.assertRaisesRegex(ValueError, "element"):
            w.register_reference_snapshot("foreign.json", "library", True)


if __name__ == "__main__":
    unittest.main()
