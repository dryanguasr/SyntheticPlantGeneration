"""Pure checks for the morphology-derived cutting fixture, no Gazebo required."""

from copy import deepcopy
import json
import math
import unittest
import xml.etree.ElementTree as ET

from uchuva_gazebo.harvest_plants import DEFAULT_PLANT_CONFIG, build_harvest_plants
from uchuva_lsystem.collisions import build_scene_proxies
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.scene import CultivationScene


class HarvestPlantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = build_harvest_plants({})
        cls.models = {model.attrib["name"]: model for model in cls.bundle["models"]}

    def test_three_plants_and_six_independent_bodies_with_no_static_duplicate(self):
        b = self.bundle
        self.assertEqual(len(b["plants"]), 3)
        self.assertEqual(len(b["fruits"]), 6)
        self.assertEqual(len(self.models), 9)
        self.assertEqual(len({f["id"] for f in b["fruits"]}), 6)
        for fruit in b["fruits"]:
            model = self.models[fruit["model_name"]]
            self.assertEqual(model.findtext("static"), "false")
            self.assertEqual(model.find("link").attrib["name"], "fruit_link")
            self.assertIsNone(model.find("model"))
            parent = self.models[fruit["parent_model"]]
            self.assertEqual(parent.findtext("static"), "true")
            fruit_uri = model.findtext("link/visual[@name='calyx']/geometry/mesh/uri")
            self.assertNotIn(fruit_uri, [v.text for v in parent.findall(".//mesh/uri")])
        for report in b["plants"]:
            self.assertEqual(report["fruit_calyx_count"], 6)
            self.assertEqual(report["dynamic_fruit_count"], 2)
            self.assertEqual(len(report["static_visual_only_fruit_ids"]), 4)

    def test_reproduction_identity_and_units_roundtrip_to_source_interpreter(self):
        b = self.bundle
        scene = CultivationScene.from_dict(b["provenance"]["source_scene"])
        plants = {p["id"]: Plant.from_dict(p["source_morphology"]) for p in b["plants"]}
        proxies = build_scene_proxies(scene, plants)
        calyces = {p.attachment_id: p for p in proxies if p.kind == "calyx"}
        pedicels = {p.attachment_id: p for p in proxies if p.kind == "pedicel"}
        for fruit in b["fruits"]:
            proxy = calyces[fruit["id"]]
            for actual, source in zip(fruit["center_world_m"], proxy.center):
                self.assertAlmostEqual(actual, source / 8.0, places=12)
            self.assertAlmostEqual(fruit["radius_m"], max(proxy.half_extents) / 8.0)
            pedicel = pedicels[fruit["id"]]
            for i in range(3):
                expected_cut = (pedicel.start[i] + pedicel.end[i]) / 16.0
                self.assertAlmostEqual(fruit["cut_point_world_m"][i], expected_cut)
                self.assertAlmostEqual(fruit["cut_point_local_m"][i] + fruit["center_world_m"][i], expected_cut)
            self.assertIn(fruit["node_id"], fruit["unit_id"])
            self.assertEqual(fruit["pedicel_id"], fruit["unit_id"] + "_pedicel")

    def test_mass_inertia_and_meshes_are_physical_and_local(self):
        for fruit in self.bundle["fruits"]:
            model = self.models[fruit["model_name"]]
            mass = float(model.findtext("link/inertial/mass"))
            moments = [float(model.findtext("link/inertial/inertia/" + name)) for name in ("ixx", "iyy", "izz")]
            self.assertGreater(mass, 0)
            self.assertGreater(min(moments), 0)
            self.assertLessEqual(max(moments), sum(moments) - max(moments))
            self.assertAlmostEqual(moments[0], 0.4 * mass * fruit["radius_m"] ** 2)
            uri = model.findtext("link/visual[@name='calyx']/geometry/mesh/uri")
            vertices = [tuple(map(float, line.split()[1:])) for line in self.bundle["meshes"][uri].splitlines() if line.startswith("v ")]
            self.assertLessEqual(max(math.sqrt(sum(x * x for x in v)) for v in vertices), fruit["radius_m"] + 1e-9)
            self.assertGreater(fruit["minimum_initial_clearance_m"], 0)
            self.assertGreater(fruit["center_world_m"][2] - fruit["radius_m"], 0)
        referenced = {e.text for model in self.bundle["models"] for e in model.findall(".//mesh/uri")}
        self.assertEqual(referenced, set(self.bundle["meshes"]))

    def test_exported_xml_colliders_have_no_initial_dynamic_penetration(self):
        # Reconstruct the actual SDF cylinders independently of the exporter's
        # proxy selection: a wrong local/world frame or uncut pedicel fails here.
        cylinders = []
        for model in self.models.values():
            if model.findtext("static") != "true":
                continue
            origin = list(map(float, model.findtext("pose").split()))[:3]
            for collision in model.findall("link/collision"):
                pose = list(map(float, collision.findtext("pose").split()))
                radius = float(collision.findtext("geometry/cylinder/radius"))
                half_length = float(collision.findtext("geometry/cylinder/length")) / 2
                pitch, yaw = pose[4:6]
                direction = (math.cos(yaw) * math.sin(pitch), math.sin(yaw) * math.sin(pitch), math.cos(pitch))
                center = [origin[i] + pose[i] for i in range(3)]
                a = [center[i] - half_length * direction[i] for i in range(3)]
                b = [center[i] + half_length * direction[i] for i in range(3)]
                cylinders.append((a, b, radius))
        for fruit in self.bundle["fruits"]:
            model = self.models[fruit["model_name"]]
            center = list(map(float, model.findtext("pose").split()))[:3]
            radius = float(model.findtext("link/collision/geometry/sphere/radius"))
            for a, b, cylinder_radius in cylinders:
                direction = [b[i] - a[i] for i in range(3)]
                t = sum((center[i] - a[i]) * direction[i] for i in range(3)) / sum(v * v for v in direction)
                closest = [a[i] + max(0, min(1, t)) * direction[i] for i in range(3)]
                self.assertGreaterEqual(math.dist(center, closest) - radius - cylinder_radius, DEFAULT_PLANT_CONFIG["clearance_m"] - 1e-7)
            # The distal stalk's local proximal endpoint must still match the
            # declared cut point; it belongs to the released fruit body.
            pose = list(map(float, model.findtext("link/visual[@name='distal_pedicel']/pose").split()))
            length = float(model.findtext("link/visual[@name='distal_pedicel']/geometry/cylinder/length"))
            pitch, yaw = pose[4:6]
            direction = (math.cos(yaw) * math.sin(pitch), math.sin(yaw) * math.sin(pitch), math.cos(pitch))
            for i in range(3):
                self.assertAlmostEqual(center[i] + pose[i] - length * direction[i] / 2, fruit["cut_point_world_m"][i], places=7)

    def test_deterministic_and_caller_config_not_mutated(self):
        config = deepcopy(DEFAULT_PLANT_CONFIG)
        before = deepcopy(config)
        b = build_harvest_plants(config)
        self.assertEqual(config, before)
        for key in ("meshes", "fruits", "plants", "provenance"):
            self.assertEqual(b[key], self.bundle[key])
        self.assertEqual([ET.tostring(m) for m in b["models"]], [ET.tostring(m) for m in self.bundle["models"]])
        json.dumps({k: v for k, v in b.items() if k != "models"}, allow_nan=False)

    def test_instance_translation_is_applied_once(self):
        config = deepcopy(DEFAULT_PLANT_CONFIG)
        config["positions_m"] = [[x + 3.0, y + 5.0, z] for x, y, z in config["positions_m"]]
        shifted = build_harvest_plants(config)
        old = {f["id"]: f for f in self.bundle["fruits"]}
        for fruit in shifted["fruits"]:
            self.assertEqual(fruit["id"], old[fruit["id"]]["id"])
            for i, delta in enumerate((3.0, 5.0, 0.0)):
                self.assertAlmostEqual(fruit["center_world_m"][i], old[fruit["id"]]["center_world_m"][i] + delta)
                self.assertAlmostEqual(fruit["cut_point_local_m"][i], old[fruit["id"]]["cut_point_local_m"][i])

    def test_rejects_bad_config_and_unreachable_target_count(self):
        for update in ({"fruit_mass_kg": -1}, {"fruit_mass_kg": float("nan")}, {"cut_fraction": 0}, {"clearance_m": -1}, {"unknown": 1}, {"phenology_model": "literature_cohort_v1"}, {"max_dynamic_fruits_per_plant": 6}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                build_harvest_plants(update)
        with self.assertRaises(ValueError):
            build_harvest_plants({"positions_m": [[0, 0, 0]]})


if __name__ == "__main__":
    unittest.main()
