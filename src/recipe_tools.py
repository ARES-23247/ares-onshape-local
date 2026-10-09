"""Lightweight MCP-facing recipe tools. Geometry runs in a fixed, isolated subprocess."""
import asyncio
import html
import hashlib
import json
from pathlib import Path
import re
import sys
import os
from uuid import uuid4

import local_workflow as workflow
import part_recipes as recipes
import part_spec

BASE = Path(__file__).resolve().parent
CAD_PYTHON = Path(os.environ.get("ARES_ONSHAPE_CAD_PYTHON", BASE.parent / ".venv-build123d" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")))


def list_part_recipes():
    environment = CAD_PYTHON.parent.parent
    module_paths = [environment / "Lib/site-packages/build123d/__init__.py"]
    module_paths += list((environment / "lib").glob("python*/site-packages/build123d/__init__.py"))
    return {**recipes.catalog(), "local_engine_installed": CAD_PYTHON.is_file() and any(p.is_file() for p in module_paths),
            "native_handoff": "prepare_native_recipe/prepare_recipe_step compile these recipes to tracked native variables/sketches/extrudes from fresh session receipts; the host executes in Explorer",
            "conversion_scope": "Six bounded families; added hub, radial plate and lofted guide require live native validation. Arbitrary CAD programs and STEP histories are not converted"}


def write_preview(folder, label):
    mesh = json.loads((folder / "mesh.json").read_text(encoding="utf-8"))
    record = json.loads((folder / "recipe.json").read_text(encoding="utf-8"))
    template = (BASE / "recipe-preview.html").read_text(encoding="utf-8")
    template = template.replace("__TITLE__", html.escape(label)).replace("__RECIPE__", html.escape(record["recipe"]))
    template = template.replace("__METRICS__", html.escape(f'{record["local_geometry"]["volume_mm3"]:.2f} mmÂ³ Â· {record["local_geometry"]["solid_count"]} valid solid Â· STEP roundtrip passed'))
    template = template.replace("__PARAMETERS__", html.escape(json.dumps(record["parameters_mm"], indent=2)))
    template = template.replace("__MESH_JSON__", json.dumps(mesh, separators=(",", ":")))
    preview = folder / "preview.html"
    preview.write_text(template, encoding="utf-8")
    record["artifacts"][preview.name] = {"bytes": preview.stat().st_size,
                                         "sha256": hashlib.sha256(preview.read_bytes()).hexdigest()}
    (folder / "recipe.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


async def build_part_recipe(recipe, parameters_mm, label="", design="shared", source_snapshot=""):
    parameters = recipes.normalize(recipe, parameters_mm)
    if not isinstance(label, str) or len(label) > 80 or (label and not re.fullmatch(r"[A-Za-z0-9 _.-]+", label)):
        raise ValueError("Use a label of up to 80 letters, numbers, spaces, underscores, dots or hyphens")
    if design != "shared":
        workflow.design_record(design)
    provenance = {"kind": "operator-supplied recipe dimensions", "hardware_match_verified": False}
    if source_snapshot:
        evidence = workflow.read_snapshot(source_snapshot, limit=1)
        provenance.update({k: evidence[k] for k in ("source", "file_sha256", "identity")})
        provenance["applicability"] = "Operator must establish that this recorded interface applies to the chosen design"
    if not CAD_PYTHON.is_file():
        raise ValueError("Install the isolated build123d environment using requirements-build123d.txt")
    root = workflow.project.runtime_path("FEASIBILITY-local-recipes", workflow.WORKSPACE) / design
    folder = root / uuid4().hex
    if not folder.resolve().is_relative_to(workflow.WORKSPACE.resolve()):
        raise ValueError("Recipe output must stay inside the workspace")
    job = {"recipe": recipe, "parameters_mm": parameters, "label": label or ("ARES " + recipe),
           "design": design, "output_dir": str(folder), "source_provenance": provenance}
    job["part_definition"] = part_spec.make(recipe, parameters, job["label"], design)
    process = await asyncio.create_subprocess_exec(
        str(CAD_PYTHON), str(BASE / "recipe_worker.py"), cwd=str(workflow.WORKSPACE),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        creationflags=0x08000000 if sys.platform == "win32" else 0)
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(json.dumps(job).encode()), timeout=45)
        if len(stdout) > 64000:
            raise ValueError("Unexpected oversized geometry worker response")
        try:
            result = json.loads(stdout.decode("utf-8-sig"))
        except (ValueError, UnicodeDecodeError):
            raise ValueError("Local geometry worker failed to initialize; check its isolated dependencies") from None
        if process.returncode:
            raise ValueError("Local recipe generation failed: " + result.get("message", "worker error"))
        write_preview(folder, job["label"])
        result["preview"] = str(folder / "preview.html")
        result["parameters_mm"] = parameters
        result["design"] = design
        result["native_construction_plan"] = recipes.native_plan(recipe, parameters)
        return result
    except asyncio.TimeoutError:
        raise ValueError("Local recipe generation exceeded 45 seconds; partial FEASIBILITY output is not verified") from None
    finally:
        if process.returncode is None:
            process.kill()
            await process.communicate()
