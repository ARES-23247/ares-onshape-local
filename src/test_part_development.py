"""Definition integrity, resumable native intent and geometry/parameter evidence checks."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

import native_recipe_bridge as bridge
import native_recipe_geometry as geometry
import part_development as parts
import part_recipes as recipes
import part_spec
import test_native_recipe_bridge as helpers


class PartDevelopmentTests(unittest.TestCase):
    def setUp(self):
        self.case = helpers.NativeBridgeTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def definition(self, recipe="spacer", supplied=None):
        # Preserve definition files within the test folder instead of polluting the real workspace.
        definition = part_spec.make(recipe, supplied or {})
        path = self.case.root / (part_spec.digest(definition)+".json")
        path.write_text(json.dumps(definition))
        return str(path)

    def finish(self, recipe="spacer"):
        definition = self.definition(recipe)
        prepared = parts.prepare_part_definition(definition, self.case.head())
        self.case.manifest = prepared["manifest"]
        count = prepared["operations"]
        for i in range(count):
            bridge.prepare_recipe_step(self.case.manifest, self.case.head())
            self.case.simulate_execution()
            bridge.bind_recipe_step(self.case.manifest, self.case.head())
        return definition

    def actual_spacer_verification(self, changed=False):
        # Historical BRep, synthetic target/time identities and analytically updated test volume.
        fixture_root = Path(__file__).resolve().parents[1]/"tests/fixtures"
        sources = {}
        for kind, route in (("body", "bodydetails"), ("mass", "massproperties")):
            case = "changed" if changed and kind == "body" else "default"
            data = json.loads((fixture_root/f"spacer-{case}-{kind}.json").read_text())
            micro = self.case.response["sourceMicroversion"]
            data["requestUrl"] = self.case.url.replace("/w/"+"b"*24, "/m/"+micro).replace("/features", "/"+route)
            if kind == "body":
                data["response"]["microversionId"]["theId"] = micro
            else:
                data["response"]["microversionId"] = micro
                if changed:
                    for body in data["response"]["bodies"].values():
                        body["volume"][0] *= 1.5
            path = self.case.root/(kind+".json")
            path.write_text(json.dumps(data))
            sources[kind] = str(path)
        return bridge.verify_native_recipe(self.case.manifest, self.case.head(), sources["body"], sources["mass"])

    def test_definition_schema_rejects_units_code_and_unknown_fields(self):
        base = part_spec.make("spacer", {})
        for alteration in ({"units": "in"}, {"python": "arbitrary program"}, {"datum": "another axis"},
                           {"parameters_mm": {"length": 12}}):
            with self.subTest(alteration=alteration), self.assertRaises(ValueError):
                part_spec.validate({**base, **alteration})
        self.assertEqual(part_spec.digest(base), part_spec.digest(copy.deepcopy(base)))

    def test_cli_saves_reusable_definition_in_selected_workspace(self):
        source = self.case.root/"arguments.json"
        source.write_text(json.dumps({"recipe": "flanged_hub", "parameters_mm": {"length": 30}}))
        environment = {**os.environ, "ARES_ONSHAPE_WORKSPACE": str(self.case.root)}
        environment.pop("ARES_ONSHAPE_PROJECT", None)
        script = Path(__file__).with_name("part_development_cli.py")
        command = [sys.executable, str(script), "save_part_definition", "--input", str(source)]
        first = subprocess.run(command, cwd=self.case.root, env=environment, capture_output=True, text=True, timeout=15)
        self.assertEqual(first.returncode, 0, first.stderr+first.stdout)
        saved = json.loads(first.stdout)
        self.assertTrue(Path(saved["definition"]).is_relative_to(self.case.root))
        self.assertFalse(saved["native_cad_file"])
        second = subprocess.run(command, cwd=self.case.root, env=environment, capture_output=True, text=True, timeout=15)
        self.assertEqual(second.returncode, 0, second.stderr+second.stdout)
        self.assertEqual(json.loads(second.stdout)["definition"], saved["definition"])

    def test_all_new_native_families_resume_and_bind(self):
        for recipe in ("flanged_hub", "radial_hole_plate", "lofted_guide"):
            self.case.response["features"] = []
            self.case.response["featureStates"] = {}
            self.case.response["sourceMicroversion"] = "1"*24
            definition = self.finish(recipe)
            status = parts.part_development_status(definition, self.case.manifest)
            self.assertEqual(status["native"]["next_index"], status["native"]["operation_count"])
            self.assertFalse(status["native_geometry_verified"])
            types = {f["featureType"] for f in self.case.response["features"]}
            self.assertIn({"flanged_hub": "revolve", "radial_hole_plate": "circularPattern", "lofted_guide": "loft"}[recipe], types)

    def test_altered_definition_stops_request_preparation(self):
        source = self.definition()
        prepared = parts.prepare_part_definition(source, self.case.head())
        data = json.loads(Path(source).read_text())
        data["parameters_mm"]["length"] = 18
        Path(source).write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "definition was changed"):
            bridge.prepare_recipe_step(prepared["manifest"], self.case.head())

    def test_swapped_or_foreign_loft_profiles_cannot_be_bound(self):
        source = self.definition("lofted_guide")
        prepared = parts.prepare_part_definition(source, self.case.head())
        self.case.manifest = prepared["manifest"]
        while True:
            bridge.prepare_recipe_step(self.case.manifest, self.case.head())
            feature = self.case.simulate_execution()
            if feature["featureType"] == "loft":
                profiles = next(p for p in feature["parameters"] if p["parameterId"] == "sheetProfilesArray")
                original = copy.deepcopy(profiles["items"])
                profiles["items"].reverse()
                with self.assertRaisesRegex(ValueError, "ordered profile array"):
                    bridge.bind_recipe_step(self.case.manifest, self.case.head())
                profiles["items"] = original
                profiles["items"][0]["parameters"][0]["queries"][0]["featureId"] = "FOREIGN"
                with self.assertRaisesRegex(ValueError, "ordered profile array"):
                    bridge.bind_recipe_step(self.case.manifest, self.case.head())
                break
            bridge.bind_recipe_step(self.case.manifest, self.case.head())

    def test_revision_requires_new_definition_and_preserves_native_ids(self):
        source = self.finish()
        baseline = self.actual_spacer_verification()
        changed = self.definition(supplied={"length": 18})
        before_ids = bridge.native_recipe_status(self.case.manifest)["feature_ids"]
        with self.assertRaisesRegex(ValueError, "prepare_part_definition"):
            bridge.prepare_recipe_update(self.case.manifest, {"length": 18}, self.case.head())
        prepared = parts.prepare_part_definition(changed, self.case.head(), self.case.manifest)
        self.assertFalse(parts.part_development_status(changed, self.case.manifest)["native_geometry_verified"])
        body = json.loads(Path(prepared["body_path"]).read_text())
        features = {f["featureId"]: f for f in self.case.response["features"]}
        for updated in body["features"]:
            features[updated["featureId"]].update(updated)
        self.case.response["sourceMicroversion"] = "e"*24
        bridge.bind_recipe_step(self.case.manifest, self.case.head())
        self.actual_spacer_verification(changed=True)
        result = parts.verify_part_parameter_change(self.case.manifest, baseline["report"])
        self.assertTrue(result["passed"])
        self.assertTrue(result["feature_ids_preserved"])
        self.assertEqual(bridge.native_recipe_status(self.case.manifest)["feature_ids"], before_ids)
        self.assertTrue(parts.part_development_status(changed, self.case.manifest)["native_geometry_verified"])
        with self.assertRaisesRegex(ValueError, "not the journal"):
            parts.part_development_status(source, self.case.manifest)
        Path(baseline["report"]).write_text("{}")
        with self.assertRaisesRegex(ValueError, "unchanged verification"):
            parts.verify_part_parameter_change(self.case.manifest, baseline["report"])

    def test_unchanged_dimensions_keep_current_definition_binding(self):
        source = self.finish()
        renamed = part_spec.make("spacer", {}, "Another label")
        path = self.case.root/"renamed.json"
        path.write_text(json.dumps(renamed))
        result = parts.prepare_part_definition(str(path), self.case.head(), self.case.manifest)
        self.assertFalse(result["changed"])
        self.assertFalse(result["definition_bound"])
        self.assertEqual(parts.part_development_status(source, self.case.manifest)["recipe"], "spacer")
        with self.assertRaisesRegex(ValueError, "not the journal"):
            parts.part_development_status(str(path), self.case.manifest)

    def test_status_rejects_altered_native_verification(self):
        source = self.finish()
        verified = self.actual_spacer_verification()
        self.assertTrue(parts.part_development_status(source, self.case.manifest)["native_geometry_verified"])
        Path(verified["report"]).write_text("{}")
        with self.assertRaisesRegex(ValueError, "verification is altered"):
            parts.part_development_status(source, self.case.manifest)

    def test_new_family_geometric_guards(self):
        for recipe, supplied in (("flanged_hub", {"hub_diameter": 39}),
                                  ("flanged_hub", {"flange_thickness": 20}),
                                  ("radial_hole_plate", {"bolt_circle_diameter": 78}),
                                  ("radial_hole_plate", {"bolt_circle_diameter": 10}),
                                  ("lofted_guide", {"wall": 10})):
            with self.subTest(recipe=recipe), self.assertRaises(ValueError):
                recipes.normalize(recipe, supplied)

    def test_sloped_guide_plane_equation_detects_reversed_taper(self):
        # Synthetic analytic BRep; does not establish live Onshape surface serialization.
        p = recipes.normalize("lofted_guide", {})
        faces = []
        for i, wanted in enumerate(geometry.expected_faces("lofted_guide", p)):
            normal = wanted.get("normal", [0, 0, 1])
            faces.append({"id": str(i), "area": wanted["area"], "box": {
                "minCorner": dict(zip("xyz", wanted["min"])), "maxCorner": dict(zip("xyz", wanted["max"]))},
                "surface": {"type": "PLANE", "normal": dict(zip("xyz", normal)),
                            "origin": dict(zip("xyz", wanted.get("origin", wanted["min"])))} })
        body = {"errorEnum": "NO_ERROR", "bodies": [{"type": "SOLID", "id": "S", "faces": faces}]}
        self.assertTrue(geometry.check_brep("lofted_guide", p, body)["passed"])
        faces[2]["surface"]["origin"]["z"] += .01
        with self.assertRaises(ValueError):
            geometry.check_brep("lofted_guide", p, body)

    def test_changed_preview_artifact_and_path_escape_are_rejected(self):
        definition = part_spec.make("spacer", {})
        folder = self.case.root/"bundle"
        folder.mkdir()
        artifacts = {}
        for name in ("part-definition.json", "native-plan.json", "mesh.json", "FEASIBILITY-spacer.step"):
            path = folder/name
            path.write_text(json.dumps(definition) if name == "part-definition.json" else "synthetic artifact")
            artifacts[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        record = {"part_definition_sha256": part_spec.digest(definition), "recipe": "spacer",
                  "parameters_mm": definition["parameters_mm"], "design": "shared", "units": "mm",
                  "local_geometry": {"passed": True}, "step_roundtrip": {"passed": True}, "artifacts": artifacts}
        source = folder/"recipe.json"
        source.write_text(json.dumps(record))
        self.assertTrue(parts.preview_evidence(str(source), definition)["local_geometry_verified"])
        (folder/"mesh.json").write_text("changed")
        with self.assertRaisesRegex(ValueError, "artifact was changed"):
            parts.preview_evidence(str(source), definition)
        artifacts["../outside"] = {"sha256": "fake"}
        artifacts.pop("mesh.json")
        source.write_text(json.dumps(record))
        with self.assertRaises(ValueError):
            parts.preview_evidence(str(source), definition)


if __name__ == "__main__":
    unittest.main()
