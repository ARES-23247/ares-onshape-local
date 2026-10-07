"""Transaction, targeting and design-intent checks using local simulated receipts."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_recipe_bridge as bridge
import native_recipe_features as compiler
import part_recipes as recipes
import native_recipe_geometry as geometry


class NativeBridgeTests(unittest.TestCase):
    def setUp(self):
        bridge.BASE.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="unit-", dir=bridge.BASE)
        self.root = Path(self.temp.name)
        self.base_patch = patch.object(bridge, "BASE", self.root)
        self.base_patch.start()
        self.addCleanup(self.base_patch.stop)
        self.addCleanup(self.temp.cleanup)
        self.response = {"sourceMicroversion": "1" * 24, "libraryVersion": 3083,
                         "serializationVersion": "1.2.21", "isComplete": True,
                         "features": [], "featureStates": {},
                         "defaultFeatures": [{"name": n, "featureId": n, "featureType": "defaultPlane"}
                                             for n in ("Top", "Front", "Right")]}
        self.url = "https://cad.onshape.com/api/v17/partstudios/d/" + "a" * 24 + "/w/" + "b" * 24 + "/e/" + "c" * 24 + "/features"
        self.receipt = self.root / "head.json"

    def head(self, **overrides):
        data = {"transport": "onshape-session", "method": "GET", "httpStatus": 200,
                "requestUrl": self.url, "observedAt": datetime.now(timezone.utc).isoformat(),
                "response": self.response, **overrides}
        self.receipt.write_text(json.dumps(data), encoding="utf-8")
        return str(self.receipt)

    def prepare(self):
        result = bridge.prepare_native_recipe("spacer", {}, self.head())
        self.manifest = result["manifest"]
        return bridge.prepare_recipe_step(self.manifest, self.head())

    def simulate_execution(self):
        _, m = bridge.load(self.manifest)
        f = copy.deepcopy(m["pending"]["expected_features"][0])
        f["featureId"] = f"F{len(self.response['features'])}"
        for p in f["parameters"]:
            if p["btType"].startswith("BTMParameterQuantity"):
                p["value"] = 999  # Native evaluated/cache values are not design intent.
        self.response["features"].append(f)
        self.response["featureStates"][f["featureId"]] = {"featureStatus": "OK"}
        self.response["sourceMicroversion"] = f"{len(self.response['features']) + 1:024x}"
        return f

    def complete(self):
        self.prepare()
        for index in range(5):
            self.simulate_execution()
            bridge.bind_recipe_step(self.manifest, self.head())
            if index < 4:
                bridge.prepare_recipe_step(self.manifest, self.head())

    def test_pending_request_cannot_be_submitted_twice(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, "pending"):
            bridge.prepare_recipe_step(self.manifest, self.head())
        with self.assertRaisesRegex(ValueError, "did not advance"):
            bridge.bind_recipe_step(self.manifest, self.head())

    def test_recipe_start_preserves_existing_models(self):
        self.response["features"] = [{"featureId": "Existing", "featureType": "extrude", "name": "Existing part"}]
        with self.assertRaisesRegex(ValueError, "empty Part Studio"):
            bridge.prepare_native_recipe("spacer", {}, self.head())

    def test_changed_request_and_duplicate_native_name_are_rejected(self):
        request = self.prepare()
        self.simulate_execution()
        Path(request["body_path"]).write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "modified"):
            bridge.bind_recipe_step(self.manifest, self.head())

    def test_receipt_transport_target_freshness_and_revision(self):
        self.prepare()
        for override in ({"transport": "api-key"}, {"httpStatus": 429},
                         {"observedAt": "2000-01-01T00:00:00+00:00"},
                         {"requestUrl": self.url.replace("c" * 24, "d" * 24)}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                bridge.prepare_recipe_step(self.manifest, self.head(**override))
        self.response["libraryVersion"] = 9999
        with self.assertRaisesRegex(ValueError, "revision"):
            bridge.prepare_native_recipe("spacer", {}, self.head())

    def test_failed_regeneration_is_not_bound(self):
        self.prepare()
        f = self.simulate_execution()
        self.response["featureStates"][f["featureId"]]["featureStatus"] = "ERROR"
        with self.assertRaisesRegex(ValueError, "regeneration failed"):
            bridge.bind_recipe_step(self.manifest, self.head())

    def test_complete_recipe_and_preserved_id_update(self):
        self.complete()
        status = bridge.native_recipe_status(self.manifest)
        ids = status["feature_ids"]
        self.assertEqual(len(ids), 5)
        self.assertFalse(status["native_geometry_verified"])
        update = bridge.prepare_recipe_update(self.manifest, {"length": 18}, self.head())
        body = json.loads(Path(update["body_path"]).read_text())
        self.assertEqual(body["features"][0]["featureId"], ids["var:length"])
        self.response["features"][2]["parameters"][-1]["expression"] = "18 mm"
        self.response["features"][2]["parameters"][-1]["value"] = 0.018
        self.response["features"][3]["entities"][2]["geometry"]["radius"] = .01
        self.response["sourceMicroversion"] = "e" * 24
        bridge.bind_recipe_step(self.manifest, self.head())
        self.assertEqual(bridge.native_recipe_status(self.manifest)["feature_ids"], ids)
        self.assertEqual(bridge.native_recipe_status(self.manifest)["parameters_mm"]["length"], 18)

    def test_unexpected_design_edit_is_detected(self):
        self.complete()
        self.response["features"][3]["constraints"][-1]["parameters"][1]["expression"] = "3 mm"
        with self.assertRaisesRegex(ValueError, "changed outside"):
            bridge.prepare_recipe_update(self.manifest, {"length": 18}, self.head())

    def test_mutation_lock_rejects_parallel_process(self):
        self.prepare()
        lock = Path(self.manifest).with_suffix(".lock")
        lock.write_text("another process", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "another process"):
            bridge.prepare_recipe_step(self.manifest, self.head())
        self.assertTrue(lock.is_file())

    def test_dimensional_constraints_cover_each_recipe(self):
        for name in recipes.RECIPES:
            p = recipes.normalize(name, {})
            variables = {k: "ares_" + k for k in p}
            ids = {op["role"]: "F" + str(i) for i, op in enumerate(compiler.operations(name, p))}
            for op in compiler.operations(name, p):
                f = compiler.compile_step(op, name, p, variables, ids, {"Top": "Top", "Front": "Front"}, "test")
                if f["featureType"] == "newSketch":
                    self.assertGreater(len(f["constraints"]), 4)
                    for e in f["entities"]:
                        if not e["isConstruction"]:
                            point = e.get("centerId", e.get("startPointId"))
                            self.assertTrue(any(c["entityId"] == point + "x" for c in f["constraints"]))
                            self.assertTrue(any(c["entityId"] == point + "y" for c in f["constraints"]))

    def test_native_brep_checks_detect_changed_holes_and_missing_faces(self):
        # Actual Onshape pilot response, kept as a regression fixture. No network access.
        source = Path(__file__).resolve().parents[1] / "tests/fixtures/spacer-changed-body.json"
        original = json.loads(source.read_text(encoding="utf-8"))["response"]
        p = recipes.normalize("spacer", {"length": 18})
        self.assertTrue(geometry.check_brep("spacer", p, original)["passed"])
        for change in ("radius", "position", "missing", "orientation", "area"):
            altered = copy.deepcopy(original)
            face = altered["bodies"][0]["faces"][0]
            if change == "radius":
                face["surface"]["radius"] *= .9
            elif change == "position":
                face["surface"]["origin"]["x"] += .001
            elif change == "missing":
                altered["bodies"][0]["faces"].pop()
            elif change == "orientation":
                face["orientation"] = True
            else:
                face["area"] *= .9
            with self.subTest(change=change), self.assertRaises(ValueError):
                geometry.check_brep("spacer", p, altered)

    def test_all_actual_native_default_and_changed_surfaces(self):
        root = Path(__file__).resolve().parents[1] / "tests/fixtures"
        trials = {"spacer": ("spacer", {"length": 18}),
                  "plate": ("hole_pattern_plate", {"pitch_x": 50, "pitch_y": 25}),
                  "bracket": ("mounting_bracket", {"width": 36, "height": 36, "hole_pitch_x": 24, "wall_hole_z": 24})}
        for label, (recipe, changed) in trials.items():
            for case, dimensions in (("default", {}), ("changed", changed)):
                payload = json.loads((root / f"{label}-{case}-body.json").read_text())["response"]
                with self.subTest(recipe=recipe, case=case):
                    self.assertTrue(geometry.check_brep(recipe, dimensions, payload)["passed"])

    def test_manifest_cannot_inject_variable_expressions_or_operations(self):
        self.prepare()
        path, m = bridge.load(self.manifest)
        m["variable_names"]["length"] = "unexpected expression"
        bridge.save(path, m)
        with self.assertRaisesRegex(ValueError, "definitions were altered"):
            bridge.native_recipe_status(self.manifest)

    def test_verification_requires_matching_immutable_evidence_and_native_volume(self):
        self.complete()
        root = Path(__file__).resolve().parents[1] / "tests/fixtures"
        sources = {}
        for kind, route in (("body", "bodydetails"), ("mass", "massproperties")):
            receipt = json.loads((root / f"spacer-default-{kind}.json").read_text())
            receipt["requestUrl"] = self.url.replace("/w/" + "b" * 24, "/m/" + self.response["sourceMicroversion"]).replace("/features", "/" + route)
            receipt["test_fixture"] = "SIMULATED identities with copied actual native geometry"
            if kind == "body":
                receipt["response"]["microversionId"]["theId"] = self.response["sourceMicroversion"]
            else:
                receipt["response"]["microversionId"] = self.response["sourceMicroversion"]
            path = self.root / (kind + ".json")
            path.write_text(json.dumps(receipt))
            sources[kind] = str(path)
        result = bridge.verify_native_recipe(self.manifest, self.head(), sources["body"], sources["mass"])
        self.assertTrue(result["verified"])
        self.assertTrue(bridge.native_recipe_status(self.manifest)["verification_evidence"])
        altered = json.loads(Path(sources["mass"]).read_text())
        altered["response"]["bodies"]["JHD"]["volume"][0] *= 2
        Path(sources["mass"]).write_text(json.dumps(altered))
        with self.assertRaisesRegex(ValueError, "volume differs"):
            bridge.verify_native_recipe(self.manifest, self.head(), sources["body"], sources["mass"])
        altered["requestUrl"] = altered["requestUrl"].replace("c" * 24, "d" * 24)
        Path(sources["mass"]).write_text(json.dumps(altered))
        with self.assertRaisesRegex(ValueError, "same immutable target"):
            bridge.verify_native_recipe(self.manifest, self.head(), sources["body"], sources["mass"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
