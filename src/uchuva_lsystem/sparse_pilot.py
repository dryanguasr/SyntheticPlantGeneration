"""Pure, versioned contract for the sparse overhead-string pilot.

Dimensions and NTC grouping are experimental assumptions, not field measurements.
Blender uses eight internal units per metre, consistently with the legacy cm scale.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import math
import random

VERSION = "sparse-overhead/1.1-dense-crowns"
PRESET = "sparse_overhead_strings_v1"
UNITS_PER_METRE = 8.0
CLASSES = ("verde", "pintona", "madura", "sobremadura")
REFERENCE_FRAMES = (
    "54b14999deb5ce89_f000014626.jpg",
    "b5a8301471dcca22_f000002383.jpg",
    "5d41efddf01cd412_f000016991.jpg",
    "00feba219f5ac1d8_f000000871.jpg",
)
# Qualitative palettes from the supplied illustration, not calibrated reflectance.
CALYX_COLORS = ((.08, .22, .018, 1), (.14, .30, .025, 1),
                (.27, .37, .035, 1), (.40, .44, .04, 1),
                (.51, .47, .045, 1), (.59, .49, .05, 1), (.62, .46, .045, 1))
FRUIT_COLORS = ((.06, .20, .015, 1), (.14, .30, .02, 1),
                (.30, .40, .025, 1), (.47, .47, .02, 1),
                (.65, .46, .012, 1), (.80, .36, .01, 1), (.86, .24, .008, 1))


def class_for_grade(grade: int) -> int:
    if type(grade) is not int or not 0 <= grade <= 6:
        raise ValueError("Synthetic reference grade must be an integer in 0..6")
    return 0 if grade <= 1 else 1 if grade <= 4 else 2 if grade == 5 else 3


@dataclass(frozen=True)
class SparseConfig:
    rows: int = 6
    columns: int = 6
    row_spacing_m: float = 1.8
    plant_spacing_m: float = 1.4
    support_height_m: float = 2.5
    axis_length_factor: float = 1.4
    strings_per_plant: int = 3
    marker_side_m: float = .10
    marker_margin_m: float = .02
    marker_bottom_m: float = .05
    marker_offset_m: float = .18
    marker_backing_thickness_m: float = .003
    parameter_status: str = "manual_initial_guess"

    def __post_init__(self):
        if self.rows != 6 or self.columns != 6:
            raise ValueError("This pilot requires exactly 6 x 6 plants")
        if self.strings_per_plant < 1:
            raise ValueError("At least one support string is required")
        if not math.isfinite(self.axis_length_factor) or self.axis_length_factor <= 0:
            raise ValueError("Axis length factor must be positive and finite")
        for name, value in asdict(self).items():
            if name.endswith("_m") and (not math.isfinite(value) or value <= 0):
                raise ValueError(f"Invalid dimension: {name}")


def create_sparse_scene(seed: int, config: SparseConfig | None = None):
    from .scene import CultivationScene, PlantInstance, EnvironmentConfig
    from .support import SupportSystem, SupportPost, SupportLine
    c = config or SparseConfig()
    rng = random.Random(seed)
    plants, posts, lines = [], [], []
    u = UNITS_PER_METRE
    for row in range(c.rows):
        y = (row - (c.rows - 1) / 2) * c.row_spacing_m * u
        ends = ((-(c.columns - 1) / 2 * c.plant_spacing_m - .4) * u,
                ((c.columns - 1) / 2 * c.plant_spacing_m + .4) * u)
        for side, x in enumerate(ends):
            posts.append(SupportPost(f"row_{row}_post_{side}", (x, y, 0),
                                     c.support_height_m * u, .05*u, .05*u, f"row_{row}"))
        lines.append(SupportLine(f"row_{row}_overhead", (ends[0], y, c.support_height_m*u),
                                 (ends[1], y, c.support_height_m*u), .002*u, f"row_{row}"))
        for column in range(c.columns):
            index = row*c.columns + column
            plants.append(PlantInstance(
                f"plant_{index:02d}", seed*100 + index,
                position=((column-(c.columns-1)/2)*c.plant_spacing_m*u, y, 0),
                rotation_deg=0, scale=rng.uniform(.95, 1.05),
                training_mode="overhead_strings", collision_proxy={"canopy_radius": .35*u}))
    return CultivationScene(
        scene_id=f"{PRESET}_seed_{seed}", preset_name=PRESET, seed=seed,
        plant_instances=plants,
        support_system=SupportSystem(f"support_{seed}", "overhead_strings", posts, lines),
        row_or_bed={"row_count": c.rows, "columns": c.columns, "plant_count": 36},
        environment=EnvironmentConfig(terrain_size=90, row_spacing=c.row_spacing_m*u,
                                      ground_vegetation_profile="potato_context"),
        metadata={"script_version": VERSION, "config": asdict(c),
                  "units_per_metre": u, "parameter_status": c.parameter_status,
                  "reference_split": "train", "agronomic_interaction": "not_simulated"})


def walk_axes(axes):
    for axis in axes:
        yield axis
        yield from walk_axes(axis.child_axes)


def sparse_morphology_parameters(preset="sparse_overhead_dense_crown_v2"):
    """Dense individual crowns, independent of the sparse field layout.

    Qualitative manual revision against train frames 54b14999...14626 and
    b5a830...2383. These are engineering guesses, not measured leaf counts.
    """
    from .parameters import get_morphology_parameters
    params = get_morphology_parameters("trained_trellis")
    params["preset_name"] = "sparse_overhead_dense_crown_v2"
    def update(section, key, **values):
        params[section][key].update(values, status="manual_initial_guess")
    update("axis", "main_node_count", value=16)
    update("axis", "branch_node_count_range", min=5, max=7)
    for order, bounds in enumerate(((78,92),(32,45),(20,30),(12,20))):
        params["growth"]["length_budget_cm_by_order"][str(order)].update(
            min=bounds[0], max=bounds[1], status="manual_initial_guess")
        params["growth"]["max_internodes_by_order"][str(order)].update(
            value=(16,7,6,5)[order], status="manual_initial_guess")
    for order, probability in enumerate((.78,.60,.32)):
        params["growth"]["branch_probability_by_order"][str(order)].update(
            value=probability, status="manual_initial_guess")
    update("growth", "apical_dominance", value=.40)
    update("growth", "vigor_decay_by_order", value=.80)
    update("leaf", "length_cm_range", min=10.0, max=17.0)
    for order, scale in enumerate((1.0,1.0,.95,.90)):
        params["growth"]["leaf_length_scale_by_order"][str(order)].update(value=scale,status="manual_initial_guess")
    update("reproduction", "target_reproductive_units_range", min=40, max=65)
    if preset == "individual_dense_crown_v3":
        params["preset_name"] = preset
        update("axis", "branch_node_count_range", min=6, max=8)
        for order, probability in enumerate((.85, .70, .48)):
            params["growth"]["branch_probability_by_order"][str(order)].update(value=probability)
        update("growth", "vigor_decay_by_order", value=.86)
        update("growth", "apical_dominance", value=.25)
        for order, count in enumerate((16, 8, 7, 6)):
            params["growth"]["max_internodes_by_order"][str(order)].update(value=count)
        for order, scale in enumerate((1.0, .85, .72, .62)):
            params["growth"]["internode_length_scale_by_order"][str(order)].update(value=scale)
    elif preset != "sparse_overhead_dense_crown_v2":
        raise ValueError(f"Unknown crown preset: {preset}")
    return params


def prepare_plant(plant, config: SparseConfig | None = None):
    """Apply declared upward training and explicit grades without moving organs off nodes."""
    rng = random.Random(plant.seed + 4580)
    config = config or SparseConfig()
    units = []
    for axis in walk_axes(plant.axes):
        factor = config.axis_length_factor
        if plant.parameter_preset == "individual_dense_crown_v3" and axis.order:
            factor = 1.2
        for internode in axis.internodes:
            internode.length_cm *= factor
            internode.provenance["sparse_axis_length_factor"] = factor
        axis.growth_budget_length_cm *= factor
        axis.remaining_budget_length_cm *= factor
        axis.mechanical_deflection_deg = 0
        axis.reproductive_load = 0
        if axis.order:
            axis.branch_angle_deg = min(axis.branch_angle_deg, 55)
        axis.resolved_direction = None
        axis.training_phase = "overhead_strings_manual_initial_guess"
        for node in axis.nodes:
            if node.leaf and plant.parameter_preset in {"individual_dense_crown_v3", "sparse_overhead_dense_crown_v2"}:
                angle = rng.uniform(110,155)
                node.leaf.insertion_angle_deg = angle
                node.leaf.preferred_insertion_angle_deg = angle
                node.leaf.provenance["pose_constraint"] = "drooping_110_155_manual_initial_guess"
            unit = node.reproductive_unit
            if unit and unit.calyx and unit.fruit:
                units.append(unit)
    rng.shuffle(units)
    for index, unit in enumerate(units):
        grade = (index + plant.seed) % 7
        unit.synthetic_reference_grade = grade
        unit.provenance["synthetic_reference"] = {
            "source": "Nuevo Dataset/Norma.webp", "grade": grade,
            "class_id": class_for_grade(grade), "schema": VERSION,
            "grouping": "user_approximation", "human_validation": "pending",
            "agronomic_maturity": None}
        # Keep morphology ontology stable; visual materials have separate grade keys.
        unit.calyx.material_key = f"calyx_ntc_{grade}"
        unit.calyx.openness = .04
        unit.calyx.wrinkle = .04
    plant.metadata["sparse_pilot"] = {"version": VERSION, "parameter_status": "manual_initial_guess"}
    return plant


def attach_strings(scene, plants, config: SparseConfig | None = None):
    from .growth import _node_frames
    from .support import SupportTie, SupportContact
    from .collisions import build_scene_proxies, CollisionProxy, _proxy_clearance
    c = config or SparseConfig()
    system = scene.support_system
    system.ties.clear()
    system.contacts.clear()
    calyxes = [p for p in build_scene_proxies(scene, plants) if p.kind == "calyx"]
    for index, instance in enumerate(scene.plant_instances):
        plant = plants[instance.plant_id]
        for axis in walk_axes(plant.axes):
            axis.support_contacts = [value for value in axis.support_contacts
                                     if not value.startswith(f"{instance.plant_id}_string_")]
        frames = _node_frames(plant, instance)
        axes = [a for a in walk_axes(plant.axes) if a.nodes]
        candidates = sorted(axes, key=lambda a: (a.order != 1, a.id))[:c.strings_per_plant]
        for k, axis in enumerate(candidates):
            node = axis.nodes[-1]
            point = frames[node.id][0]
            cable = system.lines[index // c.columns]
            if point[2] >= cable.start[2]:
                raise ValueError("Support cable must be above every attachment")
            candidates = []
            for offset in (0, .12, -.12, .24, -.24, .36, -.36):
                top_x = min(cable.end[0], max(cable.start[0], point[0]+offset*UNITS_PER_METRE))
                top = (top_x, cable.start[1], cable.start[2])
                proxy = CollisionProxy("candidate",instance.plant_id,"support_tie","capsule",
                    tuple((a+b)/2 for a,b in zip(point,top)), ((1,0,0),(0,1,0),(0,0,1)),
                    (.006,.006,.006), start=point,end=top,radius=.006)
                clearance = min((_proxy_clearance(proxy,p) for p in calyxes if p.plant_id == instance.plant_id), default=1.0)
                candidates.append((clearance, -abs(offset), top))
                if clearance >= .025:
                    break
            _, _, top = max(candidates,key=lambda v:(v[0]>=.025,v[1] if v[0]>=.025 else v[0]))
            identifier = f"{instance.plant_id}_string_{k}"
            system.ties.append(SupportTie(identifier, instance.plant_id, point, top, cable.id))
            system.contacts.append(SupportContact(identifier, instance.plant_id, node.id,
                                                   identifier, point))
            axis.support_contacts.append(identifier)
    system.provenance = {"script_version": VERSION, "seed": scene.seed, "preset": PRESET,
                         "parameter_status": "manual_initial_guess"}


def marker_specs(scene, config: SparseConfig | None = None):
    c = config or SparseConfig()
    specs = []
    for i, plant in enumerate(scene.plant_instances):
        x, y, z = [v / UNITS_PER_METRE for v in plant.position]
        for face, sign in (("front", -1), ("back", 1)):
            specs.append({"id": 2*i + (face == "back"), "plant_id": plant.plant_id,
                          "face": face, "dictionary": "DICT_4X4_100",
                          "side_m": c.marker_side_m, "normal_world": [0, sign, 0],
                          "backing_thickness_m": c.marker_backing_thickness_m,
                          "printed_faces": "outward_only", "reverse_appearance": "plain_opaque",
                          "center_world_m": [x, y + sign*c.marker_offset_m,
                            z+c.marker_bottom_m+c.marker_margin_m+c.marker_side_m/2]})
    return specs


def encode_rle(mask):
    """COCO uncompressed RLE in column-major order; preserves holes/components."""
    height, width = len(mask), len(mask[0])
    counts, previous, run = [], False, 0
    for x in range(width):
        for y in range(height):
            value = bool(mask[y][x])
            if value == previous:
                run += 1
            else:
                counts.append(run)
                run, previous = 1, value
    counts.append(run)
    return {"size": [height, width], "counts": counts}


def decode_rle(rle):
    height, width = rle["size"]
    if any(type(c) is not int or c < 0 for c in rle["counts"]) or sum(rle["counts"]) != height*width:
        raise ValueError("Malformed RLE")
    result = [[False]*width for _ in range(height)]
    offset, value = 0, False
    for count in rle["counts"]:
        for i in range(offset, offset+count):
            result[i % height][i // height] = value
        offset += count
        value = not value
    return result
