"""Saved assembly checks must detect wrong references, incomplete mates and failed restoration."""
import copy
from datetime import datetime, timezone
import json
import unittest

import assembly_workflow as a
import native_operations as journal
import test_local_workflow as fixture
from test_local_workflow import DID, WID, EID, MID, URL

ASSEMBLY_URL = URL.replace("partstudios", "assemblies")
DEFINITION_URL = ASSEMBLY_URL.rsplit("/", 1)[0]
IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
MATE = {"btType": "BTMMate-64", "featureType": "mate", "name": "Complete native revolute",
        "parameters": [{"parameterId": "mateType", "btType": "BTMParameterEnum-145", "value": "REVOLUTE"},
                       {"parameterId": "mateConnectorsQuery", "btType": "BTMParameterQueryWithOccurrenceList-67", "queries": []},
                       {"parameterId": "limitAxialZ", "btType": "BTMParameterBoolean-144", "value": False}]}
REFERENCE = {"documentId": "f" * 24, "elementId": "e" * 24, "partId": "part",
             "configuration": "Exact variant", "documentMicroversion": "1" * 24}


class AssemblyTests(unittest.TestCase):
    setUp, tearDown, make_receipt = fixture.LocalTests.setUp, fixture.LocalTests.tearDown, fixture.LocalTests.make_receipt

    def features(self, suppressed=False):
        data = self.make_receipt(url=ASSEMBLY_URL, name="assembly-features.json")
        data["response"]["features"] = [{**copy.deepcopy(MATE), "featureId": "mate", "suppressed": suppressed}]
        data["response"]["featureStates"] = {"mate": {"featureStatus": "OK"}}
        (self.root / "assembly-features.json").write_text(json.dumps(data))
        return data

    def definition(self, name="assembly.json", transform=None, mid=MID, reference=None):
        data = {"method": "GET", "requestUrl": DEFINITION_URL, "httpStatus": 200, "transport": "onshape-session",
                "observedAt": datetime.now(timezone.utc).isoformat(), "units": "m",
                "response": {"rootAssembly": {"documentId": DID, "elementId": EID, "documentMicroversion": mid,
                    "instances": [{"id": "root", "type": "Part", **(reference or REFERENCE)}],
                    "occurrences": [{"path": ["root"], "transform": transform or IDENTITY}]}}}
        (self.root / name).write_text(json.dumps(data))
        return data

    def test_full_template_preparation_and_minimal_mate_rejected(self):
        self.features()
        feature = {**copy.deepcopy(MATE), "name": "New mate"}
        manifest = a.prepare_assembly_change("demo", EID, "assembly-features.json", feature, "mate")
        self.assertIn("/assemblies/", manifest["requestUrl"])
        journal.record_native_submission(manifest["manifest"], "cancel_unsubmitted")
        feature["parameters"] = feature["parameters"][:2]
        with self.assertRaisesRegex(ValueError, "complete native"):
            a.prepare_assembly_change("demo", EID, "assembly-features.json", feature, "mate")
        feature = copy.deepcopy(MATE)
        feature["parameters"][0]["value"] = "FASTENED"
        with self.assertRaisesRegex(ValueError, "same native"):
            a.prepare_assembly_change("demo", EID, "assembly-features.json", feature, "mate")

    def test_missing_states_are_unknown_and_deliberate_suppression_is_explicit(self):
        d = self.features()
        d["response"]["featureStates"] = {}
        (self.root / "assembly-features.json").write_text(json.dumps(d))
        result = a.review_features("assembly-features.json", "demo", EID, MID, ["mate"])
        self.assertFalse(result["recorded_feature_states_healthy"])
        self.assertEqual(result["checks"][0]["feature_status"], "UNKNOWN")
        self.features(True)
        self.assertFalse(a.review_features("assembly-features.json", "demo", EID, MID, ["mate"])["recorded_feature_states_healthy"])
        result = a.review_features("assembly-features.json", "demo", EID, MID, ["mate"], ["mate"])
        self.assertTrue(result["recorded_feature_states_healthy"])
        self.assertEqual(result["deliberately_suppressed_features"], ["mate"])

    def test_source_reference_and_pose_checks_detect_no_op_replacement(self):
        self.features()
        self.definition()
        expected = [{"instance_id": "root", "reference": REFERENCE}]
        args = ("assembly-features.json", "assembly.json", "demo", EID, MID, ["mate"])
        result = a.review_assembly_result(*args, expected, [{"path": ["root"], "transform": IDENTITY}])
        self.assertTrue(result["recorded_assembly_expectations_met"])
        changed = copy.deepcopy(expected)
        changed[0]["reference"]["partId"] = "replacement"
        self.assertFalse(a.review_assembly_result(*args, changed)["recorded_assembly_expectations_met"])
        wrong = IDENTITY.copy()
        wrong[3] = 0.01
        self.assertFalse(a.review_assembly_result(*args, expected, [{"path": ["root"], "transform": wrong}])["recorded_assembly_expectations_met"])

    def test_pose_samples_and_full_neutral_restoration(self):
        self.definition("baseline.json")
        moved = IDENTITY.copy()
        moved[3] = 0.002
        self.definition("moved.json", moved, "e" * 24)
        self.definition("restored.json", mid="f" * 24)
        observation = {"source": "moved.json", "microversion": "e" * 24,
                       "command": {"feature_id": "slider", "value": 2, "units": "mm"},
                       "expected_poses": [{"path": ["root"], "transform": moved}]}
        args = ("demo", EID, "baseline.json", MID, [observation], "restored.json", "f" * 24)
        result = a.review_assembly_motion(*args)
        self.assertTrue(result["neutral_pose_restored"])
        self.assertTrue(result["recorded_sampled_motion_matches"])
        self.assertFalse(result["motion_verified"])
        self.definition("restored.json", moved, "f" * 24)
        self.assertFalse(a.review_assembly_motion(*args)["recorded_sampled_motion_matches"])
        d = self.definition("restored.json", mid="f" * 24)
        d["response"]["rootAssembly"]["occurrences"].append({"path": ["extra"], "transform": IDENTITY})
        (self.root / "restored.json").write_text(json.dumps(d))
        self.assertFalse(a.review_assembly_motion(*args)["neutral_pose_restored"])

    def test_mismatched_heads_units_and_nonrigid_matrices_are_rejected(self):
        self.features()
        self.definition(mid="e" * 24)
        with self.assertRaisesRegex(ValueError, "different microversion"):
            a.review_assembly_result("assembly-features.json", "assembly.json", "demo", EID, MID, ["mate"])
        d = self.definition()
        d["units"] = "mm"
        (self.root / "assembly.json").write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError, "metres"):
            a.definition("assembly.json", "demo", EID, MID)
        bad = IDENTITY.copy()
        bad[0] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            a.matrix(bad)
        bad[0] = 2
        with self.assertRaisesRegex(ValueError, "orthonormal"):
            a.matrix(bad)


if __name__ == "__main__":
    unittest.main()
