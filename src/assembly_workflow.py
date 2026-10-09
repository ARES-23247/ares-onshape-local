"""Prepare native mates and review source-bound saved assembly states/poses."""
import math
import re
from urllib.parse import quote, urlsplit

import local_workflow as w
import native_operations as journal

ASSEMBLY_TYPES = {"mate": "BTMMate", "mateGroup": "BTMMateGroup",
                  "mateConnector": "BTMMateConnector", "mateRelation": "BTMMateRelation"}


def feature_receipt(source, design, element_id, expected_microversion="", fresh=False):
    path, raw, data, ident = w.receipt(source, design, element_id, fresh)
    route = re.fullmatch(r"/api/(v[0-9]+/)?(partstudios|assemblies)/d/[0-9a-f]{24}/([wmv])/[0-9a-f]{24}/e/[0-9a-f]{24}/features",
                         urlsplit(ident["url"]).path)
    r = data["response"]
    if not route or not isinstance(r, dict) or not isinstance(r.get("features"), list):
        raise ValueError("A native Part Studio or Assembly feature-list receipt is required")
    if r.get("isComplete") is not True or r.get("microversionSkew"):
        raise ValueError("A complete unskewed native feature list is required")
    if ident["configuration"] != "__unspecified__" or any(
            k not in {"rollbackBarIndex"} or v != "-1" for k, v in ident["request"]["query"]):
        raise ValueError("A full unfiltered default feature list is required")
    if not w.catalog.ID.fullmatch(r.get("sourceMicroversion", "")):
        raise ValueError("Feature-list microversion is missing")
    if expected_microversion and r["sourceMicroversion"] != expected_microversion:
        raise ValueError("Readback microversion differs from the expected post-change result")
    if len({f.get("featureId") for f in r["features"]}) != len(r["features"]):
        raise ValueError("Feature-list identities are duplicated")
    return path, raw, data, ident, route.group(2)


def feature_state(response, fid):
    states = response.get("featureStates", {})
    state = states.get(fid, {}) if isinstance(states, dict) else {}
    if isinstance(state, dict) and isinstance(state.get("message"), dict):
        state = state["message"]
    return state.get("featureStatus", "UNKNOWN") if isinstance(state, dict) else "UNKNOWN"


def review_features(source, design, element_id, expected_microversion, expected_feature_ids,
                    expected_suppressed_feature_ids=None):
    if not w.catalog.ID.fullmatch(expected_microversion) or not expected_feature_ids:
        raise ValueError("Provide the post-change microversion and feature IDs to verify")
    path, raw, data, ident, kind = feature_receipt(source, design, element_id, expected_microversion)
    suppressed = set(expected_suppressed_feature_ids or [])
    if not suppressed.issubset(expected_feature_ids) or len(set(expected_feature_ids)) != len(expected_feature_ids):
        raise ValueError("Expected suppression must name distinct features in the review scope")
    r = data["response"]
    features = {f.get("featureId"): f for f in r["features"]}
    checks = []
    for fid in expected_feature_ids:
        actual = features.get(fid, {})
        inactive = actual.get("suppressed", False)
        status = feature_state(r, fid)
        checks.append({"feature_id": fid, "present": fid in features, "feature_status": status,
                       "suppressed": inactive, "expected_suppressed": fid in suppressed,
                       "expectation_met": fid in features and (
                           inactive is True if fid in suppressed else inactive is False and status == "OK")})
    return {"source": path.relative_to(w.WORKSPACE).as_posix(), "file_sha256": w.catalog.digest(raw),
            "identity": ident, "element_kind": kind, "checks": checks,
            "recorded_feature_states_healthy": all(c["expectation_met"] for c in checks),
            "active_features_healthy": all(c["expectation_met"] for c in checks if not c["expected_suppressed"]),
            "deliberately_suppressed_features": sorted(suppressed),
            "live_geometry_verified": False, "motion_verified": False, "physical_validation": False,
            "scope": "Saved active feature states and explicitly expected recovery suppression; no live geometry/motion proof"}


def parameters(feature):
    values = feature.get("parameters")
    if not isinstance(values, list) or any(not isinstance(p, dict) or not p.get("parameterId") for p in values):
        raise ValueError("Native parameters need distinct parameterId values")
    mapping = {p["parameterId"]: p for p in values}
    if len(mapping) != len(values):
        raise ValueError("Native parameter identities are duplicated")
    return mapping


def prepare_assembly_change(design, element_id, head_receipt, feature, template_feature_id,
                            operation="create", feature_id="", api_version="v17"):
    path, raw, data, ident, kind = feature_receipt(head_receipt, design, element_id, fresh=True)
    if kind != "assemblies" or ident["context_type"] != "w":
        raise ValueError("Use a fresh owning Assembly workspace head")
    if operation not in ("create", "update") or not re.fullmatch(r"v[0-9]+", api_version):
        raise ValueError("Choose create/update and the current Explorer API version")
    w.secret_free(feature)
    feature_type = feature.get("featureType")
    prefix = ASSEMBLY_TYPES.get(feature_type)
    if (not prefix or not re.fullmatch(prefix + r"-[0-9]+", feature.get("btType", ""))
            or feature.get("namespace") or feature.get("imports")):
        raise ValueError("Use a supported serialized standard native Assembly feature")
    if not feature.get("name") or len(w.catalog.canonical(feature)) > 2 * 1024 * 1024:
        raise ValueError("Use a named bounded native feature")
    if re.search(r"PLACEHOLDER|YOUR_[A-Z_]+|SKETCH_FEATURE_ID", w.catalog.canonical(feature)):
        raise ValueError("Resolve all template placeholders")
    r = data["response"]
    templates = [f for f in r["features"] if f.get("featureId") == template_feature_id]
    if (len(templates) != 1 or feature_state(r, template_feature_id) != "OK"
            or templates[0].get("suppressed") or templates[0].get("featureType") != feature_type
            or templates[0].get("btType") != feature["btType"]):
        raise ValueError("Choose a healthy native template of the same feature type from this head")
    original, submitted = parameters(templates[0]), parameters(feature)
    if set(original) != set(submitted) or any(original[k].get("btType") != submitted[k].get("btType") for k in original):
        raise ValueError("Preserve the complete native template parameter schema; minimal mate definitions are unsafe")
    for key in ("mateType", "relationType"):
        if key in original and original[key].get("value") != submitted[key].get("value"):
            raise ValueError("Template must use the same native mate/relation variant")
    if operation == "update":
        if not feature_id or not any(f.get("featureId") == feature_id for f in r["features"]):
            raise ValueError("Update requires an existing feature ID")
        if feature.get("featureId") not in (None, feature_id):
            raise ValueError("Body and update feature identities differ")
        feature = dict(feature, featureId=feature_id)
    elif feature_id or feature.get("featureId"):
        raise ValueError("Create must let Onshape assign the native feature ID")
    body = {"feature": feature, "sourceMicroversion": r["sourceMicroversion"], "rejectMicroversionSkew": True}
    for key in ("serializationVersion", "libraryVersion"):
        if key in r:
            body[key] = r[key]
    native = w.design_record(design)["onshape"]
    target = f'https://cad.onshape.com/api/{api_version}/assemblies/d/{native["document_id"]}/w/{native["workspace_id"]}/e/{element_id}/features'
    if operation == "update":
        target += "/featureid/" + quote(feature_id, safe="")
    return journal.prepare(design, ident, r, path, raw, body, target, operation, feature_id)


def definition(source, design, element_id, expected_microversion):
    path, raw, data, ident = w.receipt(source, design, element_id)
    if not re.fullmatch(r"/api/(v[0-9]+/)?assemblies/d/[0-9a-f]{24}/[wmv]/[0-9a-f]{24}/e/[0-9a-f]{24}", urlsplit(ident["url"]).path):
        raise ValueError("Use an Assembly definition receipt, not a feature list")
    if ident["units"] != "m":
        raise ValueError("Assembly matrices use metres; record units=m")
    root = data["response"].get("rootAssembly", {})
    if (root.get("documentMicroversion") != expected_microversion
            or not w.catalog.ID.fullmatch(expected_microversion)
            or not isinstance(root.get("instances"), list) or not isinstance(root.get("occurrences"), list)):
        raise ValueError("Assembly definition is incomplete or at a different microversion")
    evidence = {"source": path.relative_to(w.WORKSPACE).as_posix(), "sha256": w.catalog.digest(raw),
                "identity": ident, "microversion": expected_microversion}
    return root, evidence


def matrix(value):
    if (not isinstance(value, list) or len(value) != 16
            or any(isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) for n in value)):
        raise ValueError("Expected a finite 16-value row-major transform; translations in metres")
    if any(abs(value[12 + i] - v) > 1e-10 for i, v in enumerate((0, 0, 0, 1))):
        raise ValueError("Expected a homogeneous rigid transform")
    for i in range(3):
        for j in range(3):
            dot = sum(value[i * 4 + k] * value[j * 4 + k] for k in range(3))
            if abs(dot - (1 if i == j else 0)) > 1e-7:
                raise ValueError("Rotation matrix must be orthonormal")
    det = (value[0] * (value[5] * value[10] - value[6] * value[9])
           - value[1] * (value[4] * value[10] - value[6] * value[8])
           + value[2] * (value[4] * value[9] - value[5] * value[8]))
    if abs(det - 1) > 1e-7:
        raise ValueError("Expected a proper rotation")
    return value


def pose_checks(root, expected_poses, tolerance):
    if (isinstance(tolerance, bool) or not isinstance(tolerance, (int, float))
            or not math.isfinite(tolerance) or not 0 < tolerance <= 1e-3):
        raise ValueError("Matrix tolerance must be positive and at most 0.001")
    if not isinstance(expected_poses, list) or not 1 <= len(expected_poses) <= 5000:
        raise ValueError("Name 1-5000 expected occurrence transforms")
    actual = {}
    for occurrence in root["occurrences"]:
        path = tuple(occurrence.get("path", []))
        if path in actual:
            raise ValueError("Assembly occurrence paths are duplicated")
        actual[path] = occurrence
    checks, seen = [], set()
    for expected in expected_poses:
        path = expected.get("path")
        if not isinstance(path, list) or not path or any(not isinstance(p, str) or not p for p in path):
            raise ValueError("Expected occurrence path is invalid")
        key = tuple(path)
        if key in seen:
            raise ValueError("Expected pose paths must be distinct")
        seen.add(key)
        want = matrix(expected.get("transform"))
        occurrence = actual.get(key)
        error = max(abs(a - b) for a, b in zip(matrix(occurrence.get("transform")), want)) if occurrence else None
        checks.append({"path": path, "present": occurrence is not None, "maximum_matrix_error": error,
                       "passed": error is not None and error <= tolerance})
    return checks


def review_assembly_result(features_source, assembly_source, design, element_id, expected_microversion,
                           expected_feature_ids, expected_part_references=None, expected_poses=None,
                           expected_suppressed_feature_ids=None, matrix_tolerance=1e-8):
    result = review_features(features_source, design, element_id, expected_microversion,
                             expected_feature_ids, expected_suppressed_feature_ids)
    if result["element_kind"] != "assemblies":
        raise ValueError("Assembly review requires Assembly features")
    root, evidence = definition(assembly_source, design, element_id, expected_microversion)
    if evidence["identity"]["configuration"] != result["identity"]["configuration"]:
        raise ValueError("Assembly and features must use the same configuration")
    references = expected_part_references or []
    if not isinstance(references, list) or len(references) > 5000:
        raise ValueError("Bounded root-instance reference expectations are required")
    instances = {i["id"]: i for i in root["instances"]}
    if len(instances) != len(root["instances"]):
        raise ValueError("Root instance identities are duplicated")
    checks, seen = [], set()
    for expected in references:
        instance_id = expected.get("instance_id")
        wanted = expected.get("reference", {})
        required = {"documentId", "elementId", "partId", "configuration"}
        permitted = required | {"documentVersion", "documentMicroversion", "fullConfiguration"}
        if (not instance_id or instance_id in seen or not isinstance(wanted, dict)
                or not required.issubset(wanted) or not set(wanted).issubset(permitted)
                or not any(wanted.get(k) for k in ("documentVersion", "documentMicroversion"))
                or any(not isinstance(v, str) or not v for v in wanted.values())):
            raise ValueError("Expected part reference needs a distinct root instance, exact source/part/configuration and version or microversion")
        for key in ("documentId", "elementId", "documentVersion", "documentMicroversion"):
            if key in wanted and not w.catalog.ID.fullmatch(wanted[key]):
                raise ValueError("Part source identities must be valid Onshape IDs")
        seen.add(instance_id)
        actual = instances.get(instance_id, {})
        checks.append({"instance_id": instance_id, "present": bool(actual), "expected": wanted,
                       "passed": actual.get("type") == "Part" and not actual.get("suppressed", False)
                       and all(actual.get(k) == v for k, v in wanted.items())})
    poses = pose_checks(root, expected_poses, matrix_tolerance) if expected_poses else []
    return {**result, "assembly_evidence": evidence, "part_reference_checks": checks, "pose_checks": poses,
            "recorded_assembly_expectations_met": result["recorded_feature_states_healthy"]
            and all(c["passed"] for c in checks + poses),
            "scope": "Saved feature states, requested root-part references and occurrence matrices only; no continuous clearance or physical proof"}


def review_assembly_motion(design, element_id, baseline_source, baseline_microversion, observations,
                           restored_source, restored_microversion, matrix_tolerance=1e-8):
    before, baseline = definition(baseline_source, design, element_id, baseline_microversion)
    if not isinstance(observations, list) or not 1 <= len(observations) <= 100:
        raise ValueError("Provide 1-100 saved commanded observations")
    samples = []
    for observation in observations:
        command = observation.get("command")
        if (not isinstance(command, dict) or not command.get("feature_id")
                or command.get("units") not in ("deg", "rad", "mm", "m")
                or isinstance(command.get("value"), bool) or not isinstance(command.get("value"), (int, float))
                or not math.isfinite(command["value"])):
            raise ValueError("Record the commanded native feature, finite value and units")
        root, evidence = definition(observation["source"], design, element_id, observation["microversion"])
        if evidence["identity"]["request"] != baseline["identity"]["request"]:
            raise ValueError("Motion observations must use the same target/configuration/filters")
        checks = pose_checks(root, observation["expected_poses"], matrix_tolerance)
        samples.append({"command": command, "command_evidence": "operator-recorded; not independently executed by MCP",
                        "evidence": evidence, "checks": checks, "passed": all(c["passed"] for c in checks)})
    restored, final = definition(restored_source, design, element_id, restored_microversion)
    if final["identity"]["request"] != baseline["identity"]["request"]:
        raise ValueError("Restoration must use the same target/configuration/filters")
    expected = [{"path": o["path"], "transform": o["transform"]} for o in before["occurrences"]]
    restoration = pose_checks(restored, expected, matrix_tolerance)
    same_inventory = {tuple(o["path"]) for o in restored["occurrences"]} == {tuple(o["path"]) for o in before["occurrences"]}
    neutral = same_inventory and all(c["passed"] for c in restoration)
    return {"baseline": baseline, "samples": samples, "restored": final, "restoration_checks": restoration,
            "neutral_pose_restored": neutral, "recorded_sampled_motion_matches": neutral and all(s["passed"] for s in samples),
            "live_geometry_verified": False, "motion_verified": False, "physical_validation": False,
            "scope": "Scoped saved pose expectations and full baseline occurrence restoration; no continuous motion/interference or physical proof"}
