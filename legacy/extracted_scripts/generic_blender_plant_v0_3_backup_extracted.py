import bpy
import math
import random
import json
from pathlib import Path
from mathutils import Vector

# ============================================================
# Script: planta mínima procedural en Blender
# Versión: 0.3
#
# Novedad principal:
# - semilla procedural reproducible
# - variación controlada en frutos, hojas y materiales
# ============================================================


PROJECT_MATERIAL_PREFIXES = (
    "Tallo_verde",
    "Hoja_verde",
    "Fruto_naranja"
)

# ============================================================
# 1. Limpieza de escena
# ============================================================

def remove_project_materials():
    """
    Elimina materiales generados por este script.
    """
    for mat in list(bpy.data.materials):
        if mat.name.startswith(PROJECT_MATERIAL_PREFIXES):
            bpy.data.materials.remove(mat, do_unlink=True)


def remove_unused_data_blocks():
    """
    Elimina data-blocks huérfanos que quedan después de borrar objetos.

    Blender puede conservar meshes, cámaras, luces, curvas, materiales, etc.,
    aunque ya no haya objetos visibles usándolos.
    """
    data_collections = [
        bpy.data.meshes,
        bpy.data.cameras,
        bpy.data.lights,
        bpy.data.curves,
        bpy.data.materials,
    ]

    for data_collection in data_collections:
        for datablock in list(data_collection):
            if datablock.users == 0:
                data_collection.remove(datablock)


def clear_scene():
    """
    Limpia la escena y purga residuos de ejecuciones anteriores.

    Esta versión borra:
    - objetos visibles;
    - meshes huérfanas;
    - cámaras huérfanas;
    - luces huérfanas;
    - materiales del proyecto;
    - otros data-blocks sin usuarios.
    """
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

    remove_project_materials()
    remove_unused_data_blocks()


# ============================================================
# 2. Utilidades generales
# ============================================================

def clamp01(x):
    return max(0.0, min(1.0, x))


def jitter_color(base_color, rng, amount=0.05):
    """
    Perturba ligeramente el color RGB manteniendo alpha.
    """
    r, g, b, a = base_color
    return (
        clamp01(r + rng.uniform(-amount, amount)),
        clamp01(g + rng.uniform(-amount, amount)),
        clamp01(b + rng.uniform(-amount, amount)),
        a
    )


def distance_3d(a, b):
    return math.sqrt(
        (a[0] - b[0]) ** 2 +
        (a[1] - b[1]) ** 2 +
        (a[2] - b[2]) ** 2
    )


# ============================================================
# 3. Materiales
# ============================================================

def create_material(name, color, roughness=0.55, metallic=0.0):
    """
    Crea o actualiza un material coherente para viewport y render.

    Si el material ya existe, no crea uno nuevo: lo reutiliza y actualiza.
    """
    mat = bpy.data.materials.get(name)

    if mat is None:
        mat = bpy.data.materials.new(name)

    mat.diffuse_color = color
    mat.use_nodes = True

    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")

    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic

    return mat


def create_project_materials(rng):
    """
    Crea materiales con ligera variación controlada por semilla.
    """
    stem_base = (0.05, 0.45, 0.05, 1.0)
    leaf_base = (0.15, 0.75, 0.12, 1.0)
    fruit_base = (1.0, 0.48, 0.02, 1.0)

    materials = {
        "stem": create_material(
            "Tallo_verde",
            jitter_color(stem_base, rng, amount=0.03),
            roughness=0.65 + rng.uniform(-0.05, 0.05)
        ),
        "leaf": create_material(
            "Hoja_verde",
            jitter_color(leaf_base, rng, amount=0.05),
            roughness=0.75 + rng.uniform(-0.07, 0.05)
        ),
        "fruit": create_material(
            "Fruto_naranja",
            jitter_color(fruit_base, rng, amount=0.06),
            roughness=0.35 + rng.uniform(-0.05, 0.08)
        )
    }

    return materials


# ============================================================
# 4. Utilidades geométricas
# ============================================================

def create_cylinder_between(name, start, end, radius, material):
    start = Vector(start)
    end = Vector(end)

    direction = end - start
    length = direction.length

    if length < 1e-6:
        print(f"Advertencia: cilindro '{name}' no creado porque su longitud es casi cero.")
        return None

    midpoint = (start + end) / 2

    bpy.ops.mesh.primitive_cylinder_add(
        vertices=16,
        radius=radius,
        depth=length,
        location=midpoint
    )

    cylinder = bpy.context.object
    cylinder.name = name
    cylinder.rotation_euler = direction.to_track_quat('Z', 'Y').to_euler()
    cylinder.data.materials.append(material)

    bpy.ops.object.shade_smooth()

    return cylinder


# ============================================================
# 5. Creadores de órganos vegetales
# ============================================================

def create_stem(name, radius, depth, location, material):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=32,
        radius=radius,
        depth=depth,
        location=location
    )

    stem = bpy.context.object
    stem.name = name
    stem.data.materials.append(material)

    bpy.ops.object.shade_smooth()

    return stem


def create_fruit(name, location, radius, fruit_material, stem_material, attach_to_stem=True):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=32,
        ring_count=16,
        radius=radius,
        location=location
    )

    fruit = bpy.context.object
    fruit.name = name
    fruit.data.materials.append(fruit_material)

    bpy.ops.object.shade_smooth()

    if attach_to_stem:
        x, y, z = location
        start = (0, 0, z)

        fruit_center = Vector(location)
        stem_point = Vector(start)
        direction = fruit_center - stem_point

        if direction.length > 1e-6:
            direction = direction.normalized()
            end = fruit_center - direction * radius * 0.85

            create_cylinder_between(
                name=f"pedunculo_{name}",
                start=start,
                end=end,
                radius=0.025,
                material=stem_material
            )

    return fruit


def create_leaf(name, location, direction, scale, material):
    """
    Crea una hoja procedural simple con forma foliar.

    La hoja:
    - nace en 'location';
    - crece en la dirección 'direction';
    - usa su eje local +Y como eje longitudinal.
    """
    width = scale[0] * 2.0
    length = scale[1] * 2.0

    mesh = create_leaf_mesh(
        name=name,
        length=length,
        width=width,
        curve_amount=0.035,
        segments=10
    )

    leaf = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(leaf)

    direction = Vector(direction)

    if direction.length < 1e-6:
        direction = Vector((0, 1, 0))

    direction = direction.normalized()

    # Alinea el eje local +Y de la hoja con la dirección deseada.
    leaf.rotation_euler = direction.to_track_quat('Y', 'Z').to_euler()
    leaf.location = location

    leaf.data.materials.append(material)

    return leaf

def create_leaf_mesh(name, length, width, curve_amount=0.04, segments=8):
    """
    Crea una malla simple con forma de hoja.

    La hoja se define en coordenadas locales:
    - nace cerca de y = 0;
    - crece hacia +Y;
    - tiene anchura variable;
    - termina en punta;
    - tiene una ligera curvatura en Z.
    """
    vertices = []
    faces = []

    for i in range(segments + 1):
        t = i / segments

        y = t * length

        # Perfil de anchura:
        # - cero en la base;
        # - máximo hacia la zona media;
        # - cero en la punta.
        profile = math.sin(math.pi * t) ** 0.75

        # Ajuste suave para que la hoja sea un poco más ancha antes de la mitad.
        asymmetry = 1.0 - 0.18 * t
        half_width = 0.5 * width * profile * asymmetry

        # Curvatura ligera: centro algo elevado.
        z = curve_amount * math.sin(math.pi * t)

        vertices.append((-half_width, y, z))
        vertices.append(( half_width, y, z))

    for i in range(segments):
        left_0 = 2 * i
        right_0 = 2 * i + 1
        left_1 = 2 * (i + 1)
        right_1 = 2 * (i + 1) + 1

        faces.append((left_0, right_0, right_1, left_1))

    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()

    return mesh


# ============================================================
# 6. Generadores de especificaciones
# ============================================================

def generate_fruit_specs(
    rng,
    count=2,
    z_start=2.45,
    z_step=0.42,
    radius_from_stem=0.58,
    angle_start_deg=0,
    angle_step_deg=145,
    radii=None
):
    specs = []

    if radii is None:
        radii = [0.35, 0.25, 0.28]

    for i in range(count):
        angle_deg = angle_start_deg + i * angle_step_deg + rng.uniform(-18, 18)
        angle_rad = math.radians(angle_deg)

        local_radius_from_stem = radius_from_stem + rng.uniform(-0.07, 0.07)

        x = local_radius_from_stem * math.cos(angle_rad)
        y = local_radius_from_stem * math.sin(angle_rad)
        z = z_start + i * z_step + rng.uniform(-0.06, 0.06)

        base_radius = radii[i % len(radii)]
        radius = max(0.12, base_radius * rng.uniform(0.88, 1.15))

        specs.append({
            "name": f"fruto_{i+1:02d}",
            "location": (x, y, z),
            "radius": radius
        })

    return specs


def generate_leaf_specs(
    rng,
    count=6,
    z_start=0.9,
    z_step=0.32,
    z_max=3.05,
    stem_radius=0.08,
    angle_step_deg=137.5,
    fruit_specs=None,
    min_clearance_to_fruit=0.25,
    max_candidates_factor=8
):
    """
    Genera hojas que nacen del tallo y crecen radialmente hacia afuera.

    Mejora v0.4:
    - la ubicación de la hoja es su punto de inserción en el tallo;
    - la dirección de crecimiento se calcula radialmente;
    - se evita que las hojas floten desconectadas del tallo.
    """
    specs = []
    fruit_specs = fruit_specs or []

    candidate_index = 0
    max_candidates = count * max_candidates_factor

    while len(specs) < count and candidate_index < max_candidates:
        angle_deg = candidate_index * angle_step_deg + rng.uniform(-18, 18)
        angle_rad = math.radians(angle_deg)

        z_candidate = z_start + candidate_index * z_step + rng.uniform(-0.05, 0.05)

        if z_candidate > z_max:
            break

        # Punto de nacimiento: cerca de la superficie del tallo.
        attach_radius = stem_radius * 1.05

        x_attach = attach_radius * math.cos(angle_rad)
        y_attach = attach_radius * math.sin(angle_rad)

        attachment_location = (x_attach, y_attach, z_candidate)
        petiole_length = rng.uniform(0.16, 0.26)
        petiole_radius = rng.uniform(0.012, 0.018)

        blade_location = (
            x_attach + direction[0] * petiole_length,
            y_attach + direction[1] * petiole_length,
            z_candidate + direction[2] * petiole_length
        )

        # Dirección radial hacia afuera, con una pequeña inclinación vertical.
        elevation_deg = rng.uniform(-12, 18)
        elevation_rad = math.radians(elevation_deg)

        direction = (
            math.cos(angle_rad) * math.cos(elevation_rad),
            math.sin(angle_rad) * math.cos(elevation_rad),
            math.sin(elevation_rad)
        )

        # Punto aproximado del centro de la hoja para revisar cercanía con frutos.
        approximate_leaf_length = 0.95
        leaf_center_estimate = (
            blade_location[0] + direction[0] * approximate_leaf_length * 0.5,
            blade_location[1] + direction[1] * approximate_leaf_length * 0.5,
            blade_location[2] + direction[2] * approximate_leaf_length * 0.5
        )

        too_close_to_fruit = False

        for fruit in fruit_specs:
            fruit_location = fruit["location"]
            fruit_radius = fruit["radius"]
            safe_distance = fruit_radius + min_clearance_to_fruit

            if distance_3d(leaf_center_estimate, fruit_location) < safe_distance:
                too_close_to_fruit = True
                break

        if not too_close_to_fruit:
            base_length = 0.45 + 0.04 * (candidate_index % 3)
            base_width = 0.18 + 0.02 * (candidate_index % 2)

            leaf_length = base_length * rng.uniform(0.90, 1.15)
            leaf_width = base_width * rng.uniform(0.88, 1.12)

            specs.append({
                "name": f"hoja_{len(specs)+1:02d}",
                "attachment_location": attachment_location,
                "blade_location": blade_location,
                "direction": direction,
                "petiole_length": petiole_length,
                "petiole_radius": petiole_radius,
                "scale": (leaf_width, leaf_length, 1.0)
            })

        candidate_index += 1

    if len(specs) < count:
        print(
            f"Advertencia: solo se generaron {len(specs)} hojas de {count}. "
            "La altura máxima o las restricciones con frutos pueden estar limitando la generación."
        )

    return specs


def generate_plant_specs(seed=42):
    """
    Genera la descripción completa de la planta a partir de una semilla.
    """
    rng = random.Random(seed)

    stem_radius = 0.08 + rng.uniform(-0.01, 0.015)
    stem_depth = 3.4 + rng.uniform(-0.15, 0.20)

    stem_specs = {
        "name": "tallo_principal",
        "radius": stem_radius,
        "depth": stem_depth,
        "location": (0, 0, stem_depth / 2)
    }

    fruit_count = rng.randint(2, 4)
    leaf_count = rng.randint(5, 8)

    fruit_specs = generate_fruit_specs(
        rng=rng,
        count=fruit_count,
        z_start=2.20 + rng.uniform(-0.10, 0.10),
        z_step=0.38 + rng.uniform(-0.04, 0.05),
        radius_from_stem=0.56 + rng.uniform(-0.05, 0.05),
        angle_start_deg=rng.uniform(0, 30),
        angle_step_deg=135 + rng.uniform(-15, 15),
        radii=[0.35, 0.25, 0.30]
    )

    leaf_specs = generate_leaf_specs(
        rng=rng,
        count=leaf_count,
        z_start=0.80 + rng.uniform(-0.08, 0.08),
        z_step=0.30 + rng.uniform(-0.03, 0.04),
        z_max=stem_depth - 0.35,
        stem_radius=stem_radius,
        angle_step_deg=137.5 + rng.uniform(-10, 10),
        fruit_specs=fruit_specs,
        min_clearance_to_fruit=0.25)

    return {
        "seed": seed,
        "stem": stem_specs,
        "fruits": fruit_specs,
        "leaves": leaf_specs
    }


# ============================================================
# 7. Construcción de planta
# ============================================================

def build_plant(plant_specs, materials):
    stem_spec = plant_specs["stem"]

    create_stem(
        name=stem_spec["name"],
        radius=stem_spec["radius"],
        depth=stem_spec["depth"],
        location=stem_spec["location"],
        material=materials["stem"]
    )

    for fruit in plant_specs["fruits"]:
        create_fruit(
            name=fruit["name"],
            location=fruit["location"],
            radius=fruit["radius"],
            fruit_material=materials["fruit"],
            stem_material=materials["stem"],
            attach_to_stem=True
        )

    for leaf in plant_specs["leaves"]:
        create_cylinder_between(
            name=f"peciolo_{leaf['name']}",
            start=leaf["attachment_location"],
            end=leaf["blade_location"],
            radius=leaf["petiole_radius"],
            material=materials["stem"]
        )

        create_leaf(
            name=leaf["name"],
            location=leaf["blade_location"],
            direction=leaf["direction"],
            scale=leaf["scale"],
            material=materials["leaf"]
        )


# ============================================================
# 8. Cámara, luz y render
# ============================================================

def setup_camera_and_light():
    bpy.ops.object.light_add(
        type='AREA',
        location=(2.5, -3.0, 5.0)
    )

    light = bpy.context.object
    light.name = "luz_area"
    light.data.energy = 500
    light.data.size = 4

    bpy.ops.object.camera_add(
        location=(3.0, -5.0, 3.0),
        rotation=(math.radians(60), 0, math.radians(32))
    )

    camera = bpy.context.object
    camera.name = "camara_principal"
    bpy.context.scene.camera = camera

    return camera, light


def setup_render_settings():
    bpy.context.scene.render.resolution_x = 1280
    bpy.context.scene.render.resolution_y = 720

def save_plant_specs_to_json(plant_specs, filename="plant_specs_seed_42.json"):
    """
    Guarda las especificaciones procedurales de la planta en un archivo JSON.

    Esto permite reconstruir, auditar o comparar una planta sin depender
    visualmente de la escena de Blender.
    """
    output_path = Path(bpy.path.abspath("//")) / filename

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(plant_specs, f, indent=4, ensure_ascii=False)

    print(f"Especificaciones guardadas en: {output_path}")


# ============================================================
# 9. Ejecución principal
# ============================================================

def main():
    seed = random.randint(0,10)

    clear_scene()

    plant_specs = generate_plant_specs(seed=seed)
    save_plant_specs_to_json(
    plant_specs,
    filename=f"plant_specs_seed_{seed}.json"
)

    rng_for_materials = random.Random(seed + 1000)
    materials = create_project_materials(rng_for_materials)

    build_plant(
        plant_specs=plant_specs,
        materials=materials
    )

    setup_camera_and_light()
    setup_render_settings()

    print("Planta procedural generada correctamente.")
    print(f"Seed: {plant_specs['seed']}")
    print(f"Frutos generados: {len(plant_specs['fruits'])}")
    print(f"Hojas generadas: {len(plant_specs['leaves'])}")


main()
