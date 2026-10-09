"""Offline shared definitions, preview bindings and resumable native browser handoffs."""
import hashlib
from pathlib import Path

import local_workflow as w
import native_operations
import native_recipe_bridge as bridge
import part_spec as spec
import recipe_tools


def load_definition(source):
    path, raw, definition = w.local_json(source)
    definition = spec.validate(definition)
    if definition["design"] != "shared":
        w.design_record(definition["design"])
    return definition, {"source": path.relative_to(w.WORKSPACE).as_posix(),
                        "sha256": hashlib.sha256(raw).hexdigest(), "definition_sha256": spec.digest(definition)}


def save_part_definition(recipe, parameters_mm, label="", design="shared"):
    definition = spec.make(recipe, parameters_mm, label, design)
    if design != "shared":
        w.design_record(design)
    folder = w.project.runtime_path("part-definitions", w.WORKSPACE)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (spec.digest(definition) + ".json")
    if path.exists():
        existing, _ = load_definition(str(path))
        if existing != definition:
            raise ValueError("Existing content-addressed definition was changed")
    else:
        native_operations.atomic(path, definition)
    _, evidence = load_definition(str(path))
    return {"definition": str(path), **evidence, "recipe": recipe, "parameters_mm": definition["parameters_mm"],
            "native_cad_file": False, "outbound_Onshape_calls": 0}


async def preview_part_definition(definition_source):
    definition, evidence = load_definition(definition_source)
    result = await recipe_tools.build_part_recipe(definition["recipe"], definition["parameters_mm"],
                                                 definition["label"], definition["design"])
    if result["part_definition_sha256"] != evidence["definition_sha256"]:
        raise ValueError("Preview differs from its source definition")
    return {**result, "source_definition": evidence}


def preview_evidence(record_source, definition):
    path, raw, record = w.local_json(record_source)
    if (record.get("part_definition_sha256") != spec.digest(definition)
        or record.get("recipe") != definition["recipe"] or record.get("parameters_mm") != definition["parameters_mm"]
        or record.get("design") != definition["design"] or record.get("units") != "mm"
        or not record.get("local_geometry", {}).get("passed") or not record.get("step_roundtrip", {}).get("passed")):
        raise ValueError("Preview dimensions, owner, definition or local geometry checks do not match")
    required = {"part-definition.json", "native-plan.json", "mesh.json", "FEASIBILITY-"+definition["recipe"]+".step"}
    if not required.issubset(record.get("artifacts", {})):
        raise ValueError("Preview record is missing its checked artifacts")
    for name, expected in record["artifacts"].items():
        if not isinstance(name, str) or Path(name).name != name or "/" in name or "\\" in name:
            raise ValueError("Preview artifact must be a sibling file")
        artifact = (path.parent/name).resolve()
        if artifact.parent != path.parent.resolve() or not artifact.is_file():
            raise ValueError("Preview artifact is missing or outside its bundle")
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != expected["sha256"]:
            raise ValueError("Preview artifact was changed")
    saved, _ = load_definition(str(path.parent/"part-definition.json"))
    if saved != definition:
        raise ValueError("Preview's shared definition differs")
    return {"source": path.relative_to(w.WORKSPACE).as_posix(), "sha256": hashlib.sha256(raw).hexdigest(),
            "definition_sha256": spec.digest(definition), "local_geometry_verified": True,
            "native_geometry_verified": False}


def prepare_part_definition(definition_source, head_receipt, manifest_source="", preview_record=""):
    definition, evidence = load_definition(definition_source)
    preview = preview_evidence(preview_record, definition) if preview_record else None
    if manifest_source:
        path, manifest = bridge.load(manifest_source)
        if manifest["recipe"] != definition["recipe"] or manifest["design"] != definition["design"]:
            raise ValueError("A revision must retain its recipe family and owning design")
        previous = manifest.get("part_definition")
        if not previous:
            raise ValueError("Use a journal originally prepared from a shared part definition")
        old, old_evidence = load_definition(previous["source"])
        if old_evidence != previous or old["parameters_mm"] != manifest["parameters_mm"]:
            raise ValueError("Original shared definition or journal dimensions were changed")
        result = bridge.prepare_recipe_update(manifest_source, definition["parameters_mm"], head_receipt, evidence, preview)
        if result.get("changed") is False:
            return {**result, "manifest": str(path), "definition_bound": False,
                    "next": "Dimensions are unchanged; the journal retains its current definition"}
        return {**result, "definition": evidence, "local_preview": preview}
    result = bridge.prepare_native_recipe(definition["recipe"], definition["parameters_mm"], head_receipt,
                                           definition["label"], definition["design"], evidence, preview)
    return {**result, "definition": evidence, "local_preview": preview}


def part_development_status(definition_source, manifest_source=""):
    definition, evidence = load_definition(definition_source)
    result = {"definition": evidence, "recipe": definition["recipe"], "parameters_mm": definition["parameters_mm"],
              "native_geometry_verified": False, "outbound_Onshape_calls": 0}
    if not manifest_source:
        return {**result, "next": "preview_part_definition, then prepare_part_definition using a fresh empty native Part Studio head"}
    path, manifest = bridge.load(manifest_source)
    current = manifest.get("part_definition")
    pending_definition = (manifest.get("pending") or {}).get("part_definition")
    if evidence not in (current, pending_definition):
        raise ValueError("Definition is not the journal's current or pending revision")
    result["native"] = bridge.native_recipe_status(manifest_source)
    result["native_geometry_verified"] = result["native"]["native_geometry_verified"] and evidence == current
    if result["native_geometry_verified"]:
        entry = manifest["verifications"][-1]
        _, raw, report = w.local_json(entry["report"])
        if hashlib.sha256(raw).hexdigest() != entry["sha256"] or report.get("part_definition") != evidence:
            raise ValueError("Saved native verification is altered or bound to another definition")
    if manifest["pending"]:
        result["next"] = "Read the live target and bind_recipe_step; never blindly repeat a pending request"
    elif manifest["next_index"] < len(manifest["operations"]):
        result["next"] = "prepare_recipe_step from a fresh head, reobserve immediately, submit through session Explorer, then bind_recipe_step"
    else:
        result["next"] = "verify_native_recipe with actual immutable geometry, then verify a meaningful parameter change"
    result["scope"] = "Saved receipts only; this does not observe a live model or certify physical fit"
    return result


def verify_part_parameter_change(manifest_source, baseline_report):
    path, manifest = bridge.load(manifest_source)
    if not manifest.get("native_geometry_verified") or len(manifest.get("verifications", [])) < 2:
        raise ValueError("Verify baseline and changed native geometry before checking parameter behavior")
    baseline_path, baseline_raw, baseline = w.local_json(baseline_report)
    entries = manifest["verifications"]
    recorded = next((v for v in entries[:-1] if Path(v["report"]).resolve() == baseline_path.resolve()), None)
    if not recorded or hashlib.sha256(baseline_raw).hexdigest() != recorded["sha256"]:
        raise ValueError("Baseline is not an unchanged verification from this journal")
    _, changed_raw, changed = w.local_json(entries[-1]["report"])
    if hashlib.sha256(changed_raw).hexdigest() != entries[-1]["sha256"]:
        raise ValueError("Changed native geometry verification was modified")
    if baseline["target"] != changed["target"] or baseline["native_feature_ids"] != changed["native_feature_ids"]:
        raise ValueError("Parameter test must preserve the target and native feature IDs")
    if baseline["microversion"] == changed["microversion"] or baseline["parameters_mm"] == changed["parameters_mm"]:
        raise ValueError("Parameter test needs changed dimensions and a different native microversion")
    before, after = baseline["native_geometry"], changed["native_geometry"]
    # Face IDs can change without geometric change. Compare checked analytic surfaces instead.
    import native_recipe_geometry as geometry
    if geometry.expected_faces(manifest["recipe"], baseline["parameters_mm"]) == geometry.expected_faces(manifest["recipe"], changed["parameters_mm"]):
        raise ValueError("Saved geometry does not demonstrate a meaningful parameter change")
    report = {"passed": True, "before_microversion": baseline["microversion"], "after_microversion": changed["microversion"],
              "feature_ids_preserved": True, "parameters_before_mm": baseline["parameters_mm"],
              "parameters_after_mm": changed["parameters_mm"], "native_volume_before_mm3": before["volume_mm3"],
              "native_volume_after_mm3": after["volume_mm3"], "physical_validation": False,
              "scope": "Recorded baseline and changed native geometry; does not prove later live state", "outbound_Onshape_calls": 0}
    return report
