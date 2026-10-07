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
            "shared_references": {}, "event_dir": "events"}
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
                assert len(tools) == 18
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
                assert len(value(await session.call_tool("list_part_recipes", {}))["recipes"]) == 3
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
                return {"passed": True, "transport": "actual stdio MCP", "tools_discovered": len(tools),
                        "resources_discovered": len(resources), "native_execution": "simulated receipts only", "local_geometry_executed": geometry,
                        "outbound_Onshape_calls": 0, "workspace": "isolated temporary synthetic data"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geometry", action="store_true", help="Also execute the optional isolated build123d worker")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(verify(args.geometry)), indent=2))
