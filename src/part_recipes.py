"""Bounded part recipes shared by local previews and native construction instructions.

Dimensions are millimetres. These study solids are not final native Onshape models.
This module is stdlib-only until build_shape is called in the isolated CAD worker.
"""
from __future__ import annotations

import math

RECIPES = {
    "spacer": {
        "description": "Straight cylindrical spacer with concentric through bore",
        "defaults_mm": {"outer_diameter": 20.0, "bore_diameter": 8.0, "length": 12.0},
        "datum": "XY bore centre at origin; bottom z=0; length extends in +Z",
    },
    "mounting_bracket": {
        "description": "Sharp-corner L bracket with two base holes and two upright holes",
        "defaults_mm": {"width": 30.0, "base_depth": 40.0, "height": 30.0, "thickness": 4.0,
                        "hole_diameter": 4.5, "hole_pitch_x": 18.0, "base_hole_y": 26.0,
                        "wall_hole_z": 19.0},
        "datum": "Width centred about x=0; back y=0; bottom z=0; base +Y and upright +Z",
    },
    "hole_pattern_plate": {
        "description": "Rectangular plate with four centred rectangular-pattern through holes",
        "defaults_mm": {"width": 80.0, "depth": 50.0, "thickness": 4.0,
                        "hole_diameter": 4.5, "pitch_x": 60.0, "pitch_y": 30.0},
        "datum": "Rectangle centred in XY; bottom z=0; thickness extends in +Z",
    },
    "flanged_hub": {
        "description": "Stepped cylindrical hub with a flange and concentric through bore",
        "defaults_mm": {"flange_diameter": 40.0, "hub_diameter": 24.0, "bore_diameter": 8.0,
                        "flange_thickness": 4.0, "length": 20.0},
        "datum": "Bore on Z axis; flange bottom z=0; overall length extends in +Z",
    },
    "radial_hole_plate": {
        "description": "Round plate with a centre bore and six equally spaced bolt holes",
        "defaults_mm": {"outer_diameter": 80.0, "bore_diameter": 8.0, "thickness": 4.0,
                        "hole_diameter": 4.5, "bolt_circle_diameter": 60.0},
        "datum": "Plate centred on Z axis; bottom z=0; six holes start on +X",
        "fixed_hole_count": 6,
    },
    "lofted_guide": {
        "description": "Centred rectangular transition with open ends and straight tapered walls",
        "defaults_mm": {"inlet_width": 60.0, "inlet_height": 40.0, "outlet_width": 30.0,
                        "outlet_height": 20.0, "length": 60.0, "wall": 3.0},
        "datum": "Inlet centred at z=0; outlet centred at z=length; wall measured in each XY section",
    },
}
MIN_WEB = 1.0  # Geometric guard, not a load-bearing design requirement.


def catalog():
    return {"engine": "build123d", "units": "mm", "recipes": RECIPES,
            "scope": "FEASIBILITY previews and native construction instructions; no live CAD execution",
            "assumptions": ["Sharp edges; no bend radius, print compensation, threads or material/load rating",
                            "Hole and edge webs are screened geometrically only",
                            "Use STEP for temporary solid references; STL is experimental printing data"]}


def normalize(recipe, supplied):
    if recipe not in RECIPES or not isinstance(supplied, dict):
        raise ValueError("Choose a listed bounded recipe with a parameter object")
    defaults = RECIPES[recipe]["defaults_mm"]
    if set(supplied) - set(defaults):
        raise ValueError("Unknown recipe parameter; use list_part_recipes for the allowed millimetre dimensions")
    values = {**defaults, **supplied}
    for name, value in values.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} must be a finite number in millimetres")
        if not 0.5 <= value <= 500:
            raise ValueError(f"{name} must be between 0.5 and 500 mm for this bounded preview tool")
        values[name] = float(value)
    p = values
    if recipe == "spacer":
        if (p["outer_diameter"] - p["bore_diameter"]) / 2 < MIN_WEB:
            raise ValueError("Spacer requires at least 1 mm radial wall")
    elif recipe == "hole_pattern_plate":
        d = p["hole_diameter"]
        if min((p["width"] - p["pitch_x"] - d) / 2,
               (p["depth"] - p["pitch_y"] - d) / 2,
               p["pitch_x"] - d, p["pitch_y"] - d) < MIN_WEB:
            raise ValueError("Plate holes must retain at least 1 mm edge/inter-hole web")
    elif recipe == "flanged_hub":
        if min((p["hub_diameter"] - p["bore_diameter"]) / 2,
               (p["flange_diameter"] - p["hub_diameter"]) / 2,
               p["length"] - p["flange_thickness"]) < MIN_WEB:
            raise ValueError("Hub needs at least 1 mm bore wall, flange shoulder and exposed hub length")
    elif recipe == "radial_hole_plate":
        if min((p["outer_diameter"] - p["bolt_circle_diameter"] - p["hole_diameter"]) / 2,
               (p["bolt_circle_diameter"] - p["bore_diameter"] - p["hole_diameter"]) / 2,
               p["bolt_circle_diameter"] / 2 - p["hole_diameter"]) < MIN_WEB:
            raise ValueError("Radial holes need at least 1 mm edge, bore and adjacent-hole web")
    elif recipe == "lofted_guide":
        if min(p[k] - 2 * p["wall"] for k in ("inlet_width", "inlet_height", "outlet_width", "outlet_height")) < 1:
            raise ValueError("Guide must retain at least 1 mm open width and height at both ends")
    else:
        r, t = p["hole_diameter"] / 2, p["thickness"]
        if min(p["base_depth"] - t, p["height"] - t) <= 2 * r + 2 * MIN_WEB:
            raise ValueError("Bracket legs must accommodate the thickness and holes")
        if min((p["width"] - p["hole_pitch_x"] - 2 * r) / 2, p["hole_pitch_x"] - 2 * r,
               p["base_hole_y"] - r - t, p["base_depth"] - p["base_hole_y"] - r,
               p["wall_hole_z"] - r - t, p["height"] - p["wall_hole_z"] - r) < MIN_WEB:
            raise ValueError("Bracket holes must retain at least 1 mm edge/inter-hole web and clear the corner overlap")
    return values


def expected_geometry(recipe, p):
    """Independent analytic volume and named material/void probes."""
    if recipe in ("flanged_hub", "radial_hole_plate", "lofted_guide"):
        return extended_geometry(recipe, p)
    if recipe == "spacer":
        od, bore, length = p["outer_diameter"], p["bore_diameter"], p["length"]
        return {"volume_mm3": math.pi / 4 * (od * od - bore * bore) * length,
                "bounds_min_mm": [-od / 2, -od / 2, 0], "bounds_max_mm": [od / 2, od / 2, length],
                "probes": [{"name": "bore void", "point_mm": [0, 0, length / 2], "material": False},
                           {"name": "spacer wall", "point_mm": [(od + bore) / 4, 0, length / 2], "material": True}]}
    if recipe == "hole_pattern_plate":
        w, d, t = p["width"], p["depth"], p["thickness"]
        hole = math.pi * (p["hole_diameter"] / 2) ** 2 * t
        probes = [{"name": "plate centre material", "point_mm": [0, 0, t / 2], "material": True}]
        probes += [{"name": f"plate hole {sx},{sy}", "point_mm": [sx * p["pitch_x"] / 2, sy * p["pitch_y"] / 2, t / 2],
                    "material": False} for sx in (-1, 1) for sy in (-1, 1)]
        return {"volume_mm3": w * d * t - 4 * hole, "bounds_min_mm": [-w / 2, -d / 2, 0],
                "bounds_max_mm": [w / 2, d / 2, t], "probes": probes}
    w, d, h, t = p["width"], p["base_depth"], p["height"], p["thickness"]
    hole = math.pi * (p["hole_diameter"] / 2) ** 2 * t
    probes = [{"name": "base material", "point_mm": [0, (d + t) / 2, t / 2], "material": True},
              {"name": "wall material", "point_mm": [0, t / 2, (h + t) / 2], "material": True},
              {"name": "open L interior", "point_mm": [0, (d + t) / 2, (h + t) / 2], "material": False}]
    for sx in (-1, 1):
        probes += [{"name": f"base hole {sx}", "point_mm": [sx * p["hole_pitch_x"] / 2, p["base_hole_y"], t / 2], "material": False},
                   {"name": f"wall hole {sx}", "point_mm": [sx * p["hole_pitch_x"] / 2, t / 2, p["wall_hole_z"]], "material": False}]
    return {"volume_mm3": w * t * (d + h - t) - 4 * hole,
            "bounds_min_mm": [-w / 2, 0, 0], "bounds_max_mm": [w / 2, d, h], "probes": probes}


def native_plan(recipe, p):
    """High-level native instructions, intentionally not serialized API feature bodies."""
    if recipe in ("flanged_hub", "radial_hole_plate", "lofted_guide"):
        import native_recipe_features as compiler
        steps = compiler.operations(recipe, p)
    elif recipe == "spacer":
        steps = [{"name": "Spacer annulus", "operation": "native_sketch", "plane": "XY at z=0",
                  "geometry": {"concentric_circles_diameter_mm": [p["outer_diameter"], p["bore_diameter"]]},
                  "design_intent": "Constrain common centre to origin and diameters to named variables"},
                 {"name": "Spacer length", "operation": "native_extrude_new", "depth_mm": p["length"],
                  "direction": "+Z", "region": "annulus; exclude bore"}]
    elif recipe == "hole_pattern_plate":
        steps = [{"name": "Plate profile", "operation": "native_sketch", "plane": "XY at z=0",
                  "geometry": {"centred_rectangle_mm": [p["width"], p["depth"]]},
                  "design_intent": "Constrain centre, width and depth with named variables"},
                 {"name": "Plate thickness", "operation": "native_extrude_new", "depth_mm": p["thickness"], "direction": "+Z"},
                 {"name": "Four mounting holes", "operation": "native_sketch", "plane": "XY at z=0",
                  "geometry": {"circle_diameter_mm": p["hole_diameter"], "centres_mm": [
                      [sx * p["pitch_x"] / 2, sy * p["pitch_y"] / 2] for sx in (-1, 1) for sy in (-1, 1)]},
                  "design_intent": "Constrain hole diameter and X/Y pitches with named variables"},
                 {"name": "Through holes", "operation": "native_extrude_remove", "direction": "+Z", "extent": "through all"}]
    else:
        w, d, h, t = p["width"], p["base_depth"], p["height"], p["thickness"]
        steps = [{"name": "Bracket base profile", "operation": "native_sketch", "plane": "XY at z=0",
                  "geometry": {"closed_polyline_uv_mm": [[-w / 2, 0], [w / 2, 0], [w / 2, d], [-w / 2, d]]},
                  "design_intent": "Constrain width and base depth to named variables; back edge y=0"},
                 {"name": "Bracket base", "operation": "native_extrude_new", "depth_mm": t, "direction": "+Z"},
                 {"name": "Bracket upright profile", "operation": "native_sketch", "plane": "XY at z=0",
                  "geometry": {"closed_polyline_uv_mm": [[-w / 2, 0], [w / 2, 0], [w / 2, t], [-w / 2, t]]},
                  "design_intent": "Constrain upright thickness and width to named variables"},
                 {"name": "Bracket upright", "operation": "native_extrude_add", "depth_mm": h, "direction": "+Z"},
                 {"name": "Base holes", "operation": "native_sketch", "plane": "XY at z=0",
                  "geometry": {"circle_diameter_mm": p["hole_diameter"], "centres_mm": [
                      [sx * p["hole_pitch_x"] / 2, p["base_hole_y"]] for sx in (-1, 1)]}},
                 {"name": "Base holes cut", "operation": "native_extrude_remove", "direction": "+Z", "depth_mm": t},
                 {"name": "Wall holes", "operation": "native_sketch",
                  "plane": {"origin_mm": [0, 0, 0], "u_axis": "+X", "v_axis": "+Z", "normal": "-Y"},
                  "geometry": {"circle_diameter_mm": p["hole_diameter"], "centres_mm": [
                      [sx * p["hole_pitch_x"] / 2, p["wall_hole_z"]] for sx in (-1, 1)]}},
                 {"name": "Wall holes cut", "operation": "native_extrude_remove", "direction": "+Y", "depth_mm": t}]
    return {"plan_kind": "native-construction-instructions", "recipe": recipe, "units": "mm",
            "parameters_mm": p, "named_length_variables": {k: f"{v:g} mm" for k, v in p.items()},
            "datum": RECIPES[recipe]["datum"], "steps": steps,
            "api_payloads_prepared": False, "native_regeneration_verified": False,
            "execution": "Host agent's signed-in Onshape browser/session-authenticated official API Explorer",
            "handoff": ["Choose the owning design and preserve a recovery checkpoint",
                        "Observe the target workspace head and resolve its native plane/region queries",
                        "Create named variables, constrained native sketches and standard features using current schemas",
                        "Capture returned feature IDs; prepare_native_change can bind each actual serialized feature",
                        "Compare fresh regenerated bounds/volume and changing parameters against this recipe",
                        "Verify actual geometry, changed interfaces and required motion before final release"],
            "scope": "Construction instructions only; JSON is not an importable CAD model or executable API request"}


def build_shape(recipe, p):
    from build123d import Align, Box, Cylinder, Pos, Rot, Plane, Rectangle, loft
    aligned = (Align.CENTER, Align.CENTER, Align.MIN)
    if recipe == "flanged_hub":
        part = Cylinder(p["flange_diameter"] / 2, p["flange_thickness"], align=aligned)
        part += Cylinder(p["hub_diameter"] / 2, p["length"], align=aligned)
        return part - Cylinder(p["bore_diameter"] / 2, p["length"], align=aligned)
    if recipe == "radial_hole_plate":
        part = Cylinder(p["outer_diameter"] / 2, p["thickness"], align=aligned)
        part -= Cylinder(p["bore_diameter"] / 2, p["thickness"], align=aligned)
        for x, y in radial_centres(p):
            part -= Pos(x, y, 0) * Cylinder(p["hole_diameter"] / 2, p["thickness"], align=aligned)
        return part
    if recipe == "lofted_guide":
        def transition(inset):
            return loft([Rectangle(p["inlet_width"] - 2 * inset, p["inlet_height"] - 2 * inset),
                         Plane.XY.offset(p["length"]) * Rectangle(p["outlet_width"] - 2 * inset,
                                                                  p["outlet_height"] - 2 * inset)], ruled=True)
        return transition(0) - transition(p["wall"])
    if recipe == "spacer":
        return Cylinder(p["outer_diameter"] / 2, p["length"], align=aligned) - Cylinder(p["bore_diameter"] / 2, p["length"], align=aligned)
    if recipe == "hole_pattern_plate":
        part = Box(p["width"], p["depth"], p["thickness"], align=aligned)
        for sx in (-1, 1):
            for sy in (-1, 1):
                part -= Pos(sx * p["pitch_x"] / 2, sy * p["pitch_y"] / 2, 0) * Cylinder(p["hole_diameter"] / 2, p["thickness"], align=aligned)
        return part
    align_legs = (Align.CENTER, Align.MIN, Align.MIN)
    part = Box(p["width"], p["base_depth"], p["thickness"], align=align_legs) + Box(p["width"], p["thickness"], p["height"], align=align_legs)
    for sx in (-1, 1):
        hole = Cylinder(p["hole_diameter"] / 2, p["thickness"], align=aligned)
        part -= Pos(sx * p["hole_pitch_x"] / 2, p["base_hole_y"], 0) * hole
        part -= Pos(sx * p["hole_pitch_x"] / 2, 0, p["wall_hole_z"]) * Rot(X=-90) * hole
    return part


def radial_centres(p):
    radius = p["bolt_circle_diameter"] / 2
    return [[radius * math.cos(i * math.pi / 3), radius * math.sin(i * math.pi / 3)] for i in range(6)]


def extended_geometry(recipe, p):
    if recipe == "flanged_hub":
        f, h, b, t, length = [p[k] for k in ("flange_diameter", "hub_diameter", "bore_diameter", "flange_thickness", "length")]
        return {"volume_mm3": math.pi / 4 * ((f*f-b*b)*t + (h*h-b*b)*(length-t)),
                "bounds_min_mm": [-f/2, -f/2, 0], "bounds_max_mm": [f/2, f/2, length],
                "probes": [{"name": "bore", "point_mm": [0, 0, length/2], "material": False},
                           {"name": "flange", "point_mm": [(f+h)/4, 0, t/2], "material": True},
                           {"name": "hub wall", "point_mm": [(h+b)/4, 0, (t+length)/2], "material": True},
                           {"name": "above flange", "point_mm": [(f+h)/4, 0, (t+length)/2], "material": False}]}
    if recipe == "radial_hole_plate":
        r, b, h, t = [p[k]/2 for k in ("outer_diameter", "bore_diameter", "hole_diameter", "thickness")]
        t *= 2
        probes = [{"name": "centre bore", "point_mm": [0, 0, t/2], "material": False},
                  {"name": "inner web", "point_mm": [(p["bore_diameter"] + p["bolt_circle_diameter"] - p["hole_diameter"])/4, 0, t/2], "material": True}]
        probes += [{"name": f"radial hole {i}", "point_mm": [x, y, t/2], "material": False}
                   for i, (x, y) in enumerate(radial_centres(p))]
        return {"volume_mm3": math.pi * (r*r-b*b-6*h*h)*t,
                "bounds_min_mm": [-r, -r, 0], "bounds_max_mm": [r, r, t], "probes": probes}
    w0, h0, w1, h1, length, wall = [p[k] for k in ("inlet_width", "inlet_height", "outlet_width", "outlet_height", "length", "wall")]
    probes = []
    for fraction in (.25, .75):
        w, h = w0 + fraction*(w1-w0), h0 + fraction*(h1-h0)
        for name, point, material in (("open path", [0, 0, fraction*length], False),
                                      ("X wall", [w/2-wall/2, 0, fraction*length], True),
                                      ("Y wall", [0, h/2-wall/2, fraction*length], True),
                                      ("outside", [w/2+wall, 0, fraction*length], False)):
            probes.append({"name": f"{name} at {fraction}", "point_mm": point, "material": material})
    return {"volume_mm3": length * (wall * (w0+h0+w1+h1) - 4*wall*wall),
            "bounds_min_mm": [-max(w0,w1)/2, -max(h0,h1)/2, 0],
            "bounds_max_mm": [max(w0,w1)/2, max(h0,h1)/2, length], "probes": probes}


def check_shape(part, expected):
    bounds = part.bounding_box()
    actual_min, actual_max = list(bounds.min), list(bounds.max)
    checks = {"valid_solid": bool(part.is_valid), "one_solid": len(part.solids()) == 1,
              "volume_matches": math.isclose(part.volume, expected["volume_mm3"], rel_tol=1e-7, abs_tol=1e-6),
              "bounds_match": all(math.isclose(a, b, abs_tol=1e-5) for a, b in zip(
                  actual_min + actual_max, expected["bounds_min_mm"] + expected["bounds_max_mm"]))}
    solids = part.solids()
    probes = []
    for probe in expected["probes"]:
        inside = any(s.is_inside(tuple(probe["point_mm"]), tolerance=1e-7) for s in solids)
        probes.append({**probe, "actual_material": inside, "passed": inside == probe["material"]})
    checks["material_and_hole_probes_match"] = all(p["passed"] for p in probes)
    return {"passed": all(checks.values()), "checks": checks, "volume_mm3": part.volume,
            "expected_volume_mm3": expected["volume_mm3"], "bounds_min_mm": actual_min,
            "bounds_max_mm": actual_max, "solid_count": len(solids), "probes": probes}
