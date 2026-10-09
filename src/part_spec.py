"""Portable, bounded part definitions; these are recipes, not native CAD files."""
import hashlib
import json
import re

import part_recipes as recipes


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def make(recipe, parameters_mm, label="", design="shared"):
    if not isinstance(recipe, str):
        raise ValueError("Choose a listed bounded recipe name")
    if not isinstance(label, str) or len(label) > 80 or (label and not re.fullmatch(r"[A-Za-z0-9 _.-]+", label)):
        raise ValueError("Use an ASCII part label up to 80 characters")
    if not isinstance(design, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", design):
        raise ValueError("Use a configured design name or shared")
    return {"schema_version": 1, "kind": "ares-part-definition", "recipe": recipe,
            "parameters_mm": recipes.normalize(recipe, parameters_mm), "units": "mm",
            "label": label or "ARES " + recipe, "design": design,
            "datum": recipes.RECIPES[recipe]["datum"]}


def validate(value):
    if not isinstance(value, dict):
        raise ValueError("Expected an ARES part-definition object")
    expected = make(value.get("recipe"), value.get("parameters_mm"), value.get("label", ""), value.get("design", "shared"))
    if value != expected:
        raise ValueError("Part definition schema, units, datum or fields differ from the bounded recipe")
    return expected
