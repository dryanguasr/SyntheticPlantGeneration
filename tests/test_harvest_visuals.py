"""Visual topology, source-pose and packaged-material checks, without Blender."""

from collections import Counter
from copy import deepcopy
import math
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
import xml.etree.ElementTree as ET
import zlib

from uchuva_gazebo.harvest_visuals import (
    apply_plant_material,
    apply_soil_material,
    cylinder_batch_mesh,
    detailed_calyx_mesh,
    detailed_leaf_mesh,
    merge_obj_meshes,
    plant_texture_preset,
    procedural_soil_assets,
    texture_asset_paths,
)
from uchuva_lsystem.blender_geometry import _leaf_shape_profile


def parse_obj(content):
    data = {"v": [], "vt": [], "vn": [], "f": []}
    for line in content.splitlines():
        fields = line.split()
        if fields and fields[0] in data:
            data[fields[0]].append([tuple(map(int, part.split("/"))) for part in fields[1:]]
                                  if fields[0] == "f" else tuple(map(float, fields[1:])))
    return data


def leaf_slabs():
    result = []
    for index, (t, width_factor) in enumerate(((0.24, 0.50), (0.53, 0.62), (0.81, 0.42))):
        tangent_length = math.hypot(1, 0.2 * t)
        result.append(SimpleNamespace(
            proxy_id=f"plant:leaf:blade_{index}", attachment_id="plant:leaf",
            center=(8 * t, 8.0, 2.0 - 0.8 * t * t),
            axes=((1 / tangent_length, 0, -0.2 * t / tangent_length), (0, 1, 0),
                  (0.2 * t / tangent_length, 0, 1 / tangent_length)),
            half_extents=(8 * 0.17, 4 * width_factor, 0.0055),
        ))
    return result


class HarvestVisualTests(unittest.TestCase):
    def setUp(self):
        self.calyx = SimpleNamespace(
            center=(7, 8, 9), half_extents=(0.4, 0.25, 0.25),
            axes=((0, 0, -1), (1, 0, 0), (0, -1, 0)),
        )

    def assert_valid_obj(self, mesh):
        self.assertTrue(mesh["f"])
        for kind in ("v", "vt", "vn"):
            self.assertTrue(all(math.isfinite(x) for item in mesh[kind] for x in item))
        for normal in mesh["vn"]:
            self.assertAlmostEqual(sum(x * x for x in normal), 1.0, places=7)
        for uv in mesh["vt"]:
            self.assertTrue(all(0 <= x <= 1 for x in uv))
        for face in mesh["f"]:
            self.assertEqual(len(face), 3)
            for p, uv, n in face:
                self.assertTrue(1 <= p <= len(mesh["v"]))
                self.assertTrue(1 <= uv <= len(mesh["vt"]))
                self.assertTrue(1 <= n <= len(mesh["vn"]))
            a, b, c = (mesh["v"][index[0] - 1] for index in face)
            ab, ac = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
            cross = (ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0])
            self.assertGreater(sum(x * x for x in cross), 1e-24)

    def test_three_slabs_make_one_continuous_curved_leaf(self):
        source = leaf_slabs()
        before = deepcopy(source)
        mesh = parse_obj(detailed_leaf_mesh(source, (0, 1, 0)))
        self.assert_valid_obj(mesh)
        self.assertEqual(len(mesh["v"]), 77)
        self.assertEqual(len(mesh["f"]), 240)
        self.assertEqual(source, before)
        for actual, expected in zip(mesh["v"][0], (0, 0, 0.25)):
            self.assertAlmostEqual(actual, expected, places=9)
        for actual, expected in zip(mesh["v"][-1], (1, 0, 0.15)):
            self.assertAlmostEqual(actual, expected, places=9)
        # The middle follows sag, rather than a straight chord or three diamonds.
        center = mesh["v"][1 + 7 * 5 + 2]
        self.assertAlmostEqual(center[0], 0.5)
        self.assertGreater(center[2], 0.22)

    def test_leaf_backs_reverse_winding_and_normals(self):
        mesh = parse_obj(detailed_leaf_mesh(leaf_slabs(), (0, 0, 0)))
        for front, back in zip(mesh["f"][::2], mesh["f"][1::2]):
            self.assertEqual([item[:2] for item in front], list(reversed([item[:2] for item in back])))
            for f, b in zip(front, reversed(back)):
                for n1, n2 in zip(mesh["vn"][f[2] - 1], mesh["vn"][b[2] - 1]):
                    self.assertAlmostEqual(n1, -n2)

    def test_leaf_outline_follows_each_source_shape_without_rescaling(self):
        source = leaf_slabs()
        widths = {}
        for shape in ("ovate", "deltoid_ovate", "ovate_cordate"):
            mesh = parse_obj(detailed_leaf_mesh(source, (0, 1, 0), leaf_shapes={"plant:leaf": shape}))
            self.assert_valid_obj(mesh)
            for row in range(1, 16):
                profile, lobes = _leaf_shape_profile(shape, row / 16)
                expected = min(4 * 0.62, 4 * 0.5 * profile * lobes) / 8
                left, right = mesh["v"][1 + (row - 1) * 5], mesh["v"][5 + (row - 1) * 5]
                self.assertAlmostEqual(left[1], -expected, places=9)
                self.assertAlmostEqual(right[1], expected, places=9)
            widths[shape] = mesh["v"][10][1]
            self.assertEqual(mesh["v"][0], (0, 0, 0.25))
            self.assertEqual(mesh["v"][-1], (1, 0, 0.15))
        self.assertEqual(len(set(widths.values())), 3)

    def test_missing_shape_entries_preserve_ovate_compatibility(self):
        expected = detailed_leaf_mesh(leaf_slabs(), (0, 0, 0))
        self.assertEqual(expected, detailed_leaf_mesh(leaf_slabs(), (0, 0, 0), leaf_shapes={}))
        self.assertEqual(expected, detailed_leaf_mesh(leaf_slabs(), (0, 0, 0), leaf_shapes={"unrelated:leaf": "ovate_cordate"}))

    def test_calyx_stays_in_original_ellipsoid_and_is_closed(self):
        mesh = parse_obj(detailed_calyx_mesh(self.calyx))
        self.assert_valid_obj(mesh)
        edges = Counter()
        for point in mesh["v"]:
            local = [sum(point[i] * axis[i] for i in range(3)) for axis in self.calyx.axes]
            self.assertLessEqual(sum((local[i] / (self.calyx.half_extents[i] / 8)) ** 2 for i in range(3)), 1.00000001)
        for face in mesh["f"]:
            points = [tuple(round(x, 9) for x in mesh["v"][index[0] - 1]) for index in face]
            edges.update(tuple(sorted((points[i], points[(i + 1) % 3]))) for i in range(3))
        self.assertEqual(set(edges.values()), {2})
        # Split UV seam has identical normals; no dark crease between u=0 and u=1.
        for ring in range(15):
            self.assertEqual(mesh["vn"][1 + ring * 41], mesh["vn"][1 + ring * 41 + 40])

    def test_calyx_has_five_structural_ribs(self):
        mesh = parse_obj(detailed_calyx_mesh(self.calyx))
        center_ring = mesh["v"][1 + 7 * 41:1 + 8 * 41]
        radii = [math.hypot(point[0], point[1]) for point in center_ring[:-1]]
        crests = sum(radii[i] > radii[(i - 1) % 40] and radii[i] > radii[(i + 1) % 40] for i in range(40))
        self.assertEqual(crests, 5)

    def test_batching_translates_positions_and_preserves_indices(self):
        content = detailed_calyx_mesh(self.calyx)
        source = parse_obj(content)
        merged = parse_obj(merge_obj_meshes(((content, (0, 0, 0)), (content, (1, 2, 3)))))
        self.assert_valid_obj(merged)
        self.assertEqual(len(merged["f"]), 2 * len(source["f"]))
        for original, translated in zip(source["v"], merged["v"][len(source["v"]):]):
            for i in range(3):
                self.assertAlmostEqual(translated[i], original[i] + i + 1)
        self.assertEqual(merged["vn"], 2 * source["vn"])

    def test_cylinder_batch_preserves_endpoints_radii_and_cap_normals(self):
        mesh = parse_obj(cylinder_batch_mesh((((0, 0, 0), (0, 0, 1), 0.02),)))
        self.assert_valid_obj(mesh)
        self.assertEqual(len(mesh["f"]), 48)
        self.assertEqual({v[2] for v in mesh["v"]}, {0.0, 1.0})
        self.assertAlmostEqual(max(math.hypot(v[0], v[1]) for v in mesh["v"]), 0.02)
        self.assertIn((0, 0, -1), mesh["vn"])
        self.assertIn((0, 0, 1), mesh["vn"])

    def test_material_only_changes_visual_material_and_uses_current_pngs(self):
        visual = ET.fromstring('<visual name="leaf"><geometry><mesh><uri>meshes/leaves.obj</uri></mesh></geometry><material><diffuse>0 0 0 1</diffuse></material></visual>')
        geometry = ET.tostring(visual.find("geometry"))
        name = apply_plant_material(visual, "calyx", "straw_yellow", 1)
        self.assertEqual(name, "calyx_straw_v1")
        self.assertEqual(len(visual.findall("material")), 1)
        self.assertEqual(geometry, ET.tostring(visual.find("geometry")))
        paths = texture_asset_paths([name])
        repo = Path(__file__).resolve().parents[1]
        for node in visual.findall("material/pbr/metal/*"):
            if node.tag.endswith("_map"):
                self.assertIn(node.text, paths)
                self.assertTrue((repo / paths[node.text]).is_file())
        self.assertEqual(visual.find("material/pbr/metal/normal_map").get("type"), "tangent")

    def test_all_material_states_are_available_without_maturity_inference(self):
        names = [plant_texture_preset("calyx", state, variant) for state in
                 ("inflated_green", "transitioning_yellow", "straw_yellow", "dry_deteriorated") for variant in range(4)]
        names.extend((plant_texture_preset("leaf"), plant_texture_preset("leaf", "senescent")))
        repo = Path(__file__).resolve().parents[1]
        self.assertTrue(all((repo / path).is_file() for path in texture_asset_paths(names).values()))

    def test_malformed_leaf_contract_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "three morphology leaf slabs"):
            detailed_leaf_mesh(leaf_slabs()[:1], (0, 0, 0))


class HarvestVisualIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from uchuva_gazebo.harvest_plants import build_harvest_plants
        cls.bundle = build_harvest_plants({})
        cls.models = {model.get("name"): model for model in cls.bundle["models"]}

    def test_static_plant_draw_calls_are_batched_without_losing_organs(self):
        for report in self.bundle["plants"]:
            model = self.models[report["model_name"]]
            self.assertIsNotNone(model.find("link/visual[@name='stems_visual']/geometry/mesh"))
            self.assertIsNotNone(model.find("link/visual[@name='leaves_visual_only']/geometry/mesh"))
            self.assertEqual(len(model.findall("link/visual")), 2 + len(report["static_calyx_material_batches"]))
            self.assertEqual(sum(report["static_calyx_material_batches"].values()),
                             len(report["static_visual_only_fruit_ids"]))
            self.assertLessEqual(len(report["static_calyx_material_batches"]), 4)
            leaves_uri = model.findtext("link/visual[@name='leaves_visual_only']/geometry/mesh/uri")
            vertex_count = sum(line.startswith("v ") for line in self.bundle["meshes"][leaves_uri].splitlines())
            self.assertEqual(vertex_count, 77 * report["visual_leaf_count"])
            self.assertEqual(len(model.findall("link/collision")), report["rigid_collision_count"])

    def test_every_texture_reference_has_a_binary_source_asset(self):
        referenced = set()
        for model in self.bundle["models"]:
            for metal in model.findall(".//material/pbr/metal"):
                referenced.update(node.text for node in metal if node.tag.endswith("_map"))
        self.assertTrue(referenced)
        self.assertEqual(referenced, set(self.bundle["texture_assets"]))
        for source in self.bundle["texture_assets"].values():
            path = Path(source)
            self.assertTrue(path.is_absolute())
            self.assertTrue(path.is_file())
            self.assertEqual(path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_dynamic_units_retain_independent_calyx_mesh_and_distal_pedicel(self):
        for fruit in self.bundle["fruits"]:
            model = self.models[fruit["model_name"]]
            self.assertIsNotNone(model.find("link/visual[@name='calyx']/material/pbr/metal/normal_map"))
            self.assertIsNotNone(model.find("link/visual[@name='distal_pedicel']/geometry/cylinder"))
            self.assertIsNotNone(model.find("link/collision[@name='harvest_collision']/geometry/sphere"))


class SoilVisualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assets = procedural_soil_assets()

    def test_soil_is_deterministic_flat_and_within_existing_ground(self):
        self.assertEqual(self.assets, procedural_soil_assets())
        mesh = parse_obj(self.assets["meshes"]["meshes/harvest_soil.obj"])
        self.assertEqual(mesh["v"], [(-8, -6, 0), (8, -6, 0), (8, 10, 0), (-8, 10, 0)])
        self.assertEqual(mesh["vt"], [(0, 0), (8, 0), (8, 8), (0, 8)])
        self.assertEqual(len(mesh["f"]), 2)
        self.assertEqual(set(mesh["vn"]), {(0, 0, 1)})

    def test_soil_pngs_are_valid_periodic_and_have_no_alpha(self):
        for uri, data in self.assets["generated_binary_assets"].items():
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            position, compressed = 8, bytearray()
            while position < len(data):
                length = struct.unpack(">I", data[position:position + 4])[0]
                kind = data[position + 4:position + 8]
                payload = data[position + 8:position + 8 + length]
                expected_crc = struct.unpack(">I", data[position + 8 + length:position + 12 + length])[0]
                self.assertEqual(zlib.crc32(kind + payload) & 0xFFFFFFFF, expected_crc)
                if kind == b"IHDR":
                    width, height, depth, color, _, _, _ = struct.unpack(">IIBBBBB", payload)
                    self.assertEqual((width, height, depth), (256, 256, 8))
                    self.assertIn(color, (0, 2))
                    channels = 3 if color == 2 else 1
                elif kind == b"IDAT":
                    compressed.extend(payload)
                position += length + 12
            raw = zlib.decompress(compressed)
            stride = width * channels + 1
            rows = [raw[y * stride + 1:(y + 1) * stride] for y in range(height)]
            self.assertTrue(all(raw[y * stride] == 0 for y in range(height)))
            self.assertEqual(rows[0], rows[-1])
            self.assertTrue(all(row[:channels] == row[-channels:] for row in rows))
            if "albedo" in uri:
                self.assertGreater(len({row[i:i + 3] for row in rows for i in range(0, len(row), 3)}), 90)
            else:
                self.assertGreaterEqual(min(min(row) for row in rows), 244)

    def test_soil_material_uses_generated_assets_without_changing_geometry(self):
        visual = ET.fromstring('<visual><geometry><mesh><uri>meshes/harvest_soil.obj</uri></mesh></geometry></visual>')
        before = ET.tostring(visual.find("geometry"))
        apply_soil_material(visual)
        self.assertEqual(before, ET.tostring(visual.find("geometry")))
        self.assertEqual(visual.findtext("material/pbr/metal/roughness"), "0.98")
        for kind in ("albedo", "roughness"):
            self.assertIn(visual.findtext(f"material/pbr/metal/{kind}_map"), self.assets["generated_binary_assets"])


if __name__ == "__main__":
    unittest.main()
