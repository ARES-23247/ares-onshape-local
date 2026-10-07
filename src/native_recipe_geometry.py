"""Analytic surface checks for the three bounded native recipe families (no CAD engine)."""
import math

import part_recipes as recipes


def vector(value):
    result = [value[a] for a in "xyz"]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in result):
        raise ValueError("Native geometry contains invalid coordinates")
    return result


def close(a, b):
    return math.isclose(a, b, abs_tol=1e-7, rel_tol=1e-6)


def expected_faces(recipe, p):
    result = []
    def plane(axis, lo, hi, area):
        result.append({"type": "PLANE", "axis": axis, "min": lo, "max": hi, "area": area})
    def cylinder(axis, centre, radius, length, outer=False):
        lo = [c - radius for c in centre]
        hi = [c + radius for c in centre]
        lo[axis], hi[axis] = centre[axis], centre[axis] + length
        result.append({"type": "CYLINDER", "axis": axis, "min": lo, "max": hi,
                       "radius": radius, "area": 2 * math.pi * radius * length, "outer": outer})
    if recipe == "spacer":
        r, bore, length = p["outer_diameter"] / 2000, p["bore_diameter"] / 2000, p["length"] / 1000
        cylinder(2, [0, 0, 0], r, length, True)
        cylinder(2, [0, 0, 0], bore, length)
        for z in (0, length):
            plane(2, [-r, -r, z], [r, r, z], math.pi * (r*r - bore*bore))
    elif recipe == "hole_pattern_plate":
        w, d, t, r = [p[k] / 1000 for k in ("width", "depth", "thickness", "hole_diameter")]
        r /= 2
        for z in (0, t):
            plane(2, [-w/2, -d/2, z], [w/2, d/2, z], w*d - 4*math.pi*r*r)
        for x in (-w/2, w/2):
            plane(0, [x, -d/2, 0], [x, d/2, t], d*t)
        for y in (-d/2, d/2):
            plane(1, [-w/2, y, 0], [w/2, y, t], w*t)
        for sx in (-1, 1):
            for sy in (-1, 1):
                cylinder(2, [sx*p["pitch_x"]/2000, sy*p["pitch_y"]/2000, 0], r, t)
    else:
        w, d, h, t, r = [p[k] / 1000 for k in ("width", "base_depth", "height", "thickness", "hole_diameter")]
        r /= 2
        plane(2, [-w/2, 0, 0], [w/2, d, 0], w*d - 2*math.pi*r*r)
        plane(2, [-w/2, t, t], [w/2, d, t], w*(d-t) - 2*math.pi*r*r)
        plane(2, [-w/2, 0, h], [w/2, t, h], w*t)
        plane(1, [-w/2, 0, 0], [w/2, 0, h], w*h - 2*math.pi*r*r)
        plane(1, [-w/2, t, t], [w/2, t, h], w*(h-t) - 2*math.pi*r*r)
        plane(1, [-w/2, d, 0], [w/2, d, t], w*t)
        for x in (-w/2, w/2):
            plane(0, [x, 0, 0], [x, d, h], t*(d+h-t))
        for sx in (-1, 1):
            cylinder(2, [sx*p["hole_pitch_x"]/2000, p["base_hole_y"]/1000, 0], r, t)
            cylinder(1, [sx*p["hole_pitch_x"]/2000, 0, p["wall_hole_z"]/1000], r, t)
    return result


def check_brep(recipe, parameters_mm, response):
    p = recipes.normalize(recipe, parameters_mm)
    if response.get("errorEnum") != "NO_ERROR":
        raise ValueError("Native body details contain an error")
    solids = [b for b in response.get("bodies", []) if b.get("type") == "SOLID"]
    if len(solids) != 1:
        raise ValueError("Native recipe requires exactly one solid")
    expected = expected_faces(recipe, p)
    faces = solids[0]["faces"]
    if len(faces) != len(expected):
        raise ValueError("Native face count differs from the recipe")
    remaining = list(faces)
    matches = []
    for wanted in expected:
        found = []
        for face in remaining:
            surface = face.get("surface", {})
            if surface.get("type") != wanted["type"] or not math.isclose(face["area"], wanted["area"], abs_tol=1e-12, rel_tol=1e-6):
                continue
            lo, hi = vector(face["box"]["minCorner"]), vector(face["box"]["maxCorner"])
            if not all(close(a, b) for a, b in zip(lo + hi, wanted["min"] + wanted["max"])):
                continue
            direction = vector(surface["axis"] if wanted["type"] == "CYLINDER" else surface["normal"])
            if not close(abs(direction[wanted["axis"]]), 1):
                continue
            if wanted["type"] == "CYLINDER":
                if not close(surface["radius"], wanted["radius"]) or face.get("orientation") != wanted["outer"]:
                    continue
                origin = vector(surface["origin"])
                if any(not close(origin[i], (lo[i]+hi[i])/2) for i in range(3) if i != wanted["axis"]):
                    continue
            found.append(face)
        if len(found) != 1:
            raise ValueError("Native plane/cylinder bounds, area, axis or hole location differs from the recipe")
        remaining.remove(found[0])
        matches.append({"face_id": found[0]["id"], "type": wanted["type"], "area_m2": found[0]["area"]})
    expected_volume = recipes.expected_geometry(recipe, p)["volume_mm3"]
    return {"passed": True, "solid_id": solids[0]["id"], "face_count": len(faces), "faces": matches,
            "expected_volume_mm3": expected_volume,
            "scope": "Actual native plane/cylinder surfaces, face areas, bounds, axes and inner/outer orientation; no physical fit or load validation"}
