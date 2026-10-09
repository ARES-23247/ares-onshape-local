"""Exercise the actual stdio server in a private synthetic temporary workspace."""
import asyncio
import argparse
import copy
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO = Path(__file__).resolve().parents[1]


def value(result):
    if result.isError:
        raise AssertionError("Unexpected MCP error: " + str(result.content))
    return result.structuredContent or json.loads(result.content[0].text)


async def verify(geometry=False):
    test_root = REPO / ".test-runs"
    test_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ares-onshape-protocol-", dir=test_root) as folder:
        root = Path(folder)
        (root / "PLAN.md").write_text("Synthetic verification plan")
        config = {"project": "Synthetic protocol workspace", "designs": {"demo": {
            "plan": "PLAN.md", "onshape": {"document_id": "a" * 24, "workspace_id": "b" * 24}}},
            "shared_references": {"library": {"document_id": "f" * 24}}, "event_dir": "events"}
        (root / "onshape-project.json").write_text(json.dumps(config))
        response = {"isComplete": True, "sourceMicroversion": "1" * 24,
                    "libraryVersion": 3083, "serializationVersion": "1.2.21",
                    "features": [], "featureStates": {},
                    "defaultFeatures": [{"name": n, "featureId": n, "featureType": "defaultPlane"}
                                        for n in ("Top", "Front", "Right")]}
        target = "https://cad.onshape.com/api/v17/partstudios/d/" + "a" * 24 + "/w/" + "b" * 24 + "/e/" + "c" * 24 + "/features"
        def save(name, url=target, payload=None):
            path = root / name
            path.write_text(json.dumps({"requestUrl": url, "method": "GET", "httpStatus": 200,
                "transport": "onshape-session", "observedAt": datetime.now(timezone.utc).isoformat(),
                "test_fixture": "SIMULATED identities/responses; no live requests", "response": payload or response}))
            return str(path)
        save("head.json")
        immutable = target.replace("/w/" + "b" * 24, "/m/" + "1" * 24)
        save("frozen.json", immutable)
        env = {**os.environ, "ARES_ONSHAPE_WORKSPACE": str(root), "ARES_ONSHAPE_PROJECT": str(root / "onshape-project.json")}
        params = StdioServerParameters(command=sys.executable, args=[str(REPO / "src/server.py")], cwd=str(root), env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=30)) as session:
                init = await session.initialize()
                assert init.serverInfo.name == "ARES Onshape Local"
                tools = (await session.list_tools()).tools
                assert len(tools) == 30
                assert value(await session.call_tool("workflow_status", {}))["project"] == config["project"]
                context = value(await session.call_tool("design_context", {"design": "demo"}))
                assert context["authoritative_destination"]["document_id"] == "a" * 24
                value(await session.call_tool("register_snapshot", {"source": "frozen.json", "design": "demo", "confirmed_session_response": True}))
                assert value(await session.call_tool("lookup_snapshot", {"url": immutable}))["hit"]
                assert not value(await session.call_tool("lookup_snapshot", {"url": target}))["hit"]
                assert (await session.call_tool("lookup_snapshot", {"url": target.replace("features", "featurescript")})).isError
                assert value(await session.call_tool("read_snapshot", {"source": "frozen.json"}))["file_sha256"]
                assert value(await session.call_tool("search_snapshots", {"query": "", "design": "demo"}))["total_matches"] == 1
                calculation = value(await session.call_tool("mechanism_calculation", {"kind": "shaft_stack",
                    "parameters": {"thicknesses_mm": [10, 15, 2], "available_length_mm": 30}}))
                assert calculation["result"]["remaining_length_mm"] == 3
                prepared = value(await session.call_tool("prepare_native_change", {"design": "demo", "element_id": "c" * 24,
                    "head_receipt": "head.json", "feature": {"btType": "BTMFeature-134", "featureType": "extrude", "name": "Synthetic", "parameters": []}, "api_version": "v17"}))
                assert not prepared["executed"] and Path(prepared["body_path"]).is_file()
                status = value(await session.call_tool("native_change_status", {"manifest_source": prepared["manifest"]}))
                assert status["state"] == "PREPARED"
                assert (await session.call_tool("prepare_native_change", {"design": "demo", "element_id": "c" * 24,
                    "head_receipt": "head.json", "feature": {"btType": "BTMFeature-134", "featureType": "extrude",
                    "name": "Synthetic", "parameters": []}})).isError
                value(await session.call_tool("record_native_submission", {"manifest_source": prepared["manifest"]}))
                after = copy.deepcopy(response)
                created = json.loads(Path(prepared["body_path"]).read_text())["feature"]
                created["featureId"] = "SIMULATED-created"
                after["features"].append(created)
                after["featureStates"][created["featureId"]] = {"featureStatus": "OK"}
                after["sourceMicroversion"] = "2" * 24
                save("after.json", payload=after)
                bound = value(await session.call_tool("reconcile_native_change", {
                    "manifest_source": prepared["manifest"], "readback_source": "after.json"}))
                assert bound["bound_feature_ids"] == [created["featureId"]]
                save("library.json", immutable.replace("a" * 24, "f" * 24))
                reference = value(await session.call_tool("register_reference_snapshot", {
                    "source": "library.json", "reference": "library", "confirmed_session_response": True}))
                assert not reference["editable_target"]
                mate = {"btType": "BTMMate-64", "featureType": "mate", "name": "Synthetic revolute",
                        "featureId": "SIMULATED-mate", "parameters": [
                            {"parameterId": "mateType", "btType": "BTMParameterEnum-145", "value": "REVOLUTE"},
                            {"parameterId": "limitAxialZ", "btType": "BTMParameterBoolean-144", "value": False}]}
                assembly_features = copy.deepcopy(response)
                assembly_features["features"] = [mate]
                assembly_features["featureStates"] = {mate["featureId"]: {"featureStatus": "OK"}}
                assembly_url = target.replace("partstudios", "assemblies")
                save("assembly-features.json", assembly_url, assembly_features)
                wanted = copy.deepcopy(mate)
                wanted.pop("featureId")
                wanted["name"] = "Synthetic additional revolute"
                assembly_prepared = value(await session.call_tool("prepare_assembly_change", {
                    "design": "demo", "element_id": "c" * 24, "head_receipt": "assembly-features.json",
                    "feature": wanted, "template_feature_id": mate["featureId"]}))
                value(await session.call_tool("record_native_submission", {
                    "manifest_source": assembly_prepared["manifest"], "outcome": "cancel_unsubmitted"}))
                identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
                assembly = {"rootAssembly": {"documentId": "a" * 24, "elementId": "c" * 24,
                    "documentMicroversion": "1" * 24, "instances": [],
                    "occurrences": [{"path": ["SIMULATED-root"], "transform": identity}]}}
                definition_url = assembly_url.rsplit("/", 1)[0]
                save("assembly.json", definition_url, assembly)
                result = value(await session.call_tool("review_assembly_result", {
                    "features_source": "assembly-features.json", "assembly_source": "assembly.json",
                    "design": "demo", "element_id": "c" * 24, "expected_microversion": "1" * 24,
                    "expected_feature_ids": [mate["featureId"]]}))
                assert result["recorded_assembly_expectations_met"]
                result = value(await session.call_tool("review_assembly_motion", {
                    "design": "demo", "element_id": "c" * 24, "baseline_source": "assembly.json",
                    "baseline_microversion": "1" * 24, "restored_source": "assembly.json",
                    "restored_microversion": "1" * 24, "observations": [{"source": "assembly.json",
                        "microversion": "1" * 24, "command": {"feature_id": mate["featureId"], "value": 0, "units": "deg"},
                        "expected_poses": [{"path": ["SIMULATED-root"], "transform": identity}]}]}))
                assert result["neutral_pose_restored"] and not result["motion_verified"]
                assert len(value(await session.call_tool("list_part_recipes", {}))["recipes"]) == 6
                if geometry:
                    part = value(await session.call_tool("build_part_recipe", {"recipe": "spacer",
                        "parameters_mm": {"length": 18}, "label": "Synthetic protocol geometry"}))
                    assert part["local_geometry_passed"] and part["step_roundtrip_passed"]
                    assert Path(part["preview"]).is_file() and part["outbound_Onshape_calls"] == 0
                (root / "events").mkdir()
                (root / "events/event.json").write_text(json.dumps({"event": "onshape.model.lifecycle.createversion",
                    "messageId": "synthetic-event", "documentId": "a" * 24}))
                assert value(await session.call_tool("sync_notifications", {}))["new_events"] == 1
                assert value(await session.call_tool("sync_notifications", {}))["new_events"] == 0
                assert value(await session.call_tool("design_context", {"design": "demo"}))["refresh_queue"]
                resources = (await session.list_resources()).resources
                await session.read_resource("ares://onshape/workflow")
                await session.read_resource("ares://onshape/designs/demo/plan")
                # Exercise preparation/binding and retained IDs using explicitly simulated responses.
                sandbox = target.replace("a" * 24, "d" * 24)
                save("sandbox.json", sandbox)
                journal = value(await session.call_tool("prepare_native_recipe", {"recipe": "spacer", "parameters_mm": {}, "head_receipt": "sandbox.json"}))["manifest"]
                for index in range(5):
                    step = value(await session.call_tool("prepare_recipe_step", {"manifest_source": journal, "head_receipt": "sandbox.json"}))
                    if index == 0:
                        assert (await session.call_tool("prepare_recipe_step", {"manifest_source": journal, "head_receipt": "sandbox.json"})).isError
                    feature = json.loads(Path(step["body_path"]).read_text())["feature"]
                    feature["featureId"] = "SIMULATED-F" + str(index)
                    response["features"].append(feature)
                    response["featureStates"][feature["featureId"]] = {"featureStatus": "OK"}
                    response["sourceMicroversion"] = f"{index + 2:024x}"
                    save("sandbox.json", sandbox)
                    assert value(await session.call_tool("bind_recipe_step", {"manifest_source": journal, "head_receipt": "sandbox.json"}))["bound"]
                before = value(await session.call_tool("native_recipe_status", {"manifest_source": journal}))
                value(await session.call_tool("prepare_recipe_update", {"manifest_source": journal, "head_receipt": "sandbox.json", "parameters_mm": {"length": 18}}))
                response["features"][2]["parameters"][-1]["expression"] = "18 mm"
                response["sourceMicroversion"] = "e" * 24
                save("sandbox.json", sandbox)
                value(await session.call_tool("bind_recipe_step", {"manifest_source": journal, "head_receipt": "sandbox.json"}))
                after = value(await session.call_tool("native_recipe_status", {"manifest_source": journal}))
                assert before["feature_ids"] == after["feature_ids"] and after["parameters_mm"]["length"] == 18
                # Shared definitions use the same dimensions for preview, construction and revision.
                part_target = sandbox.replace("c"*24, "e"*24)
                response["features"] = []
                response["featureStates"] = {}
                response["sourceMicroversion"] = "1"*24
                save("part-head.json", part_target)
                definition = value(await session.call_tool("save_part_definition", {"recipe": "spacer", "parameters_mm": {}}))["definition"]
                prepared = value(await session.call_tool("prepare_part_definition", {"definition_source": definition, "head_receipt": "part-head.json"}))
                part_journal = prepared["manifest"]
                for index in range(prepared["operations"]):
                    step = value(await session.call_tool("prepare_recipe_step", {"manifest_source": part_journal, "head_receipt": "part-head.json"}))
                    feature = json.loads(Path(step["body_path"]).read_text())["feature"]
                    feature["featureId"] = "SIMULATED-part-"+str(index)
                    response["features"].append(feature)
                    response["featureStates"][feature["featureId"]] = {"featureStatus": "OK"}
                    response["sourceMicroversion"] = f"{index+2:024x}"
                    save("part-head.json", part_target)
                    value(await session.call_tool("bind_recipe_step", {"manifest_source": part_journal, "head_receipt": "part-head.json"}))
                async def verify_saved_geometry(changed=False):
                    sources = {}
                    for kind, route in (("body", "bodydetails"), ("mass", "massproperties")):
                        case = "changed" if changed and kind == "body" else "default"
                        payload = json.loads((REPO/f"tests/fixtures/spacer-{case}-{kind}.json").read_text())["response"]
                        micro = response["sourceMicroversion"]
                        if kind == "body":
                            payload["microversionId"]["theId"] = micro
                        else:
                            payload["microversionId"] = micro
                            if changed:
                                for body in payload["bodies"].values():
                                    body["volume"][0] *= 1.5
                        url = part_target.replace("/w/"+"b"*24, "/m/"+micro).replace("/features", "/"+route)
                        sources[kind] = save("part-"+kind+".json", url, payload)
                    return value(await session.call_tool("verify_native_recipe", {"manifest_source": part_journal,
                        "head_receipt": "part-head.json", "body_receipt": sources["body"], "mass_receipt": sources["mass"]}))
                baseline = await verify_saved_geometry()
                revised = value(await session.call_tool("save_part_definition", {"recipe": "spacer", "parameters_mm": {"length": 18}}))["definition"]
                update = value(await session.call_tool("prepare_part_definition", {"definition_source": revised,
                    "head_receipt": "part-head.json", "manifest_source": part_journal}))
                by_id = {f["featureId"]: f for f in response["features"]}
                for f in json.loads(Path(update["body_path"]).read_text())["features"]:
                    by_id[f["featureId"]].update(f)
                response["sourceMicroversion"] = "f"*24
                save("part-head.json", part_target)
                value(await session.call_tool("bind_recipe_step", {"manifest_source": part_journal, "head_receipt": "part-head.json"}))
                await verify_saved_geometry(changed=True)
                assert value(await session.call_tool("verify_part_parameter_change", {"manifest_source": part_journal,
                    "baseline_report": baseline["report"]}))["passed"]
                assert value(await session.call_tool("part_development_status", {"definition_source": revised,
                    "manifest_source": part_journal}))["native_geometry_verified"]
                if geometry:
                    for family in ("flanged_hub", "radial_hole_plate", "lofted_guide"):
                        source = value(await session.call_tool("save_part_definition", {"recipe": family, "parameters_mm": {}}))["definition"]
                        preview = value(await session.call_tool("preview_part_definition", {"definition_source": source}))
                        assert preview["local_geometry_passed"] and preview["step_roundtrip_passed"]
                        response["features"] = []
                        response["featureStates"] = {}
                        save("preview-head.json", part_target)
                        job = value(await session.call_tool("prepare_part_definition", {"definition_source": source,
                            "head_receipt": "preview-head.json", "preview_record": preview["record"]}))
                        assert job["local_preview"]["local_geometry_verified"]
                return {"passed": True, "transport": "actual stdio MCP", "tools_discovered": len(tools),
                        "resources_discovered": len(resources), "native_execution": "simulated receipts only", "local_geometry_executed": geometry,
                        "outbound_Onshape_calls": 0, "workspace": "isolated temporary synthetic data"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geometry", action="store_true", help="Also execute the optional isolated build123d worker")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(verify(args.geometry)), indent=2))
