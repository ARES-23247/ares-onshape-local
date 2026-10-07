"""Meaningful transport boundaries/provenance tests; synthetic data never contacts Onshape."""
from contextlib import closing
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import local_workflow as w

DID, WID, EID, MID = "a" * 24, "b" * 24, "c" * 24, "d" * 24
URL = f"https://cad.onshape.com/api/v12/partstudios/d/{DID}/w/{WID}/e/{EID}/features"
FEATURE = {"btType": "BTMFeature-134", "featureType": "extrude", "name": "Test", "parameters": []}


class LocalTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parent / ".test-runs"
        base.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.temp.name)
        design_dir = self.root / "designs/demo"
        design_dir.mkdir(parents=True)
        (design_dir / "PLAN.md").write_text("Synthetic plan")
        record = {"plan": "designs/demo/PLAN.md", "architecture": "Test",
                  "onshape": {"document_id": DID, "workspace_id": WID}}
        reg = {"project": "Synthetic fixture", "designs": {"demo": record}, "shared_references": {}}
        (self.root / "onshape-project.json").write_text(json.dumps(reg))
        self.patches = [patch.object(w, "WORKSPACE", self.root), patch.object(w, "DESIGNS", ("demo",)), patch.object(w, "DB_PATH", self.root / "cache.sqlite3")]
        for p in self.patches:
            p.start()
        self.make_receipt()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def make_receipt(self, url=URL, status="OK", age=0, name="head.json"):
        data = {"requestUrl": url, "method": "GET", "httpStatus": 200, "transport": w.SESSION,
                "observedAt": (datetime.now(timezone.utc) - timedelta(seconds=age)).isoformat(),
                "response": {"sourceMicroversion": MID, "serializationVersion": "1.2.14",
                             "features": [{**FEATURE, "featureId": "test/feature+id"}],
                             "featureStates": {"test/feature+id": {"featureStatus": status}}}}
        (self.root / name).write_text(json.dumps(data))
        return data

    def test_cache_exact_identity_and_stale_hash(self):
        url = URL.replace(f"/w/{WID}/", f"/m/{MID}/") + "?configuration=default&includeSuppressed=false"
        self.make_receipt(url=url, name="frozen.json")
        w.register_snapshot("frozen.json", "demo", True)
        self.assertTrue(w.lookup_snapshot(url)["hit"])
        self.assertFalse(w.lookup_snapshot(url, "mm")["hit"])
        self.assertFalse(w.lookup_snapshot(url.replace("false", "true"))["hit"])
        (self.root / "frozen.json").write_text("{}")
        self.assertFalse(w.lookup_snapshot(url)["hit"])
        with self.assertRaisesRegex(ValueError, "changed"):
            w.read_snapshot("frozen.json")
        (self.root / "frozen.json").unlink()
        self.assertFalse(w.lookup_snapshot(url)["hit"])

    def test_workspace_reads_are_never_cache_hits(self):
        w.register_snapshot("head.json", "demo", True)
        self.assertFalse(w.lookup_snapshot(URL)["hit"])

    def test_registration_requires_session_and_correct_owner(self):
        with self.assertRaises(ValueError):
            w.register_snapshot("head.json", "demo", False)
        data = self.make_receipt()
        data["transport"] = "api-key"
        (self.root / "head.json").write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "onshape-session"):
            w.register_snapshot("head.json", "demo", True)
        self.make_receipt(url=URL.replace(DID, "e" * 24))
        with self.assertRaisesRegex(ValueError, "selected design"):
            w.register_snapshot("head.json", "demo", True)

    def test_credentials_traversal_and_forbidden_endpoints(self):
        for field in ("api_key", "Authorization", "cookie", "client_secret"):
            with self.assertRaisesRegex(ValueError, "Credential"):
                w.secret_free({"nested": {field: "synthetic-secret"}})
        with self.assertRaises(ValueError):
            w.local_json("../../outside.json")
        for url in (URL.replace("/features", "/featurescript"), URL.replace("partstudios", "featurestudios"),
                    URL + "?api_key=synthetic-secret", URL.replace("cad.onshape.com", "example.com")):
            with self.assertRaises(ValueError):
                w.safe_identity(url)

    def test_prepare_is_local_and_preconditioned(self):
        with patch("socket.socket", side_effect=AssertionError("No network permitted")):
            manifest = w.prepare_native_change("demo", EID, "head.json", FEATURE)
        self.assertFalse(manifest["executed"])
        body = json.loads(Path(manifest["body_path"]).read_text())
        self.assertEqual(body["sourceMicroversion"], MID)
        self.assertTrue(body["rejectMicroversionSkew"])
        self.assertEqual(manifest["body_sha256"], w.catalog.digest(Path(manifest["body_path"]).read_bytes()))

    def test_update_requires_existing_feature_and_encodes_id(self):
        manifest = w.prepare_native_change("demo", EID, "head.json", FEATURE, "update", "test/feature+id")
        self.assertTrue(manifest["requestUrl"].endswith("/featureid/test%2Ffeature%2Bid"))
        with self.assertRaisesRegex(ValueError, "absent"):
            w.prepare_native_change("demo", EID, "head.json", FEATURE, "update", "missing")

    def test_old_or_foreign_heads_and_custom_features_are_rejected(self):
        self.make_receipt(age=1900)
        with self.assertRaisesRegex(ValueError, "30 minutes"):
            w.prepare_native_change("demo", EID, "head.json", FEATURE)
        self.make_receipt()
        with self.assertRaises(ValueError):
            w.prepare_native_change("demo", "e" * 24, "head.json", FEATURE)
        with self.assertRaises(ValueError):
            w.prepare_native_change("demo", EID, "head.json", {**FEATURE, "namespace": "custom"})
        with self.assertRaises(ValueError):
            w.prepare_native_change("demo", EID, "head.json", {**FEATURE, "featureType": "customGeometry"})

    def test_native_serialized_query_strings_remain_allowed(self):
        feature = {**FEATURE, "parameters": [{"parameterId": "entities", "queries": [
            {"queryString": 'query = qSketchRegion(id + "validSketchId", true);', "featureId": "validSketchId"}]}]}
        self.assertFalse(w.prepare_native_change("demo", EID, "head.json", feature)["executed"])

    def test_http_success_does_not_hide_feature_error(self):
        self.make_receipt(status="ERROR")
        result = w.review_native_result("head.json", "demo", EID, MID, ["test/feature+id"])
        self.assertFalse(result["recorded_feature_states_healthy"])
        self.assertFalse(result["live_geometry_verified"])
        self.make_receipt()
        result = w.review_native_result("head.json", "demo", EID, MID, ["test/feature+id"])
        self.assertTrue(result["recorded_feature_states_healthy"])
        self.assertFalse(result["motion_verified"])
        with self.assertRaises(ValueError):
            w.review_native_result("head.json", "demo", EID, "e" * 24, ["test/feature+id"])

    def test_bounded_payload_slices(self):
        data = self.make_receipt(url=URL.replace(f"/w/{WID}/", f"/m/{MID}/"), name="large.json")
        data["response"]["items"] = [{"data": "x" * 1000} for _ in range(60)]
        (self.root / "large.json").write_text(json.dumps(data))
        w.register_snapshot("large.json", "demo", True)
        result = w.read_snapshot("large.json")
        self.assertTrue(result["value_omitted"])
        result = w.read_snapshot("large.json", "/items", 1, 3)
        self.assertEqual(len(result["value"]), 3)
        self.assertEqual(result["next_offset"], 4)

    def test_refresh_queue_excludes_other_designs(self):
        with closing(w.catalog.connect(w.DB_PATH)) as db, db:
            db.execute("INSERT INTO refresh_state VALUES (?,1,'test',NULL,NULL)", (DID,))
            db.execute("INSERT INTO refresh_state VALUES (?,1,'test',NULL,NULL)", ("e" * 24,))
        self.assertEqual([v["document_id"] for v in w.design_context("demo")["refresh_queue"]], [DID])

    def test_calculation_uses_units_and_no_eval(self):
        value = w.mechanism_calculation("roller_tip_speed", {"diameter_mm": 100, "rpm": 60})
        self.assertAlmostEqual(value["result"]["tip_speed_m_per_s"], 0.3141592653589793)
        value = w.mechanism_calculation("shaft_stack", {"thicknesses_mm": [10, 15, 2], "available_length_mm": 30})
        self.assertEqual(value["result"]["remaining_length_mm"], 3)
        for parameters in ({"diameter_mm": "eval(1)", "rpm": 1}, {"diameter_mm": float("nan"), "rpm": 1}):
            with self.assertRaises(ValueError):
                w.mechanism_calculation("roller_tip_speed", parameters)


if __name__ == "__main__":
    unittest.main(verbosity=2)
