import bpy
import math
import random
import json
from pathlib import Path
from mathutils import Vector

# ============================================================
# Script: planta procedural mínima para Blender
# Versión: 0.5
#
# Enfoque:
# - planta generada por especificaciones;
# - semilla reproducible;
# - limpieza de objetos/materiales/data-blocks;
# - tallo ligeramente ahusado;
# - frutos colgantes con pedúnculo;
# - hojas foliares con pecíolo y nervadura;
# - exportación de plant_specs a JSON.
#
# Uso recomendado en Blender:
# 1. Abrir el editor de scripting.
# 2. Pegar este script.
# 3. Ejecutar.
# 4. Revisar la semilla impresa en consola.
# ============================================================


# ============================================================
# 0. Configuración general
# ============================================================

SCRIPT_VERSION = "0.5"

# Modo de semilla:
# - "fixed": usa siempre FIXED_SEED.
# - "small_random": escoge un entero entre SMALL_RANDOM_MIN y SMALL_RANDOM_MAX.
#   Esto permite probar pocas variantes repetibles ejecutando varias veces.
SEED_MODE = "small_random"
FIXED_SEED = 42
SMALL_RANDOM_MIN = 0
SMALL_RANDOM_MAX = 10

SAVE_JSON = True
JSON_FOLDER_NAME = "generated_specs"

PROJECT_PREFIX = "planta_"
PROJECT_MATERIAL_PREFIX = "Planta_"


# ============================================================
# 1. Limpieza de escena
# ============================================================

def remove_project_materials():
    """
    Elimina materiales generados por este script.
    """
    for mat in list(bpy.data.materials):
        if mat.name.startswith(PROJECT_MATERIAL_PREFIX):
            bpy.data.materials.remove(mat, do_unlink=True)


def remove_unused_data_blocks():
    """
    Elimina data-blocks huérfanos que quedan después de borrar objetos.
    """
    data_collections = [
        bpy.data.meshes,
        bpy.data.cameras,
        bpy.data.lights,
        bpy.data.curves,
        bpy.data.materials,
        bpy.data.images,
    ]

    for data_collection in data_collections:
        for datablock in list(data_collection):
            if datablock.users == 0:
                try:
                    data_collection.remove(datablock)
                except RuntimeError:
                    pass


def clear_scene():
    """
    Limpia la escena para ejecutar el generador desde cero.
    """
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

    remove_project_materials()
    remove_unused_data_blocks()

    # Purga adicional. En algunos contextos de Blender puede fallar por contexto;
    # por eso se protege con try/except.
    try:
        bpy.ops.outliner.orphans_purge(
            do_local_ids=True,
            do_linked_ids=True,
            do_recursive=True
        )
    except Exception:
        pass


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


def radial_direction(angle_rad, elevation_deg=0.0):
    """
    Retorna una dirección radial 3D a partir de un ángulo en XY
    y una elevación en grados.
    """
    elevation_rad = math.radians(elevation_deg)

    return (
        math.cos(angle_rad) * math.cos(elevation_rad),
        math.sin(angle_rad) * math.cos(elevation_rad),
        math.sin(elevation_rad)
    )


def add_vec(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def scale_vec(v, s):
    return (v[0] * s, v[1] * s, v[2] * s)


def choose_seed():
    if SEED_MODE == "fixed":
        return FIXED_SEED

    if SEED_MODE == "small_random":
        return random.randint(SMALL_RANDOM_MIN, SMALL_RANDOM_MAX)

    raise ValueError(f"SEED_MODE no reconocido: {SEED_MODE}")


# ============================================================
# 3. Materiales
# ============================================================

def create_material(name, color, roughness=0.55, metallic=0.0):
    """
    Crea o actualiza un material coherente para viewport y render.
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
    Crea un conjunto pequeño y reutilizable de materiales.
    """
    materials = {
        "stem": create_material(
            "Planta_Tallo_verde",
            jitter_color((0.05, 0.42, 0.05, 1.0), rng, amount=0.035),
            roughness=0.70
        ),
        "petiole": create_material(
            "Planta_Peciolo_verde",
            jitter_color((0.05, 0.34, 0.04, 1.0), rng, amount=0.025),
            roughness=0.72
        ),
        "leaf": create_material(
            "Planta_Hoja_verde",
            jitter_color((0.16, 0.66, 0.13, 1.0), rng, amount=0.05),
            roughness=0.80
        ),
        "leaf_vein": create_material(
            "Planta_Nervadura_verde",
            jitter_color((0.08, 0.45, 0.07, 1.0), rng, amount=0.025),
            roughness=0.82
        ),
        "fruit_unripe": create_material(
            "Planta_Fruto_inmaduro",
            jitter_color((0.55, 0.66, 0.10, 1.0), rng, amount=0.04),
            roughness=0.45
        ),
        "fruit_ripe": create_material(
            "Planta_Fruto_maduro",
            jitter_color((0.95, 0.48, 0.04, 1.0), rng, amount=0.06),
            roughness=0.38
        ),
        "fruit_overripe": create_material(
            "Planta_Fruto_sobremaduro",
            jitter_color((0.80, 0.33, 0.02, 1.0), rng, amount=0.05),
            roughness=0.42
        ),
        "calyx": create_material(
            "Planta_Caliz_verde_seco",
            jitter_color((0.30, 0.38, 0.12, 1.0), rng, amount=0.04),
            roughness=0.82
        )
    }

    return materials


# ============================================================
# 4. Utilidades geométricas
# ============================================================

def create_cylinder_between(name, start, end, radius, material, vertices=16):
    """
    Crea un cilindro entre dos puntos 3D.
    """
    start = Vector(start)
    end = Vector(end)

    direction = end - start
    length = direction.length

    if length < 1e-6:
        print(f"Advertencia: cilindro '{name}' no creado porque su longitud es casi cero.")
        return None

    midpoint = (start + end) / 2

    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices,
        radius=radius,
        depth=length,
        location=midpoint
    )

    cylinder = bpy.context.object
    cylinder.name = name
    cylinder.data.name = f"{name}_mesh"
    cylinder.rotation_euler = direction.to_track_quat('Z', 'Y').to_euler()
    cylinder.data.materials.append(material)

    bpy.ops.object.shade_smooth()

    return cylinder


def create_tapered_stem_mesh(name, height, bottom_radius, top_radius, bend=(0.0, 0.0), vertices=32, rings=8):
    """
    Crea una malla de tallo ligeramente ahusada.

    El tallo va desde z=0 hasta z=height.
    bend permite una curvatura suave del eje central.
    """
    mesh_vertices = []
    faces = []

    for j in range(rings + 1):
        t = j / rings
        z = t * height

        radius = bottom_radius * (1.0 - t) + top_radius * t

        # Curvatura suave: cero en base y punta, máxima cerca del centro.
        bend_factor = math.sin(math.pi * t)
        cx = bend[0] * bend_factor
        cy = bend[1] * bend_factor

        for i in range(vertices):
            angle = 2.0 * math.pi * i / vertices
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)

            mesh_vertices.append((x, y, z))

    for j in range(rings):
        for i in range(vertices):
            a = j * vertices + i
            b = j * vertices + (i + 1) % vertices
            c = (j + 1) * vertices + (i + 1) % vertices
            d = (j + 1) * vertices + i

            faces.append((a, b, c, d))

    bottom_face = tuple(range(vertices - 1, -1, -1))
    top_start = rings * vertices
    top_face = tuple(top_start + i for i in range(vertices))

    faces.append(bottom_face)
    faces.append(top_face)

    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(mesh_vertices, [], faces)
    mesh.update()

    return mesh


def create_leaf_mesh(name, length, width, curve_amount=0.035, segments=12, edge_phase=0.0, edge_waviness=0.035):
    """
    Crea una hoja simple con forma foliar.

    Coordenadas locales:
    - base en y=0;
    - crecimiento hacia +Y;
    - ancho máximo cerca de la mitad;
    - punta en y=length;
    - curvatura suave en Z.
    """
    vertices = []
    faces = []

    for i in range(segments + 1):
        t = i / segments
        y = t * length

        profile = math.sin(math.pi * t) ** 0.75
        asymmetry = 1.0 - 0.16 * t

        # Pequeña variación de borde para evitar hojas demasiado perfectas.
        edge_variation = 1.0 + edge_waviness * math.sin(5.0 * math.pi * t + edge_phase)

        half_width = 0.5 * width * profile * asymmetry * edge_variation
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

    for polygon in mesh.polygons:
        polygon.use_smooth = True

    return mesh


# ============================================================
# 5. Creadores de órganos vegetales
# ============================================================

def create_stem(name, spec, material):
    """
    Crea el tallo principal.
    """
    mesh = create_tapered_stem_mesh(
        name=name,
        height=spec["height"],
        bottom_radius=spec["bottom_radius"],
        top_radius=spec["top_radius"],
        bend=spec["bend"],
        vertices=36,
        rings=10
    )

    stem = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(stem)

    stem.data.materials.append(material)

    return stem


def create_fruit(name, location, radius, scale, material):
    """
    Crea un fruto como esfera ligeramente escalada.
    """
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=36,
        ring_count=18,
        radius=radius,
        location=location
    )

    fruit = bpy.context.object
    fruit.name = name
    fruit.data.name = f"{name}_mesh"
    fruit.scale = scale
    fruit.data.materials.append(material)

    bpy.ops.object.shade_smooth()

    return fruit


def create_calyx(name, location, radius, material):
    """
    Crea un cáliz simplificado encima del fruto.
    """
    depth = radius * 0.28
    base_radius = radius * 0.18

    bpy.ops.mesh.primitive_cone_add(
        vertices=7,
        radius1=base_radius,
        radius2=base_radius * 0.35,
        depth=depth,
        location=(location[0], location[1], location[2] + depth * 0.5)
    )

    calyx = bpy.context.object
    calyx.name = name
    calyx.data.name = f"{name}_mesh"
    calyx.data.materials.append(material)

    bpy.ops.object.shade_smooth()

    return calyx


def create_leaf(name, location, direction, scale, material, edge_phase=0.0):
    """
    Crea una hoja procedural.

    La hoja crece desde su origen local hacia +Y.
    """
    width = scale[0] * 2.0
    length = scale[1] * 2.0

    mesh = create_leaf_mesh(
        name=name,
        length=length,
        width=width,
        curve_amount=0.035,
        segments=14,
        edge_phase=edge_phase,
        edge_waviness=0.035
    )

    leaf = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(leaf)

    direction = Vector(direction)

    if direction.length < 1e-6:
        direction = Vector((0.0, 1.0, 0.0))

    direction = direction.normalized()

    leaf.rotation_euler = direction.to_track_quat('Y', 'Z').to_euler()
    leaf.location = location
    leaf.data.materials.append(material)

    # Espesor mínimo para que no se vea como plano matemático perfecto.
    solidify = leaf.modifiers.new(name="espesor_minimo", type="SOLIDIFY")
    solidify.thickness = 0.006
    solidify.offset = 0.0

    return leaf


def create_leaf_midrib(name, blade_location, direction, leaf_length, material):
    """
    Crea una nervadura central simplificada.
    """
    direction = Vector(direction)

    if direction.length < 1e-6:
        return None

    direction = direction.normalized()

    start = Vector(blade_location) + direction * (leaf_length * 0.08)
    end = Vector(blade_location) + direction * (leaf_length * 0.88)

    return create_cylinder_between(
        name=name,
        start=start,
        end=end,
        radius=0.006,
        material=material,
        vertices=8
    )


# ============================================================
# 6. Generadores de especificaciones
# ============================================================

def generate_stem_specs(rng):
    height = rng.uniform(3.10, 3.65)
    bottom_radius = rng.uniform(0.075, 0.095)
    top_radius = bottom_radius * rng.uniform(0.72, 0.88)

    bend_angle = rng.uniform(0, 2.0 * math.pi)
    bend_magnitude = rng.uniform(0.00, 0.05)

    bend = (
        bend_magnitude * math.cos(bend_angle),
        bend_magnitude * math.sin(bend_angle)
    )

    return {
        "name": f"{PROJECT_PREFIX}tallo_principal",
        "height": height,
        "bottom_radius": bottom_radius,
        "top_radius": top_radius,
        "bend": bend
    }


def fruit_material_key_from_maturity(maturity):
    if maturity == "unripe":
        return "fruit_unripe"

    if maturity == "overripe":
        return "fruit_overripe"

    return "fruit_ripe"


def generate_fruit_specs(
    rng,
    stem_specs,
    count=3,
    min_clearance=0.10,
    max_attempts_per_fruit=20
):
    """
    Genera frutos colgantes con pedúnculo.

    Cada fruto tiene:
    - punto de inserción en el tallo;
    - punto de conexión en la parte superior del fruto;
    - centro del fruto;
    - radio;
    - madurez aproximada.
    """
    specs = []

    stem_height = stem_specs["height"]
    stem_radius = stem_specs["bottom_radius"]

    angle_start_deg = rng.uniform(0, 80)
    angle_step_deg = rng.uniform(110, 150)

    z_min = stem_height * 0.48
    z_max = stem_height * 0.87

    for i in range(count):
        created = False

        for attempt in range(max_attempts_per_fruit):
            angle_deg = angle_start_deg + i * angle_step_deg + rng.uniform(-22, 22) + attempt * 13.0
            angle_rad = math.radians(angle_deg)

            radius = rng.uniform(0.20, 0.36)

            # Distribución vertical por bandas para evitar acumulación excesiva.
            if count == 1:
                band_t = 0.55
            else:
                band_t = i / (count - 1)

            z_attach = z_min * (1.0 - band_t) + z_max * band_t
            z_attach += rng.uniform(-0.12, 0.12)
            z_attach = max(0.75, min(stem_height - 0.35, z_attach))

            stem_attach_radius = stem_radius * 1.05
            direction_xy = radial_direction(angle_rad, elevation_deg=0)

            stem_attachment = (
                stem_attach_radius * math.cos(angle_rad),
                stem_attach_radius * math.sin(angle_rad),
                z_attach
            )

            peduncle_length = rng.uniform(0.18, 0.34)
            fruit_attachment = add_vec(
                stem_attachment,
                scale_vec(direction_xy, peduncle_length)
            )

            # Pequeña caída del punto de unión.
            fruit_attachment = (
                fruit_attachment[0],
                fruit_attachment[1],
                fruit_attachment[2] - rng.uniform(0.00, 0.08)
            )

            fruit_center = add_vec(
                fruit_attachment,
                (
                    direction_xy[0] * radius * rng.uniform(0.05, 0.18),
                    direction_xy[1] * radius * rng.uniform(0.05, 0.18),
                    -radius * rng.uniform(0.78, 0.95)
                )
            )

            too_close = False

            for existing in specs:
                dist = distance_3d(fruit_center, existing["location"])
                safe_dist = radius + existing["radius"] + min_clearance

                if dist < safe_dist:
                    too_close = True
                    break

            if too_close:
                continue

            maturity = rng.choices(
                population=["unripe", "ripe", "overripe"],
                weights=[0.15, 0.72, 0.13],
                k=1
            )[0]

            fruit_scale = (
                rng.uniform(0.94, 1.07),
                rng.uniform(0.94, 1.07),
                rng.uniform(0.96, 1.10)
            )

            specs.append({
                "name": f"{PROJECT_PREFIX}fruto_{len(specs)+1:02d}",
                "stem_attachment": stem_attachment,
                "fruit_attachment": fruit_attachment,
                "location": fruit_center,
                "radius": radius,
                "scale": fruit_scale,
                "maturity": maturity,
                "material_key": fruit_material_key_from_maturity(maturity),
                "peduncle_radius": rng.uniform(0.014, 0.022),
                "has_calyx": True
            })

            created = True
            break

        if not created:
            print(f"Advertencia: no se pudo ubicar el fruto {i + 1} sin solapamiento razonable.")

    return specs


def generate_leaf_specs(
    rng,
    stem_specs,
    fruit_specs,
    count=7,
    min_clearance_to_fruit=0.20,
    max_angle_attempts=12
):
    """
    Genera hojas en bandas verticales.

    Mejora frente a versiones anteriores:
    - la altura ya no depende de candidate_index indefinidamente;
    - cada hoja nace del tallo;
    - hay pecíolo;
    - la lámina empieza al final del pecíolo;
    - la cercanía con frutos se revisa desde un centro aproximado de la hoja.
    """
    specs = []

    stem_height = stem_specs["height"]
    stem_radius = stem_specs["bottom_radius"]

    z_min = stem_height * 0.18
    z_max = stem_height * 0.88

    angle_offset_deg = rng.uniform(0, 360)
    angle_step_deg = 137.5 + rng.uniform(-8, 8)

    for i in range(count):
        if count == 1:
            band_t = 0.5
        else:
            band_t = i / (count - 1)

        z_base = z_min * (1.0 - band_t) + z_max * band_t
        z_base += rng.uniform(-0.10, 0.10)
        z_base = max(0.25, min(stem_height - 0.30, z_base))

        accepted = False

        for attempt in range(max_angle_attempts):
            angle_deg = angle_offset_deg + i * angle_step_deg + rng.uniform(-22, 22) + attempt * 27
            angle_rad = math.radians(angle_deg)

            elevation_deg = rng.uniform(-10, 22)
            direction = radial_direction(angle_rad, elevation_deg=elevation_deg)

            attach_radius = stem_radius * 1.08

            attachment_location = (
                attach_radius * math.cos(angle_rad),
                attach_radius * math.sin(angle_rad),
                z_base
            )

            petiole_length = rng.uniform(0.18, 0.32)
            petiole_radius = rng.uniform(0.010, 0.017)

            blade_location = add_vec(
                attachment_location,
                scale_vec(direction, petiole_length)
            )

            base_length = rng.uniform(0.42, 0.62)
            base_width = rng.uniform(0.15, 0.24)

            leaf_length = base_length * rng.uniform(0.90, 1.18)
            leaf_width = base_width * rng.uniform(0.88, 1.15)

            approximate_leaf_length = leaf_length * 2.0

            leaf_center_estimate = add_vec(
                blade_location,
                scale_vec(direction, approximate_leaf_length * 0.50)
            )

            too_close_to_fruit = False

            for fruit in fruit_specs:
                fruit_location = fruit["location"]
                fruit_radius = fruit["radius"]
                safe_distance = fruit_radius + min_clearance_to_fruit

                if distance_3d(leaf_center_estimate, fruit_location) < safe_distance:
                    too_close_to_fruit = True
                    break

            if too_close_to_fruit:
                continue

            specs.append({
                "name": f"{PROJECT_PREFIX}hoja_{len(specs)+1:02d}",
                "attachment_location": attachment_location,
                "blade_location": blade_location,
                "direction": direction,
                "petiole_length": petiole_length,
                "petiole_radius": petiole_radius,
                "scale": (leaf_width, leaf_length, 1.0),
                "edge_phase": rng.uniform(0, 2.0 * math.pi)
            })

            accepted = True
            break

        if not accepted:
            print(f"Advertencia: no se pudo ubicar la hoja {i + 1} sin cercanía fuerte a frutos.")

    return specs


def generate_plant_specs(seed=42):
    """
    Genera la descripción completa de la planta.
    """
    rng = random.Random(seed)

    stem_specs = generate_stem_specs(rng)

    fruit_count = rng.randint(2, 4)
    leaf_count = rng.randint(6, 9)

    fruit_specs = generate_fruit_specs(
        rng=rng,
        stem_specs=stem_specs,
        count=fruit_count
    )

    leaf_specs = generate_leaf_specs(
        rng=rng,
        stem_specs=stem_specs,
        fruit_specs=fruit_specs,
        count=leaf_count,
        min_clearance_to_fruit=0.20
    )

    return {
        "script_version": SCRIPT_VERSION,
        "seed": seed,
        "stem": stem_specs,
        "fruits": fruit_specs,
        "leaves": leaf_specs
    }


# ============================================================
# 7. Construcción de la planta a partir de especificaciones
# ============================================================

def build_plant(plant_specs, materials):
    """
    Construye la geometría usando plant_specs.
    """
    stem_spec = plant_specs["stem"]

    create_stem(
        name=stem_spec["name"],
        spec=stem_spec,
        material=materials["stem"]
    )

    for fruit in plant_specs["fruits"]:
        create_cylinder_between(
            name=f"{PROJECT_PREFIX}pedunculo_{fruit['name'].replace(PROJECT_PREFIX, '')}",
            start=fruit["stem_attachment"],
            end=fruit["fruit_attachment"],
            radius=fruit["peduncle_radius"],
            material=materials["petiole"],
            vertices=12
        )

        create_fruit(
            name=fruit["name"],
            location=fruit["location"],
            radius=fruit["radius"],
            scale=fruit["scale"],
            material=materials[fruit["material_key"]]
        )

        if fruit.get("has_calyx", True):
            create_calyx(
                name=f"{PROJECT_PREFIX}caliz_{fruit['name'].replace(PROJECT_PREFIX, '')}",
                location=fruit["fruit_attachment"],
                radius=fruit["radius"],
                material=materials["calyx"]
            )

    for leaf in plant_specs["leaves"]:
        create_cylinder_between(
            name=f"{PROJECT_PREFIX}peciolo_{leaf['name'].replace(PROJECT_PREFIX, '')}",
            start=leaf["attachment_location"],
            end=leaf["blade_location"],
            radius=leaf["petiole_radius"],
            material=materials["petiole"],
            vertices=10
        )

        create_leaf(
            name=leaf["name"],
            location=leaf["blade_location"],
            direction=leaf["direction"],
            scale=leaf["scale"],
            material=materials["leaf"],
            edge_phase=leaf["edge_phase"]
        )

        leaf_length = leaf["scale"][1] * 2.0

        create_leaf_midrib(
            name=f"{PROJECT_PREFIX}nervadura_{leaf['name'].replace(PROJECT_PREFIX, '')}",
            blade_location=leaf["blade_location"],
            direction=leaf["direction"],
            leaf_length=leaf_length,
            material=materials["leaf_vein"]
        )


# ============================================================
# 8. Cámara, luz y render
# ============================================================

def look_at(obj, target):
    """
    Orienta un objeto para mirar hacia target.
    Para cámaras, el eje frontal es -Z.
    """
    target = Vector(target)
    direction = target - obj.location

    if direction.length < 1e-6:
        return

    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()


def setup_camera_and_light(plant_specs):
    """
    Crea luz y cámara principal.
    """
    stem_height = plant_specs["stem"]["height"]
    target = (0.0, 0.0, stem_height * 0.55)

    bpy.ops.object.light_add(
        type='AREA',
        location=(2.4, -3.0, stem_height + 1.5)
    )

    light = bpy.context.object
    light.name = f"{PROJECT_PREFIX}luz_area"
    light.data.name = f"{PROJECT_PREFIX}luz_area_data"
    light.data.energy = 600
    light.data.size = 4.0

    bpy.ops.object.camera_add(
        location=(3.1, -5.0, stem_height * 0.72)
    )

    camera = bpy.context.object
    camera.name = f"{PROJECT_PREFIX}camara_principal"
    camera.data.name = f"{PROJECT_PREFIX}camara_principal_data"

    look_at(camera, target)

    bpy.context.scene.camera = camera

    return camera, light


def setup_render_settings():
    """
    Ajustes básicos de salida.
    """
    scene = bpy.context.scene

    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.world.color = (0.03, 0.03, 0.03)

    # Mantenerlo compatible: si Blender acepta EEVEE Next, se usa.
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        pass


# ============================================================
# 9. Exportación de especificaciones
# ============================================================

def get_output_folder():
    """
    Retorna una carpeta de salida junto al .blend.
    """
    base_path = Path(bpy.path.abspath("//"))

    output_folder = base_path / JSON_FOLDER_NAME
    output_folder.mkdir(parents=True, exist_ok=True)

    return output_folder


def save_plant_specs_to_json(plant_specs, filename=None):
    """
    Guarda plant_specs como JSON.
    """
    if filename is None:
        seed = plant_specs.get("seed", "unknown")
        filename = f"plant_specs_seed_{seed}.json"

    output_path = get_output_folder() / filename

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(plant_specs, f, indent=4, ensure_ascii=False)

    print(f"Especificaciones guardadas en: {output_path}")

    return output_path


# ============================================================
# 10. Ejecución principal
# ============================================================

def main():
    seed = choose_seed()

    clear_scene()

    plant_specs = generate_plant_specs(seed=seed)

    rng_for_materials = random.Random(seed + 1000)
    materials = create_project_materials(rng_for_materials)

    build_plant(
        plant_specs=plant_specs,
        materials=materials
    )

    setup_camera_and_light(plant_specs)
    setup_render_settings()

    if SAVE_JSON:
        save_plant_specs_to_json(
            plant_specs,
            filename=f"plant_specs_seed_{seed}.json"
        )

    print("Planta procedural generada correctamente.")
    print(f"Versión del script: {SCRIPT_VERSION}")
    print(f"Seed: {plant_specs['seed']}")
    print(f"Frutos generados: {len(plant_specs['fruits'])}")
    print(f"Hojas generadas: {len(plant_specs['leaves'])}")


main()
