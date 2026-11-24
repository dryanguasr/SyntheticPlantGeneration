"""Native split-and-weld adapter for an SDF mechanism's non-tree joints.

The auxiliary has the body's identical frame and inertial COM, with a fraction
of its mass and tensor. Their sum is precisely the original rigid inertia.
No geometry is duplicated, and no passive coordinate is prescribed.
"""
from __future__ import annotations

from copy import deepcopy
import math
import xml.etree.ElementTree as ET


def adapt_loop_joint(model: ET.Element, joint_name: str, *,
                     mass_fraction: float = 0.5) -> dict:
    """Turn one extra moving joint into a tree joint plus native fixed closure.

    Invoke before loading the model in Gazebo. The original child must also be
    connected through the ordinary kinematic tree. Multiple closures on a body
    partition the remaining body's inertia in sequence, preserving its sum.
    """
    if not math.isfinite(mass_fraction) or not 0 < mass_fraction < 1:
        raise ValueError('Auxiliary mass fraction must be strictly between 0 and 1')
    joints = {row.get('name'): row for row in model.findall('joint')}
    links = {row.get('name'): row for row in model.findall('link')}
    joint = joints[joint_name]
    if joint.get('type') not in ('revolute', 'prismatic', 'ball', 'universal'):
        raise ValueError('Closure must preserve a supported moving joint')
    body_name = joint.findtext('child')
    body = links[body_name]
    if not any(row is not joint and row.findtext('child') == body_name
               for row in joints.values()):
        raise ValueError('Closure child must already have an ordinary tree joint')
    auxiliary_name = f'{body_name}__closure_{joint_name}'
    if auxiliary_name in links:
        raise ValueError('Auxiliary already exists')
    inertial = body.find('inertial')
    if inertial is None or inertial.find('mass') is None or inertial.find('inertia') is None:
        raise ValueError('Explicit body inertia is required for a mass-conserving split')
    values = [inertial.find('mass'), *list(inertial.find('inertia'))]
    if any(not math.isfinite(float(row.text)) for row in values) or float(values[0].text) <= 0:
        raise ValueError('Non-finite or nonpositive source inertia')
    auxiliary = ET.Element('link', name=auxiliary_name)
    if body.find('pose') is not None:
        auxiliary.append(deepcopy(body.find('pose')))
    # Link-level gravity/kinematic properties must remain identical; visual,
    # collision and sensors belong only to the original physical body's link.
    for tag in ('gravity', 'kinematic', 'enable_wind', 'velocity_decay'):
        if body.find(tag) is not None:
            auxiliary.append(deepcopy(body.find(tag)))
    auxiliary_inertial = deepcopy(inertial)
    auxiliary.append(auxiliary_inertial)
    auxiliary_values = [auxiliary_inertial.find('mass'), *list(auxiliary_inertial.find('inertia'))]
    original_mass = float(values[0].text)
    for source, duplicate in zip(values, auxiliary_values):
        original = float(source.text)
        duplicate.text = format(original * mass_fraction, '.17g')
        source.text = format(original - float(duplicate.text), '.17g')
    model.insert(list(model).index(body) + 1, auxiliary)
    joint.find('child').text = auxiliary_name
    plugin = next((p for p in model.findall('plugin')
                   if p.get('name') == 'uchuva::ClosedLoopSystem'), None)
    if plugin is None:
        plugin = ET.SubElement(model, 'plugin',
            filename='libUchuvaClosedLoopSystem.so', name='uchuva::ClosedLoopSystem')
    closure = ET.SubElement(plugin, 'closure', name=joint_name)
    ET.SubElement(closure, 'body').text = body_name
    ET.SubElement(closure, 'auxiliary').text = auxiliary_name
    return {'adapter': 'native_dart_split_and_weld', 'moving_joint': joint_name,
            'body': body_name, 'auxiliary': auxiliary_name,
            'mass_fraction': mass_fraction, 'original_body_mass_kg': original_mass,
            'mass_after_kg': float(values[0].text) + float(auxiliary_values[0].text)}
