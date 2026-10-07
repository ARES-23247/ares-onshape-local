"""Fixed local geometry worker. Receives bounded recipes over stdin; network is forbidden."""
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys
from time import perf_counter

import part_recipes as recipes

from project_config import WORKSPACE


def no_network(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto", "socket.bind"}:
        raise PermissionError("Local recipe worker forbids network access")


def run(job):
    started = perf_counter()
    sys.addaudithook(no_network)
    from build123d import export_step, export_stl, import_step
    recipe = job["recipe"]
    p = recipes.normalize(recipe, job["parameters_mm"])
    folder = Path(job["output_dir"]).resolve()
    if not folder.is_relative_to(WORKSPACE.resolve()) or "FEASIBILITY" not in folder.as_posix():
        raise ValueError("Recipe output must be a FEASIBILITY folder inside the workspace")
    folder.mkdir(parents=True, exist_ok=False)
    plan = recipes.native_plan(recipe, p)
    expected = recipes.expected_geometry(recipe, p)
    shape = recipes.build_shape(recipe, p)
    local_checks = recipes.check_shape(shape, expected)
    if not local_checks["passed"]:
        raise ValueError("Local geometry did not pass analytic bounds/volume/material checks")
    stem = "FEASIBILITY-" + recipe
    step, stl = folder / (stem + ".step"), folder / (stem + ".stl")
    if not export_step(shape, str(step)) or not export_stl(shape, str(stl), tolerance=0.05, angular_tolerance=0.1):
        raise ValueError("Local STEP/STL export failed")
    imported = import_step(str(step))
    roundtrip = recipes.check_shape(imported, expected)
    if not roundtrip["passed"]:
        raise ValueError("Exported STEP did not preserve checked geometry/units")
    vertices, triangles = shape.tessellate(0.08, angular_tolerance=0.12)
    if len(triangles) > 50000:
        raise ValueError("Preview mesh exceeds the bounded triangle budget")
    mesh = {"units": "mm", "vertices": [list(v) for v in vertices], "triangles": triangles}
    (folder / "mesh.json").write_text(json.dumps(mesh, separators=(",", ":")), encoding="utf-8")
    (folder / "native-plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    record = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
              "engine": "build123d", "engine_version": version("build123d"), "recipe": recipe,
              "label": job["label"], "design": job["design"], "units": "mm", "parameters_mm": p,
              "datum": recipes.RECIPES[recipe]["datum"], "source_provenance": job["source_provenance"],
              "local_geometry": local_checks, "step_roundtrip": roundtrip,
              "mesh_triangle_count": len(triangles), "generation_seconds": round(perf_counter() - started, 3),
              "native_plan": "native-plan.json", "native_regeneration_verified": False,
              "physical_validation": False, "final_fabrication_release": False,
              "outbound_Onshape_calls": 0, "network_access": "forbidden by worker audit hook",
              "assumptions": recipes.catalog()["assumptions"]}
    files = [step, stl, folder / "mesh.json", folder / "native-plan.json"]
    record["artifacts"] = {f.name: {"bytes": f.stat().st_size, "sha256": hashlib.sha256(f.read_bytes()).hexdigest()} for f in files}
    (folder / "recipe.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return {"recipe": recipe, "folder": str(folder), "record": str(folder / "recipe.json"),
            "step": str(step), "experimental_stl": str(stl), "native_plan": str(folder / "native-plan.json"),
            "local_geometry_passed": local_checks["passed"], "step_roundtrip_passed": roundtrip["passed"],
            "volume_mm3": shape.volume, "generation_seconds": record["generation_seconds"],
            "scope": "FEASIBILITY only; native Onshape regeneration and physical fit not verified",
            "outbound_Onshape_calls": 0}


if __name__ == "__main__":
    try:
        print(json.dumps(run(json.load(sys.stdin))))
    except Exception as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)[:500]}))
        sys.exit(1)
