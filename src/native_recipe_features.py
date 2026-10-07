"""Compile bounded recipes to ordinary Onshape variables/sketches/extrudes.

No custom FeatureScript programs, evaluation requests or network client. Query strings
are the standard query serialization used inside native feature definitions.
"""
import json
import math

import part_recipes as recipes


def string(key, value):
    return {"btType": "BTMParameterString-149", "parameterId": key, "value": value}


def quantity(key, expression):
    return {"btType": "BTMParameterQuantity-147", "parameterId": key, "expression": expression, "isInteger": False}


def enum(key, name, value):
    return {"btType": "BTMParameterEnum-145", "parameterId": key, "enumName": name, "value": value}


def boolean(key, value):
    return {"btType": "BTMParameterBoolean-144", "parameterId": key, "value": value}


def query(key, expression, **extra):
    return {"btType": "BTMParameterQueryList-148", "parameterId": key,
            "queries": [{"btType": "BTMIndividualQuery-138", "queryString": expression,
                         "deterministicIds": [], **extra}]}


def created_by(feature_id, entity_type):
    return 'query = qCreatedBy(id + ' + json.dumps(feature_id) + ', EntityType.' + entity_type + ');'


def feature(kind, name, parameters, **extra):
    return {"btType": "BTMSketch-151" if kind == "newSketch" else "BTMFeature-134",
            "featureType": kind, "name": name, "namespace": "", "suppressed": False,
            "parameters": parameters, **extra}


def variable(name, value, title):
    return feature("assignVariable", title, [enum("mode", "VariableMode", "ASSIGNED"),
        enum("variableType", "VariableType", "LENGTH"), string("name", name), quantity("lengthValue", f"{value:g} mm")])


def constraint(kind, name, parameters):
    return {"btType": "BTMSketchConstraint-2", "constraintType": kind, "entityId": name,
            "namespace": "", "name": "", "parameters": parameters, "index": 1,
            "hasOffsetData1": False, "offsetOrientation1": False, "offsetDistance1": 0,
            "hasOffsetData2": False, "offsetOrientation2": False, "offsetDistance2": 0,
            "hasPierceParameter": False, "pierceParameter": 0, "helpParameters": []}


def line(name, start, end, construction=False):
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if not length:
        raise ValueError("Native profile cannot contain a zero-length line")
    return {"btType": "BTMSketchCurveSegment-155", "entityId": name, "startPointId": name + ".start",
            "endPointId": name + ".end", "startParam": 0, "endParam": length / 1000,
            "geometry": {"btType": "BTCurveGeometryLine-117", "pntX": start[0] / 1000,
                         "pntY": start[1] / 1000, "dirX": dx / length, "dirY": dy / length},
            "isConstruction": construction, "isFromSplineControlPolygon": False,
            "namespace": "", "name": "", "index": 1, "parameters": []}


def datum():
    entities = [line("datumX", [-600, 0], [600, 0], True), line("datumY", [0, -600], [0, 600], True)]
    constraints = [constraint("FIX", "fix" + entity["entityId"] + end,
                              [string("localFirst", entity[end + "PointId"])])
                   for entity in entities for end in ("start", "end")]
    return entities, constraints


def position_constraints(point, xy, expressions):
    result = []
    for axis, value, expression in zip(("x", "y"), xy, expressions):
        datum_name = "datumY" if axis == "x" else "datumX"
        name = point + axis
        if value == 0:
            result.append(constraint("COINCIDENT", name, [string("localFirst", point), string("localSecond", datum_name)]))
        else:
            positive_half = "RIGHT" if axis == "x" else "LEFT"
            half = positive_half if value > 0 else ("LEFT" if positive_half == "RIGHT" else "RIGHT")
            result.append(constraint("DISTANCE", name, [string("localFirst", datum_name), string("localSecond", point),
                enum("direction", "DimensionDirection", "MINIMUM"), quantity("length", expression),
                enum("halfSpace0", "DimensionHalfSpace", half), quantity("labelRatio", "0.5"),
                quantity("labelDistance", "5 mm")]))
    return result


def polygon(points, expressions):
    entities, constraints = datum()
    for i, point in enumerate(points):
        name = "edge" + str(i)
        entities.append(line(name, point, points[(i + 1) % len(points)]))
        constraints.extend(position_constraints(name + ".start", point, expressions[i]))
        constraints.append(constraint("COINCIDENT", "join" + str(i),
            [string("localFirst", name + ".end"), string("localSecond", "edge" + str((i + 1) % len(points)) + ".start")]))
    return entities, constraints


def circles(centres, coordinate_expressions, diameter, diameter_expression):
    entities, constraints = datum()
    for i, (centre, expressions) in enumerate(zip(centres, coordinate_expressions)):
        name = "circle" + str(i)
        entities.append({"btType": "BTMSketchCurve-4", "entityId": name, "centerId": name + ".center",
            "geometry": {"btType": "BTCurveGeometryCircle-115", "radius": diameter[i] / 2000,
                         "xCenter": centre[0] / 1000, "yCenter": centre[1] / 1000,
                         "clockwise": False, "xDir": 1, "yDir": 0},
            "isConstruction": False, "namespace": "", "name": "", "index": i + 1, "parameters": []})
        constraints.extend(position_constraints(name + ".center", centre, expressions))
        constraints.append(constraint("DIAMETER", name + "diameter", [string("localFirst", name),
            quantity("length", diameter_expression[i]), quantity("labelRatio", "1.5"), quantity("labelAngle", "0 rad")]))
    return entities, constraints


def sketch(name, plane_id, geometry):
    entities, constraints = geometry
    return feature("newSketch", name, [query("sketchPlane", created_by(plane_id, "FACE")),
            boolean("disableImprinting", True)], entities=entities, constraints=constraints)


def extrude(name, sketch_id, depth, operation="NEW", body_id=None, opposite=False):
    region = {"btType": "BTMParameterQueryList-148", "parameterId": "entities", "queries": [{
        "btType": "BTMIndividualSketchRegionQuery-140", "featureId": sketch_id,
        "filterInnerLoops": True, "deterministicIds": [],
        "queryString": 'query = qSketchRegion(id + ' + json.dumps(sketch_id) + ', true);'}]}
    parameters = [region, enum("operationType", "NewBodyOperationType", operation),
                  enum("bodyType", "ExtendedToolBodyType", "SOLID"), enum("endBound", "BoundingType", "BLIND"),
                  quantity("depth", depth), boolean("oppositeDirection", opposite),
                  boolean("symmetric", False), boolean("hasSecondDirection", False)]
    if operation != "NEW":
        parameters += [boolean("defaultScope", False), query("booleanScope", created_by(body_id, "BODY"))]
    return feature("extrude", name, parameters)


def operations(recipe, parameters):
    p = recipes.normalize(recipe, parameters)
    result = [{"role": "var:" + name, "kind": "variable", "parameter": name} for name in p]
    if recipe == "spacer":
        result += [{"role": "profile", "kind": "sketch", "shape": "annulus", "plane": "Top"},
                   {"role": "solid", "kind": "extrude", "sketch": "profile", "depth": "length", "operation": "NEW"}]
    elif recipe == "hole_pattern_plate":
        result += [{"role": "profile", "kind": "sketch", "shape": "plate", "plane": "Top"},
                   {"role": "solid", "kind": "extrude", "sketch": "profile", "depth": "thickness", "operation": "NEW"},
                   {"role": "holes", "kind": "sketch", "shape": "plate_holes", "plane": "Top"},
                   {"role": "holes_cut", "kind": "extrude", "sketch": "holes", "depth": "thickness", "operation": "REMOVE"}]
    else:
        result += [{"role": "base_profile", "kind": "sketch", "shape": "base", "plane": "Top"},
                   {"role": "solid", "kind": "extrude", "sketch": "base_profile", "depth": "thickness", "operation": "NEW"},
                   {"role": "wall_profile", "kind": "sketch", "shape": "wall", "plane": "Top"},
                   {"role": "wall_solid", "kind": "extrude", "sketch": "wall_profile", "depth": "height", "operation": "ADD"},
                   {"role": "base_holes", "kind": "sketch", "shape": "base_holes", "plane": "Top"},
                   {"role": "base_cut", "kind": "extrude", "sketch": "base_holes", "depth": "thickness", "operation": "REMOVE"},
                   {"role": "wall_holes", "kind": "sketch", "shape": "wall_holes", "plane": "Front"},
                   {"role": "wall_cut", "kind": "extrude", "sketch": "wall_holes", "depth": "thickness", "operation": "REMOVE", "opposite": True}]
    return result


def compile_step(operation, recipe, p, variable_names, feature_ids, planes, prefix):
    name = prefix + " | " + operation["role"]
    v = {key: "#" + value for key, value in variable_names.items()}
    if operation["kind"] == "variable":
        key = operation["parameter"]
        return variable(variable_names[key], p[key], name)
    if operation["kind"] == "extrude":
        return extrude(name, feature_ids[operation["sketch"]], v[operation["depth"]], operation["operation"],
                       feature_ids.get("solid"), operation.get("opposite", False))
    shape = operation["shape"]
    if shape == "annulus":
        geometry = circles([[0, 0], [0, 0]], [["0 mm", "0 mm"]] * 2,
                           [p["outer_diameter"], p["bore_diameter"]], [v["outer_diameter"], v["bore_diameter"]])
    elif shape in ("plate", "base", "wall"):
        w, d = p["width"], p["depth"] if shape == "plate" else p["base_depth"] if shape == "base" else p["thickness"]
        wd, dd = v["width"], v["depth"] if shape == "plate" else v["base_depth"] if shape == "base" else v["thickness"]
        ymin, ymax = (-d / 2, d / 2) if shape == "plate" else (0, d)
        dymin, dymax = (dd + "/2", dd + "/2") if shape == "plate" else ("0 mm", dd)
        geometry = polygon([[-w / 2, ymin], [w / 2, ymin], [w / 2, ymax], [-w / 2, ymax]],
                           [[wd + "/2", dymin], [wd + "/2", dymin], [wd + "/2", dymax], [wd + "/2", dymax]])
    else:
        if shape == "plate_holes":
            centres = [[sx * p["pitch_x"] / 2, sy * p["pitch_y"] / 2] for sx in (-1, 1) for sy in (-1, 1)]
            expressions = [[v["pitch_x"] + "/2", v["pitch_y"] + "/2"]] * 4
        else:
            ykey = "base_hole_y" if shape == "base_holes" else "wall_hole_z"
            centres = [[sx * p["hole_pitch_x"] / 2, p[ykey]] for sx in (-1, 1)]
            expressions = [[v["hole_pitch_x"] + "/2", v[ykey]]] * 2
        geometry = circles(centres, expressions, [p["hole_diameter"]] * len(centres), [v["hole_diameter"]] * len(centres))
    return sketch(name, planes[operation["plane"]], geometry)
