"""Receipt-driven native recipe preparation and feature tracking. No Onshape HTTP client."""
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
import math
from functools import wraps
from pathlib import Path
import re
from urllib.parse import quote, urlsplit, parse_qs
from uuid import uuid4

import local_workflow as workflow
import native_recipe_features as compiler
import part_recipes as recipes
import native_recipe_geometry as geometry

ID = re.compile(r"[0-9a-f]{24}")
BASE = workflow.project.runtime_path("native-recipes")
PROFILE = {"api_version": "v17", "library_version": 3083,
           "feature_types": ["assignVariable", "newSketch", "extrude", "revolve", "cPlane", "circularPattern", "loft"],
           "live_pilot_recipes": ["spacer", "mounting_bracket", "hole_pattern_plate"],
           "local_tested_recipes": ["flanged_hub", "radial_hole_plate", "lofted_guide"],
           "scope": "Original three families have historical live pilot evidence; added families require current native regeneration and parameter-change validation",
           "evidence": "docs/native-recipes.md; anonymized historical geometry fixtures in tests/fixtures"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def save(path, data):
    from native_operations import atomic
    workflow.secret_free(data)
    atomic(path, data)


def session_receipt(source, method="GET", fresh=False):
    path, raw, data = workflow.local_json(source)
    if data.get("transport") != "onshape-session" or data.get("method") != method:
        raise ValueError("Use an actual completed session-authenticated receipt with the required method")
    if not isinstance(data.get("httpStatus"), int) or not 200 <= data["httpStatus"] < 300:
        raise ValueError("Receipt does not represent a completed successful request")
    parsed = urlsplit(data.get("requestUrl", ""))
    if parsed.scheme != "https" or parsed.netloc != "cad.onshape.com":
        raise ValueError("Use a credential-free official cad.onshape.com receipt URL")
    match = re.fullmatch(r"/api/(v[0-9]+)/partstudios/d/([0-9a-f]{24})/([wvm])/([0-9a-f]{24})/e/([0-9a-f]{24})/(features(?:/updates|/featureid/[^/]+)?|massproperties|boundingboxes|bodydetails|translations)", parsed.path)
    if not match:
        raise ValueError("Receipt route is outside the bounded native recipe workflow")
    query = parse_qs(parsed.query)
    if query.get("rollbackBarIndex", ["-1"]) != ["-1"] or any(query.get(k) for k in ("configuration", "elementMicroversionId", "partIds", "linkDocumentId")):
        raise ValueError("Bounded recipes require the unfiltered default configuration at the end of the feature list")
    if fresh:
        try:
            captured = datetime.fromisoformat(data["observedAt"].replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - captured).total_seconds()
        except (KeyError, TypeError, ValueError):
            raise ValueError("Receipt needs a timezone-aware observedAt") from None
        if not 0 <= age <= 1800:
            raise ValueError("Refresh this workspace receipt through the signed-in Explorer; maximum age is 30 minutes")
    api, did, context, context_id, eid, operation = match.groups()
    identity = {"api_version": api, "document_id": did, "context_type": context,
                "context_id": context_id, "element_id": eid, "operation": operation}
    evidence = {"source": path.relative_to(workflow.WORKSPACE).as_posix(),
                "sha256": hashlib.sha256(raw).hexdigest(), "observed_at": data.get("observedAt"),
                "identity": identity, "transport": "onshape-session"}
    return data["response"], identity, evidence


def head(source, design, target=None):
    response, identity, evidence = session_receipt(source, fresh=True)
    if identity["context_type"] != "w" or identity["operation"] != "features":
        raise ValueError("Observe a full workspace feature list for this Part Studio")
    if not isinstance(response, dict) or not response.get("isComplete") or not isinstance(response.get("features"), list):
        raise ValueError("A complete native feature-list response is required")
    if not ID.fullmatch(response.get("sourceMicroversion", "")) or response.get("microversionSkew"):
        raise ValueError("Native head is missing or skewed")
    actual = {"document_id": identity["document_id"], "workspace_id": identity["context_id"], "element_id": identity["element_id"]}
    if target and target != actual:
        raise ValueError("Recipe and receipt target identities differ")
    if design != "shared":
        native = workflow.design_record(design)["onshape"]
        if actual["document_id"] != native["document_id"] or actual["workspace_id"] != native["workspace_id"]:
            raise ValueError("Native recipe target differs from the owning design registry")
        if actual["element_id"] in native.get("recovery_elements", []):
            raise ValueError("Recovery elements are not editable targets")
    elif any(actual["document_id"] == workflow.design_record(d)["onshape"]["document_id"] for d in workflow.DESIGNS):
        raise ValueError("Use the actual owning design for registered documents; shared is for separate sandbox documents")
    if identity["api_version"] != PROFILE["api_version"] or response.get("libraryVersion") != PROFILE["library_version"]:
        raise ValueError("Native library/API revision differs from the tested compiler profile; validate and update the profile first")
    return response, actual, evidence


def load(source):
    path, raw, manifest = workflow.local_json(source)
    if not path.resolve().is_relative_to(BASE.resolve()) or path.name != "recipe-manifest.json":
        raise ValueError("Choose a native recipe manifest created by this MCP")
    if manifest.get("schema_version") != 1 or not re.fullmatch(r"[0-9a-f]{32}", manifest.get("recipe_id", "")):
        raise ValueError("Unsupported native recipe manifest")
    p = recipes.normalize(manifest["recipe"], manifest["parameters_mm"])
    rid = manifest["recipe_id"]
    if path.parent.name != rid or manifest.get("prefix") != "ARES " + rid[:8]:
        raise ValueError("Native recipe manifest identity was altered")
    expected_variables = {k: "ares" + rid[:8] + "_" + k for k in p}
    if manifest.get("variable_names") != expected_variables or manifest.get("operations") != compiler.operations(manifest["recipe"], p):
        raise ValueError("Native recipe manifest operation/variable definitions were altered")
    if not 0 <= manifest.get("next_index", -1) <= len(manifest["operations"]):
        raise ValueError("Native recipe journal index is invalid")
    if manifest.get("part_definition"):
        from part_development import load_definition
        definition, evidence = load_definition(manifest["part_definition"]["source"])
        if (evidence != manifest["part_definition"] or definition["parameters_mm"] != manifest["parameters_mm"]
            or definition["recipe"] != manifest["recipe"] or definition["design"] != manifest["design"]):
            raise ValueError("Shared part definition was changed or differs from journal dimensions")
        pending = manifest.get("pending") or {}
        if pending.get("part_definition"):
            new_definition, new_evidence = load_definition(pending["part_definition"]["source"])
            if (new_evidence != pending["part_definition"] or new_definition["parameters_mm"] != pending["new_parameters_mm"]
                or new_definition["recipe"] != manifest["recipe"] or new_definition["design"] != manifest["design"]):
                raise ValueError("Pending shared part definition was changed")
    return path, manifest


def exclusive_manifest(function):
    """Serialize mutations across MCP processes; atomic replacement protects readers."""
    @wraps(function)
    def locked(manifest_source, *args, **kwargs):
        path, _ = load(manifest_source)
        lock = path.with_suffix(".lock")
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise ValueError("This recipe is being changed by another process. Inspect an abandoned lock before removing it.") from None
        try:
            with os.fdopen(descriptor, "w") as stream:
                stream.write(json.dumps({"pid": os.getpid(), "started_at": datetime.now(timezone.utc).isoformat()}))
            return function(manifest_source, *args, **kwargs)
        finally:
            lock.unlink(missing_ok=True)
    return locked


def feature_state(response, fid):
    state = response.get("featureStates", {}).get(fid, {})
    if isinstance(state.get("message"), dict):
        state = state["message"]
    return state.get("featureStatus", "UNKNOWN")


def fingerprint(feature):
    # Geometry coordinates/value caches change when the native solver regenerates.
    # Keep design-defining parameter expressions, query references and sketch constraints.
    def clean(value):
        if isinstance(value, list):
            return [clean(v) for v in value]
        if isinstance(value, dict):
            omitted = {
                "nodeId", "parameterName", "parameterLibraries", "namespace", "libraryRelationType",
                "internalIds", "subFeatures", "geometry", "startParam", "endParam", "index",
                "deterministicIds", "valueString", "suppressionState", "returnAfterSubfeatures"}
            if value.get("btType", "").startswith("BTMParameterQuantity"):
                omitted |= {"value", "units"}
            return {k: clean(v) for k, v in value.items() if k not in omitted}
        return value
    return digest(clean({k: feature[k] for k in ("featureType", "name", "parameters", "constraints", "entities") if k in feature}))


def tracked_features(manifest, response):
    features = {f["featureId"]: f for f in response["features"]}
    for role, fid in manifest["feature_ids"].items():
        f = features.get(fid)
        if not f or f.get("suppressed") or feature_state(response, fid) != "OK":
            raise ValueError("Tracked native feature is missing, suppressed or failed: " + role)
        if fingerprint(f) != manifest["feature_fingerprints"][role]:
            raise ValueError("Tracked native feature was changed outside this recipe: " + role)
    return features


def prepare_native_recipe(recipe, parameters_mm, head_receipt, label="", design="shared", part_definition=None, local_preview=None):
    p = recipes.normalize(recipe, parameters_mm)
    if not isinstance(label, str) or len(label) > 80 or (label and not re.fullmatch(r"[A-Za-z0-9 _.-]+", label)):
        raise ValueError("Use an ASCII recipe label up to 80 characters")
    response, target, evidence = head(head_receipt, design)
    if part_definition:
        from part_development import load_definition
        definition, definition_evidence = load_definition(part_definition["source"])
        if (definition_evidence != part_definition or definition["parameters_mm"] != p
            or definition["recipe"] != recipe or definition["design"] != design):
            raise ValueError("Shared definition differs from the native recipe")
    if response["features"]:
        raise ValueError("Start each bounded recipe in an empty Part Studio; use prepare_native_change for existing models")
    planes = {f["name"]: f["featureId"] for f in response.get("defaultFeatures", []) if f.get("featureType") == "defaultPlane"}
    if any(name not in planes for name in ("Top", "Front")):
        raise ValueError("Fresh target must expose its native Top and Front default planes")
    rid = uuid4().hex
    folder = BASE / rid
    folder.mkdir(parents=True, exist_ok=False)
    manifest = {"schema_version": 1, "recipe_id": rid, "recipe": recipe, "design": design,
                "label": label or recipe, "prefix": "ARES " + rid[:8], "created_at": datetime.now(timezone.utc).isoformat(),
                "parameters_mm": p, "target": target, "profile": PROFILE, "planes": planes,
                "variable_names": {k: "ares" + rid[:8] + "_" + k for k in p},
                "operations": compiler.operations(recipe, p), "next_index": 0,
                "feature_ids": {}, "feature_fingerprints": {}, "journal": [], "pending": None,
                "head_evidence": evidence, "last_bound_microversion": response["sourceMicroversion"],
                "state": "prepared", "native_geometry_verified": False,
                "executor": "Host agent's signed-in browser/session-authenticated official API Explorer",
                "outbound_Onshape_calls": 0}
    path = folder / "recipe-manifest.json"
    if part_definition:
        manifest["part_definition"] = part_definition
        manifest["local_preview"] = local_preview
    save(path, manifest)
    return {"manifest": str(path), "recipe": recipe, "target": target, "operations": len(manifest["operations"]),
            "variable_names": manifest["variable_names"], "next": "prepare_recipe_step with a fresh head receipt",
            "scope": "Prepared native recipe journal only; no Onshape request executed", "outbound_Onshape_calls": 0}


def request(path, manifest, response, evidence, features, roles, operation, pending_extra=None):
    target = manifest["target"]
    url = f'https://cad.onshape.com/api/{manifest["profile"]["api_version"]}/partstudios/d/{target["document_id"]}/w/{target["workspace_id"]}/e/{target["element_id"]}/features'
    body = {"sourceMicroversion": response["sourceMicroversion"], "rejectMicroversionSkew": True,
            "serializationVersion": response["serializationVersion"], "libraryVersion": response["libraryVersion"]}
    if operation == "create":
        body["feature"] = features[0]
    else:
        url += "/updates"
        body["features"] = features
    index = len(manifest["journal"])
    body_path = path.parent / f"request-{index:03d}.json"
    save(body_path, body)
    manifest["pending"] = {"operation": operation, "roles": roles, "requestUrl": url, "body_path": str(body_path),
                           "body_sha256": hashlib.sha256(body_path.read_bytes()).hexdigest(),
                           "expected_features": features, "expected_head": response["sourceMicroversion"],
                           "source_evidence": evidence}
    manifest["pending"].update(pending_extra or {})
    manifest["native_geometry_verified"] = False
    save(path, manifest)
    return {"manifest": str(path), "method": "POST", "requestUrl": url, "body_path": str(body_path),
            "roles": roles, "expected_head": response["sourceMicroversion"], "executed": False,
            "next": "Submit via session Explorer, save a fresh full feature-list receipt, then bind_recipe_step",
            "scope": "Local request preparation; check the live head before submission", "outbound_Onshape_calls": 0}


@exclusive_manifest
def prepare_recipe_step(manifest_source, head_receipt):
    path, m = load(manifest_source)
    response, target, evidence = head(head_receipt, m["design"], m["target"])
    tracked_features(m, response)
    if m["pending"]:
        raise ValueError("A request is pending; read back and bind/reconcile it before preparing another")
    if m["next_index"] >= len(m["operations"]):
        return {"complete": True, "feature_ids": m["feature_ids"], "next": "Verify immutable native BRep/volume or prepare_recipe_update"}
    op = m["operations"][m["next_index"]]
    native = compiler.compile_step(op, m["recipe"], m["parameters_mm"], m["variable_names"], m["feature_ids"], m["planes"], m["prefix"])
    if any(f.get("name") == native["name"] for f in response["features"]):
        raise ValueError("The next feature already exists; reconcile the pending request rather than duplicating it")
    return request(path, m, response, evidence, [native], [op["role"]], "create")


@exclusive_manifest
def bind_recipe_step(manifest_source, head_receipt):
    path, m = load(manifest_source)
    response, target, evidence = head(head_receipt, m["design"], m["target"])
    pending = m["pending"]
    if not pending:
        raise ValueError("No prepared request to bind")
    body_path = Path(pending["body_path"])
    if not body_path.resolve().is_relative_to(path.parent.resolve()) or hashlib.sha256(body_path.read_bytes()).hexdigest() != pending["body_sha256"]:
        raise ValueError("Prepared body was modified; do not bind it as the executed request")
    if response["sourceMicroversion"] == pending["expected_head"]:
        raise ValueError("Head did not advance; this readback does not confirm execution")
    candidates = []
    for role, expected in zip(pending["roles"], pending["expected_features"]):
        matches = [f for f in response["features"] if f.get("name") == expected["name"]]
        if len(matches) != 1 or matches[0].get("featureType") != expected["featureType"]:
            raise ValueError("Expected exactly one native feature for role " + role)
        actual = matches[0]
        if pending["operation"] == "update" and actual.get("featureId") != m["feature_ids"].get(role):
            raise ValueError("Parameter update changed native feature identity")
        if feature_state(response, actual["featureId"]) != "OK" or actual.get("suppressed"):
            raise ValueError("Native regeneration failed for role " + role)
        expected_params = {p["parameterId"]: p for p in expected["parameters"]}
        actual_params = {p["parameterId"]: p for p in actual["parameters"]}
        for key, parameter in expected_params.items():
            observed = actual_params.get(key, {})
            fields = ("expression",) if parameter.get("btType", "").startswith("BTMParameterQuantity") else ("expression", "value")
            for field in fields:
                if field in parameter and observed.get(field) != parameter[field]:
                    raise ValueError("Native parameter differs from the prepared value: " + key)
            if "queries" in parameter:
                wanted = [q.get("queryString") for q in parameter["queries"]]
                found = [q.get("queryString") for q in observed.get("queries", [])]
                if wanted != found:
                    raise ValueError("Native query differs from the prepared target: " + key)
            if "items" in parameter:
                expected_array = fingerprint({"parameters": [parameter]})
                actual_array = fingerprint({"parameters": [observed]})
                if expected_array != actual_array:
                    raise ValueError("Native ordered profile array differs from the prepared target: " + key)
        if expected["featureType"] == "newSketch":
            expected_entities = {e["entityId"]: e for e in expected["entities"]}
            actual_entities = {e["entityId"]: e for e in actual.get("entities", [])}
            if set(expected_entities) != set(actual_entities):
                raise ValueError("Native sketch entity set differs from its prepared definition")
            for eid, wanted in expected_entities.items():
                found = actual_entities[eid]
                for field in ("btType", "isConstruction", "startPointId", "endPointId", "centerId"):
                    if field in wanted and found.get(field) != wanted[field]:
                        raise ValueError("Native sketch entity identity differs: " + eid)
            expected_constraints = {c["entityId"]: c for c in expected["constraints"]}
            actual_constraints = {c["entityId"]: c for c in actual.get("constraints", [])}
            if set(expected_constraints) - set(actual_constraints):
                raise ValueError("Native sketch lost a required dimensional/position constraint")
            for cid, wanted in expected_constraints.items():
                found = actual_constraints[cid]
                if found.get("constraintType") != wanted["constraintType"]:
                    raise ValueError("Native sketch constraint type changed: " + cid)
                found_params = {p["parameterId"]: p for p in found["parameters"]}
                for parameter in wanted["parameters"]:
                    observed = found_params.get(parameter["parameterId"], {})
                    fields = ("expression",) if parameter.get("btType", "").startswith("BTMParameterQuantity") else ("expression", "value")
                    for field in fields:
                        if field in parameter and observed.get(field) != parameter[field]:
                            raise ValueError("Native sketch constraint differs: " + cid)
        candidates.append((role, actual))
    # Check unaffected owned features against the last bound definitions.
    affected = set(pending["roles"])
    subset = {**m, "feature_ids": {k: v for k, v in m["feature_ids"].items() if k not in affected}}
    tracked_features(subset, response)
    for role, actual in candidates:
        m["feature_ids"][role] = actual["featureId"]
        m["feature_fingerprints"][role] = fingerprint(actual)
    if pending["operation"] == "create":
        m["next_index"] += 1
    else:
        m["parameters_mm"] = pending["new_parameters_mm"]
    if pending.get("part_definition"):
        m["part_definition"] = pending["part_definition"]
        m["local_preview"] = pending.get("local_preview")
    m["journal"].append({"operation": pending["operation"], "roles": pending["roles"], "feature_ids": {r: f["featureId"] for r, f in candidates},
                         "before_microversion": pending["expected_head"], "after_microversion": response["sourceMicroversion"],
                         "request_sha256": pending["body_sha256"], "receipt": evidence})
    m["pending"] = None
    m["last_bound_microversion"] = response["sourceMicroversion"]
    m["state"] = "native-features-created" if m["next_index"] == len(m["operations"]) else "building"
    m["native_geometry_verified"] = False
    save(path, m)
    return {"bound": True, "manifest": str(path), "state": m["state"], "feature_ids": m["feature_ids"],
            "remaining_operations": len(m["operations"]) - m["next_index"], "microversion": m["last_bound_microversion"],
            "native_geometry_verified": False, "outbound_Onshape_calls": 0}


@exclusive_manifest
def prepare_recipe_update(manifest_source, parameters_mm, head_receipt, part_definition=None, local_preview=None):
    path, m = load(manifest_source)
    if m["pending"] or m["next_index"] != len(m["operations"]):
        raise ValueError("Complete and bind the current native recipe before updating parameters")
    p = recipes.normalize(m["recipe"], {**m["parameters_mm"], **parameters_mm})
    if m.get("part_definition"):
        if not part_definition:
            raise ValueError("Use prepare_part_definition to revise a journal bound to a shared definition")
        from part_development import load_definition
        definition, evidence = load_definition(part_definition["source"])
        if (evidence != part_definition or definition["parameters_mm"] != p
            or definition["recipe"] != m["recipe"] or definition["design"] != m["design"]):
            raise ValueError("Revision definition differs from the native journal")
    response, target, evidence = head(head_receipt, m["design"], m["target"])
    current = tracked_features(m, response)
    changed = [k for k, value in p.items() if value != m["parameters_mm"][k]]
    if not changed:
        return {"changed": False, "outbound_Onshape_calls": 0}
    features, roles = [], []
    for key in changed:
        role = "var:" + key
        f = copy.deepcopy(current[m["feature_ids"][role]])
        for parameter in f["parameters"]:
            if parameter["parameterId"] == "lengthValue":
                parameter["expression"] = f"{p[key]:g} mm"
        features.append(f)
        roles.append(role)
    extra = {"new_parameters_mm": p}
    if part_definition:
        extra.update({"part_definition": part_definition, "local_preview": local_preview})
    result = request(path, m, response, evidence, features, roles, "update", extra)
    return {**result, "changed_parameters_mm": {k: p[k] for k in changed},
            "scope": "Update existing named variables together; preserve native sketches/features and IDs"}


def native_recipe_status(manifest_source):
    path, m = load(manifest_source)
    return {"manifest": str(path), "recipe": m["recipe"], "state": m["state"], "parameters_mm": m["parameters_mm"],
            "target": m["target"], "feature_ids": m["feature_ids"], "pending": bool(m["pending"]),
            "next_index": m["next_index"], "operation_count": len(m["operations"]),
            "native_geometry_verified": m["native_geometry_verified"],
            "verification_evidence": m.get("verifications", [])[-1:] if m["native_geometry_verified"] else [],
            "scope": "Local saved state/evidence at the recorded microversion; this tool does not observe the live workspace",
            "outbound_Onshape_calls": 0}


@exclusive_manifest
def verify_native_recipe(manifest_source, head_receipt, body_receipt, mass_receipt):
    """Verify actual native surfaces and volume at exactly the observed head microversion."""
    path, m = load(manifest_source)
    if m["pending"] or m["next_index"] != len(m["operations"]):
        raise ValueError("Finish and bind this recipe before verifying its solid")
    response, target, head_evidence = head(head_receipt, m["design"], m["target"])
    tracked_features(m, response)
    microversion = response["sourceMicroversion"]
    if m.get("local_preview"):
        from part_development import load_definition, preview_evidence
        definition, _ = load_definition(m["part_definition"]["source"])
        current_preview = preview_evidence(m["local_preview"]["source"], definition)
        if current_preview != m["local_preview"]:
            raise ValueError("Local preview evidence was changed since native preparation")
    receipts = []
    payloads = {}
    for source, operation in ((body_receipt, "bodydetails"), (mass_receipt, "massproperties")):
        payload, identity, evidence = session_receipt(source)
        if identity != {"api_version": m["profile"]["api_version"], "document_id": target["document_id"],
                        "context_type": "m", "context_id": microversion, "element_id": target["element_id"], "operation": operation}:
            raise ValueError("Geometry must come from the same immutable target microversion as the native head")
        payloads[operation] = payload
        receipts.append(evidence)
    body = payloads["bodydetails"]
    if body.get("microversionId", {}).get("theId") != microversion:
        raise ValueError("Native BRep response microversion differs from its request")
    checks = geometry.check_brep(m["recipe"], m["parameters_mm"], body)
    mass = payloads["massproperties"]
    if mass.get("microversionId") != microversion:
        raise ValueError("Native mass-properties response microversion differs from its request")
    volume_record = mass.get("bodies", {}).get(checks["solid_id"], {})
    volume = volume_record.get("volume", [])
    if not volume or isinstance(volume[0], bool) or not isinstance(volume[0], (int, float)) or not math.isfinite(volume[0]):
        raise ValueError("Native mass-properties response lacks the checked solid volume")
    actual_volume = volume[0] * 1e9
    if not math.isclose(actual_volume, checks["expected_volume_mm3"], abs_tol=1e-5, rel_tol=1e-6):
        raise ValueError("Actual native volume differs from the recipe")
    report = {"verified_at": datetime.now(timezone.utc).isoformat(), "recipe": m["recipe"],
              "parameters_mm": m["parameters_mm"], "target": target, "microversion": microversion,
              "native_feature_ids": m["feature_ids"], "all_tracked_features_regenerated": True,
              "native_geometry": {**checks, "volume_mm3": actual_volume, "volume_matches": True},
              "part_definition": m.get("part_definition"),
              "local_preview": m.get("local_preview"),
              "evidence": [head_evidence, *receipts], "physical_validation": False,
              "assembly_motion": "Not applicable to this standalone part", "final_fabrication_release": False}
    previous = m.setdefault("verifications", [])
    report_path = path.parent / f"geometry-verification-{len(previous):03d}.json"
    save(report_path, report)
    previous.append({"report": str(report_path), "sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
                     "microversion": microversion, "parameters_mm": m["parameters_mm"]})
    m["native_geometry_verified"] = True
    m["state"] = "native-geometry-verified"
    save(path, m)
    return {"verified": True, "report": str(report_path), "microversion": microversion,
            "volume_mm3": actual_volume, "face_count": checks["face_count"],
            "scope": checks["scope"], "outbound_Onshape_calls": 0}
