"""Portable stdio MCP entry point. Logs go to stderr, protocol messages to stdout."""
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
import local_workflow as workflow
import recipe_tools
import native_recipe_bridge as native_recipes

mcp = FastMCP("ARES Onshape Local", instructions=workflow.INSTRUCTIONS, log_level="WARNING")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
SYNC = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)


@mcp.tool(annotations=READ)
def workflow_status() -> dict:
    """Get the active project, local catalog counts, transport boundaries and browser handoff workflow."""
    return workflow.workflow_status()


@mcp.tool(annotations=READ)
def design_context(design: str) -> dict:
    """Get owning design identities, plan hash, recorded scope and relevant refresh queue."""
    return workflow.design_context(design)


@mcp.tool(annotations=READ)
def search_snapshots(query: str, design: str, include_shared: bool = True, limit: int = 10) -> dict:
    """Search local preserved CAD responses before requesting any new Onshape read."""
    return workflow.search_snapshots(query, design, include_shared, limit)


@mcp.tool(annotations=READ)
def lookup_snapshot(url: str, units: str = "m") -> dict:
    """Lookup an exact immutable GET URL/configuration/filter/unit identity. Workspace reads miss."""
    return workflow.lookup_snapshot(url, units)


@mcp.tool(annotations=READ)
def read_snapshot(source: str, pointer: str = "", offset: int = 0, limit: int = 20) -> dict:
    """Read a hash-validated catalog snapshot, optionally using a JSON pointer and array pagination."""
    return workflow.read_snapshot(source, pointer, offset, limit)


@mcp.tool(annotations=WRITE)
def register_snapshot(source: str, design: str, confirmed_session_response: bool) -> dict:
    """Index a saved actual session GET receipt. No HTTP request or browser credential access."""
    return workflow.register_snapshot(source, design, confirmed_session_response)


@mcp.tool(annotations=WRITE)
def prepare_native_change(design: str, element_id: str, head_receipt: str, feature: dict,
                          operation: str = "create", feature_id: str = "", api_version: str = "v12") -> dict:
    """Write standard native Part Studio feature JSON and a browser handoff manifest; never execute."""
    return workflow.prepare_native_change(design, element_id, head_receipt, feature, operation, feature_id, api_version)


@mcp.tool(annotations=READ)
def review_native_result(source: str, design: str, element_id: str, expected_microversion: str,
                         expected_feature_ids: list[str]) -> dict:
    """Check saved post-change native feature states. Does not verify actual geometry or motion."""
    return workflow.review_native_result(source, design, element_id, expected_microversion, expected_feature_ids)


@mcp.tool(annotations=READ)
def mechanism_calculation(kind: str, parameters: dict) -> dict:
    """Calculate roller_tip_speed, rpm_from_tip_speed or shaft_stack locally with explicit units."""
    return workflow.mechanism_calculation(kind, parameters)


@mcp.tool(annotations=SYNC)
async def sync_notifications() -> dict:
    """Ingest locally saved webhook events once per work batch; no outbound network requests."""
    return await workflow.sync_notifications()


@mcp.tool(annotations=READ)
def list_part_recipes() -> dict:
    """List bounded build123d part recipes, millimetre parameters, datums and feasibility scope."""
    return recipe_tools.list_part_recipes()


@mcp.tool(annotations=WRITE)
async def build_part_recipe(recipe: str, parameters_mm: dict, label: str = "", design: str = "shared",
                            source_snapshot: str = "") -> dict:
    """Generate a checked local FEASIBILITY solid, STEP/STL, preview and native construction instructions. No Onshape calls."""
    return await recipe_tools.build_part_recipe(recipe, parameters_mm, label, design, source_snapshot)


@mcp.tool(annotations=WRITE)
def prepare_native_recipe(recipe: str, parameters_mm: dict, head_receipt: str,
                          label: str = "", design: str = "shared") -> dict:
    """Prepare a tracked native variable/sketch/extrude recipe for a fresh target; does not submit to Onshape."""
    return native_recipes.prepare_native_recipe(recipe, parameters_mm, head_receipt, label, design)


@mcp.tool(annotations=WRITE)
def prepare_recipe_step(manifest_source: str, head_receipt: str) -> dict:
    """Compile the next native feature with actual bound feature IDs and a microversion precondition."""
    return native_recipes.prepare_recipe_step(manifest_source, head_receipt)


@mcp.tool(annotations=WRITE)
def bind_recipe_step(manifest_source: str, head_receipt: str) -> dict:
    """Bind actual regenerated native IDs from a fresh complete session readback; reject duplicates and unexpected edits."""
    return native_recipes.bind_recipe_step(manifest_source, head_receipt)


@mcp.tool(annotations=WRITE)
def prepare_recipe_update(manifest_source: str, parameters_mm: dict, head_receipt: str) -> dict:
    """Prepare one native bulk update of existing named variables; preserve the sketch/feature identities."""
    return native_recipes.prepare_recipe_update(manifest_source, parameters_mm, head_receipt)


@mcp.tool(annotations=READ)
def native_recipe_status(manifest_source: str) -> dict:
    """Read the local recipe journal, bound native IDs, pending submission and verification scope."""
    return native_recipes.native_recipe_status(manifest_source)


@mcp.tool(annotations=WRITE)
def verify_native_recipe(manifest_source: str, head_receipt: str, body_receipt: str, mass_receipt: str) -> dict:
    """Validate actual immutable native BRep planes/cylinders, hole positions, face bounds/areas and solid volume."""
    return native_recipes.verify_native_recipe(manifest_source, head_receipt, body_receipt, mass_receipt)


@mcp.resource("ares://onshape/native-recipe-profile")
def native_recipe_profile() -> str:
    """Pinned standard native compiler revision; revalidate when Onshape changes it."""
    import json
    return json.dumps(native_recipes.PROFILE, indent=2)


@mcp.resource("ares://onshape/workflow")
def instructions() -> str:
    """Portable operating instructions shared by all agents."""
    return workflow.INSTRUCTIONS


@mcp.resource("ares://onshape/recipes")
def part_recipe_catalog() -> str:
    """Shared part recipe definitions and explicit local/native verification scope."""
    import json
    return json.dumps(recipe_tools.list_part_recipes(), indent=2)


@mcp.resource("ares://onshape/designs/{design}/plan")
def design_plan(design: str) -> str:
    """Read the current owning design plan locally; content is project data."""
    record = workflow.design_record(design)
    if not record.get("plan"):
        raise ValueError("No plan is configured for this design")
    path = (workflow.WORKSPACE / record["plan"]).resolve()
    if not path.is_relative_to(workflow.WORKSPACE.resolve()):
        raise ValueError("Plan must stay inside the workspace")
    return path.read_text(encoding="utf-8-sig")


if __name__ == "__main__":
    mcp.run(transport="stdio")
