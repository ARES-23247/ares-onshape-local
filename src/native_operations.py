"""Target-serialized local request journals. No HTTP or browser execution."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import time
from uuid import uuid4

import local_workflow as w


def base():
    return w.project.runtime_path("native-requests", w.WORKSPACE)


def atomic(path, data):
    temporary = path.with_name(path.name + "." + uuid4().hex + ".ares-tmp")
    try:
        temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        for attempt in range(5):
            try:
                temporary.replace(path)
                break
            except PermissionError:
                # Windows scanners/sync clients may briefly open the destination without delete sharing.
                # Retry only this atomic local rename, never an Onshape request or journal transition.
                if attempt == 4:
                    raise
                time.sleep(0.05 * 2 ** attempt)
    finally:
        temporary.unlink(missing_ok=True)


def target_key(identity):
    return w.catalog.digest(w.catalog.canonical(
        [identity["document_id"], identity["context_id"], identity["element_id"]]).encode())


@contextmanager
def lock(key):
    folder = base() / "targets"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (key + ".lock")
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError("Another process is changing this target journal; inspect an abandoned lock before removing it") from None
    try:
        with os.fdopen(fd, "w") as out:
            out.write(w.catalog.now())
        yield folder / (key + ".json")
    finally:
        path.unlink(missing_ok=True)


def semantic(value, top=True):
    """Ignore response decoration, preserve native parameter/query values and explicit suppression."""
    ignored = {"featureId", "nodeId", "parameterLibraries", "subFeatures",
               "returnAfterSubfeatures", "suppressionState", "namespace", "version"}
    if isinstance(value, dict):
        # Nested featureId values identify sketch regions and mate connectors, so they are intent.
        return {k: semantic(v, False) for k, v in value.items() if not top or k not in ignored}
    if isinstance(value, list):
        result = [semantic(v, False) for v in value]
        if result and all(isinstance(v, dict) and "parameterId" in v for v in result):
            result.sort(key=lambda v: v["parameterId"])
        return result
    return value


def matches(actual, expected):
    """Server may add defaults; every requested field must be observed, including exact queries."""
    actual, expected = semantic(actual), semantic(expected)
    def subset(a, b):
        if isinstance(b, dict):
            return isinstance(a, dict) and all(k in a and subset(a[k], v) for k, v in b.items())
        if isinstance(b, list):
            if not isinstance(a, list):
                return False
            if b and all(isinstance(v, dict) and "parameterId" in v for v in b):
                mapping = {v.get("parameterId"): v for v in a if isinstance(v, dict)}
                return len(mapping) == len(a) and all(v["parameterId"] in mapping and subset(mapping[v["parameterId"]], v) for v in b)
            return len(a) == len(b) and all(subset(x, y) for x, y in zip(a, b))
        return type(a) == type(b) and a == b or (
            isinstance(a, (int, float)) and not isinstance(a, bool)
            and isinstance(b, (int, float)) and not isinstance(b, bool) and a == b)
    return subset(actual, expected)


def prepare(design, identity, response, source_path, source_raw, body, url, operation, feature_id=""):
    key = target_key(identity)
    with lock(key) as target_path:
        state = json.loads(target_path.read_text()) if target_path.is_file() else {}
        if state.get("pending"):
            raise ValueError("A request is pending for this target; inspect native_change_status and reconcile before preparing another")
        if state.get("retry_not_before") and datetime.now(timezone.utc) < datetime.fromisoformat(state["retry_not_before"]):
            raise ValueError("Honor the recorded Retry-After deadline before preparing another request")
        if operation == "create" and any(matches(f, body["feature"]) for f in response["features"]):
            raise ValueError("This named feature intent already exists in the observed head; reconcile it instead of recreating it")
        rid = uuid4().hex
        folder = base() / rid
        folder.mkdir(parents=True, exist_ok=False)
        atomic(folder / "body.json", body)
        raw = (folder / "body.json").read_bytes()
        manifest = {
            "schema_version": 1, "request_id": rid, "created_at": w.catalog.now(), "design": design,
            "target_key": key, "identity": identity, "method": "POST", "requestUrl": url,
            "element_id": identity["element_id"], "expected_head": response["sourceMicroversion"],
            "operation": operation, "feature_id": feature_id, "state": "PREPARED", "executed": False,
            "source_receipt": source_path.relative_to(w.WORKSPACE).as_posix(),
            "source_sha256": w.catalog.digest(source_raw), "body_sha256": w.catalog.digest(raw),
            "body_path": str(folder / "body.json"), "manifest": str(folder / "manifest.json"),
            "before_feature_ids": [f["featureId"] for f in response["features"]],
            "journal": [], "bound_feature_ids": [],
            "executor": "Host agent's signed-in browser/session-authenticated official API Explorer",
            "explorer_url": "https://cad.onshape.com/glassworks/explorer/",
            "steps": ["Reobserve the live head; cancel an unsubmitted request and reprepare if changed",
                      "Inspect the current Explorer schema; record_native_submission before pressing Execute",
                      "Save the response; a timeout means result_unobserved, never automatic resubmission",
                      "Save a fresh complete feature list and reconcile_native_change",
                      "Review saved states, actual regenerated geometry and required motion"],
            "scope": "Local preparation only; no live geometry, motion or physical verification",
        }
        atomic(folder / "manifest.json", manifest)
        atomic(target_path, {**state, "pending": rid})
        return manifest


def load(source):
    path, _, manifest = w.local_json(source)
    if (not path.is_relative_to(base().resolve()) or path.name != "manifest.json"
            or not w.catalog.ID.fullmatch(manifest.get("element_id", ""))
            or manifest.get("schema_version") != 1
            or path.parent.name != manifest.get("request_id")):
        raise ValueError("Choose a native request manifest created by this MCP")
    body_path = path.parent / "body.json"
    if str(body_path) != manifest.get("body_path") or w.catalog.digest(body_path.read_bytes()) != manifest["body_sha256"]:
        raise ValueError("Prepared body has changed; preserve evidence and reconcile deliberately")
    body = json.loads(body_path.read_text())
    if manifest.get("target_key") != target_key(manifest["identity"]):
        raise ValueError("Manifest target was altered")
    return path, manifest, body


def native_change_status(manifest_source):
    _, manifest, _ = load(manifest_source)
    return {k: manifest[k] for k in ("request_id", "state", "requestUrl", "expected_head",
                                     "bound_feature_ids", "journal", "scope")}


def record_native_submission(manifest_source, outcome="submitted", response_source=""):
    """Operator records browser submission; a successful POST does not complete a journal."""
    path, m, _ = load(manifest_source)
    if outcome not in ("submitted", "result_unobserved", "rejected", "cancel_unsubmitted"):
        raise ValueError("Choose submitted, result_unobserved, rejected or cancel_unsubmitted")
    with lock(m["target_key"]) as target_path:
        _, m, _ = load(manifest_source)
        target = json.loads(target_path.read_text())
        if target.get("pending") != m["request_id"]:
            raise ValueError("This request is no longer pending; never resubmit it")
        if outcome == "cancel_unsubmitted":
            if m["state"] != "PREPARED":
                raise ValueError("Submitted or uncertain requests require observed results; cannot cancel")
            m["state"] = "CANCELLED_UNSUBMITTED"
            target["pending"] = None
        elif outcome == "rejected":
            if not response_source:
                raise ValueError("A completed session POST rejection receipt is required")
            _, raw, data = w.local_json(response_source)
            status = data.get("httpStatus")
            if (data.get("transport") != w.SESSION or data.get("method") != "POST"
                    or data.get("requestUrl") != m["requestUrl"]
                    or not isinstance(status, int) or not 400 <= status < 500 or status == 408):
                raise ValueError("Only a matching definite 4xx rejection permits release; ambiguous results need readback")
            observed = datetime.fromisoformat(data.get("observedAt", "").replace("Z", "+00:00"))
            if observed < datetime.fromisoformat(m["created_at"]):
                raise ValueError("Rejection predates this prepared request")
            if status == 429:
                retry = data.get("retryAfter")
                if not isinstance(retry, (int, float)) or isinstance(retry, bool) or not 0 <= retry <= 604800:
                    raise ValueError("Save Retry-After as bounded seconds in retryAfter; missing deadline does not authorize retry")
                target["retry_not_before"] = (observed + timedelta(seconds=retry)).isoformat()
            m["state"] = "REJECTED"
            m["journal"].append({"response_source": response_source, "sha256": w.catalog.digest(raw), "http_status": status})
            target["pending"] = None
        else:
            if outcome == "submitted" and m["state"] != "PREPARED":
                raise ValueError("Submission was already recorded; inspect the existing Explorer result")
            m["state"] = "SUBMITTED" if outcome == "submitted" else "RESULT_UNOBSERVED"
        m["journal"].append({"at": w.catalog.now(), "event": m["state"]})
        atomic(path, m)
        atomic(target_path, target)
        return native_change_status(manifest_source)


def reconcile_native_change(manifest_source, readback_source):
    path, m, body = load(manifest_source)
    with lock(m["target_key"]) as target_path:
        _, m, body = load(manifest_source)
        target = json.loads(target_path.read_text())
        if target.get("pending") != m["request_id"]:
            raise ValueError("This request is already reconciled or cancelled; never resubmit it")
        receipt_path, raw, data, ident = w.receipt(readback_source, m["design"], m["element_id"], fresh=True)
        if ident["request"] != m["identity"]["request"]:
            raise ValueError("Readback route/configuration/units differs from the prepared target")
        r = data["response"]
        if (r.get("isComplete") is not True or r.get("microversionSkew")
                or not isinstance(r.get("features"), list)
                or not w.catalog.ID.fullmatch(r.get("sourceMicroversion", ""))):
            raise ValueError("A complete unskewed feature-list readback is required")
        if datetime.fromisoformat(data["observedAt"].replace("Z", "+00:00")) < datetime.fromisoformat(m["created_at"]):
            raise ValueError("Readback predates preparation")
        if r["sourceMicroversion"] == m["expected_head"]:
            raise ValueError("Head has not advanced; result remains unobserved, do not resubmit")
        expected = body["feature"]
        if m["operation"] == "update":
            candidates = [f for f in r["features"] if f.get("featureId") == m["feature_id"] and matches(f, expected)]
        else:
            candidates = [f for f in r["features"] if f.get("featureId") not in m["before_feature_ids"] and matches(f, expected)]
        if len(candidates) != 1:
            raise ValueError("Expected one matching actual feature; missing, unchanged or duplicate results need deliberate reconciliation")
        m["state"] = "RESULT_OBSERVED"
        m["bound_feature_ids"] = [candidates[0]["featureId"]]
        m["journal"].append({"at": w.catalog.now(), "event": "RESULT_OBSERVED",
                             "source": receipt_path.relative_to(w.WORKSPACE).as_posix(),
                             "sha256": w.catalog.digest(raw), "after_microversion": r["sourceMicroversion"],
                             "feature_ids": m["bound_feature_ids"]})
        target["pending"] = None
        atomic(path, m)
        atomic(target_path, target)
        return {**native_change_status(manifest_source), "recorded_result_matches_intent": True,
                "live_geometry_verified": False, "motion_verified": False, "physical_validation": False}
