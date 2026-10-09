"""Check independently expected geometry and the bounded recipe/native handoff contract."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import part_recipes as recipes

BASE = Path(__file__).resolve().parent
VARIANTS = {
    "spacer": {"length": 18},
    "mounting_bracket": {"width": 36, "hole_pitch_x": 24, "height": 36, "wall_hole_z": 24},
    "hole_pattern_plate": {"pitch_x": 50, "pitch_y": 25},
    "flanged_hub": {"hub_diameter": 28, "length": 30},
    "radial_hole_plate": {"bolt_circle_diameter": 50, "thickness": 6},
    "lofted_guide": {"outlet_width": 45, "length": 80, "wall": 4},
}


class RecipeContractTests(unittest.TestCase):
    def test_unknown_recipe_and_parameters(self):
        for recipe, p in (("arbitrary_code", {}), ("spacer", {"python": "code"}), ("spacer", [])):
            with self.subTest(recipe=recipe, parameters=p), self.assertRaises(ValueError):
                recipes.normalize(recipe, p)

    def test_dimensions_reject_nonfinite_boolean_and_out_of_range(self):
        for value in (True, "12", float("nan"), float("inf"), 0, -1, 501):
            with self.subTest(value=value), self.assertRaises(ValueError):
                recipes.normalize("spacer", {"length": value})

    def test_geometric_web_and_corner_guards(self):
        for recipe, p in (("spacer", {"bore_diameter": 19}),
                          ("hole_pattern_plate", {"pitch_x": 79}),
                          ("hole_pattern_plate", {"pitch_y": 4.5}),
                          ("mounting_bracket", {"base_hole_y": 4}),
                          ("mounting_bracket", {"wall_hole_z": 29}),
                          ("mounting_bracket", {"height": 9}),
                          ("mounting_bracket", {"hole_pitch_x": 29})):
            with self.subTest(recipe=recipe, parameters=p), self.assertRaises(ValueError):
                recipes.normalize(recipe, p)

    def test_parameter_changes_carry_into_native_instructions(self):
        for recipe, p in VARIANTS.items():
            values = recipes.normalize(recipe, p)
            plan = recipes.native_plan(recipe, values)
            with self.subTest(recipe=recipe):
                self.assertEqual(plan["parameters_mm"], values)
                self.assertEqual(plan["plan_kind"], "native-construction-instructions")
                self.assertEqual(len(plan["named_length_variables"]), len(values))
                self.assertFalse(plan["api_payloads_prepared"])
                self.assertFalse(plan["native_regeneration_verified"])
        plate = recipes.native_plan("hole_pattern_plate", recipes.normalize("hole_pattern_plate", VARIANTS["hole_pattern_plate"]))
        self.assertEqual(plate["steps"][2]["geometry"]["centres_mm"],
                         [[-25, -12.5], [-25, 12.5], [25, -12.5], [25, 12.5]])

    def test_worker_blocks_real_python_socket_operations(self):
        # Local DNS/bind attempts are rejected by the hook before OS socket activity.
        code = '''import socket, sys
from recipe_worker import no_network
sys.addaudithook(no_network)
for operation in (lambda: socket.getaddrinfo("localhost", 80), lambda: socket.socket().bind(("127.0.0.1", 0))):
    try:
        operation()
    except PermissionError:
        continue
    raise AssertionError("Worker allowed socket activity")
print("blocked")
'''
        result = subprocess.run([sys.executable, "-c", code], cwd=BASE, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "blocked")


@unittest.skipUnless(importlib.util.find_spec("build123d"), "Run with .venv-build123d for geometry checks")
class GeometryTests(unittest.TestCase):
    def assert_geometry(self, recipe, supplied):
        p = recipes.normalize(recipe, supplied)
        shape = recipes.build_shape(recipe, p)
        result = recipes.check_shape(shape, recipes.expected_geometry(recipe, p))
        self.assertTrue(result["passed"], json.dumps(result))
        return shape, p

    def test_default_solids_and_voids(self):
        for recipe in recipes.RECIPES:
            with self.subTest(recipe=recipe):
                self.assert_geometry(recipe, {})

    def test_changed_parameters(self):
        for recipe, values in VARIANTS.items():
            with self.subTest(recipe=recipe):
                self.assert_geometry(recipe, values)

    def test_thick_bracket_keeps_open_interior(self):
        self.assert_geometry("mounting_bracket", {"thickness": 20, "base_depth": 40, "height": 40,
                                                 "base_hole_y": 30, "wall_hole_z": 30})

    def test_step_roundtrip_preserves_default_and_changed_geometry(self):
        from build123d import export_step, import_step
        root = BASE / ".test-runs"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="FEASIBILITY-recipes-", dir=root) as folder:
            for recipe in recipes.RECIPES:
                for case, values in (("default", {}), ("changed", VARIANTS[recipe])):
                    with self.subTest(recipe=recipe, case=case):
                        shape, p = self.assert_geometry(recipe, values)
                        path = Path(folder) / f"{recipe}-{case}.step"
                        self.assertTrue(export_step(shape, str(path)))
                        imported = import_step(str(path))
                        self.assertTrue(recipes.check_shape(imported, recipes.expected_geometry(recipe, p))["passed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
