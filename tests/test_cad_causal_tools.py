"""Mutation boundaries of the reproducible diagnostic-only CAD tools."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


causal = load('prepare_cad_dynamics_causal')
gear = load('probe_native_gear_backend')


class CausalMutationTests(unittest.TestCase):
    def fixture(self):
        return ET.fromstring('''<sdf><world name="fixture"><physics><max_step_size>.0001</max_step_size></physics>
        <gravity>0 0 -9.81</gravity><model name="harvester"><link name="part"><inertial><mass>2</mass></inertial>
        <collision name="solid"><geometry><sphere><radius>.001</radius></sphere></geometry>
        <surface><contact><collide_bitmask>42</collide_bitmask></contact></surface></collision></link>
        <plugin filename="libUchuvaRobotTelemetrySystem.so"><topic>/joints</topic></plugin>
        <plugin filename="gz-sim-pose-publisher-system"><update_frequency>100</update_frequency></plugin>
        <plugin filename="gz-sim-joint-controller-system"><joint_name>left_wheel_joint</joint_name>
        <use_force_commands>true</use_force_commands><p_gain>30</p_gain><i_gain>4</i_gain><d_gain>0</d_gain>
        <cmd_min>-6.5</cmd_min><cmd_max>6.5</cmd_max></plugin>
        <plugin filename="libUchuvaJointPositionForceSystem.so"><p_gain>.2</p_gain><d_gain>.01</d_gain></plugin>
        </model></world></sdf>''')

    def test_time_step_does_not_modify_source_physics_or_controls(self):
        source = self.fixture()
        frozen = causal.xml_value(source)
        result, changes = causal.derive(source,'timestep',.00005)
        self.assertEqual(causal.xml_value(source),frozen)
        self.assertEqual(result.findtext('world/physics/max_step_size'),'5.0000000000000002e-05')
        self.assertEqual(result.findtext('.//plugin[@filename="libUchuvaRobotTelemetrySystem.so"]/publish_rate'),'20000')
        self.assertEqual(result.findtext('.//plugin[@filename="gz-sim-pose-publisher-system"]/update_frequency'),'-1')
        self.assertEqual(result.findtext('.//inertial/mass'),'2')
        self.assertEqual(result.findtext('.//plugin[@filename="libUchuvaJointPositionForceSystem.so"]/d_gain'),'.01')
        self.assertEqual(len(changes),3)

    def test_zero_feedback_preserves_force_cap_and_arm_gains(self):
        result, changes = causal.derive(self.fixture(),'zero-wheel-feedback')
        wheel = result.find('.//plugin[@filename="gz-sim-joint-controller-system"]')
        self.assertEqual([wheel.findtext(k) for k in ('p_gain','i_gain','d_gain')],['0']*3)
        self.assertEqual(wheel.findtext('cmd_max'),'6.5')
        self.assertEqual(result.findtext('.//plugin[@filename="libUchuvaJointPositionForceSystem.so"]/p_gain'),'.2')
        self.assertEqual(len(changes),3)

    def test_contact_ablation_preserves_geometry_and_mass(self):
        source = self.fixture()
        result, changes = causal.derive(source,'zero-contact-masks')
        self.assertEqual(result.findtext('.//collide_bitmask'),'0')
        self.assertEqual(causal.xml_value(result.find('.//geometry')),causal.xml_value(source.find('.//geometry')))
        self.assertEqual(result.findtext('.//inertial/mass'),'2')
        self.assertEqual(changes,[{'field':'collision_mask_0','before':'42','after':'0'}])

    def test_invalid_or_ambiguous_observation_settings_fail(self):
        for value in (None,0,-.1,float('nan'),float('inf')):
            with self.assertRaises(ValueError): causal.derive(self.fixture(),'timestep',value)
        source = self.fixture()
        plugin = source.find('.//plugin[@filename="libUchuvaRobotTelemetrySystem.so"]')
        ET.SubElement(plugin,'publish_rate').text='100'
        ET.SubElement(plugin,'publish_rate').text='100'
        with self.assertRaises(ValueError): causal.derive(source,'timestep',.00005)

    def test_asset_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for relative in ('../secret.obj','file:///secret.obj'):
                with self.assertRaises(ValueError): causal.contained_file(root,relative)

    def test_native_gear_fixture_has_reciprocal_constraint_without_motors(self):
        world = gear.rotor(True,'follower')
        mimic = world.find('.//joint[@name="follower_joint"]/axis/mimic')
        self.assertEqual(mimic.get('joint'),'leader_joint')
        self.assertEqual(mimic.findtext('multiplier'),'-1')
        names = [p.get('filename') for p in world.findall('.//plugin')]
        self.assertFalse(any('JointController' in n or 'ForceSystem' in n for n in names))
        self.assertEqual(world.findtext('.//persistent/entity_name'),'rotors::follower')
        disconnected = gear.rotor(False,'follower')
        self.assertIsNone(disconnected.find('.//mimic'))

    def test_mesh_control_uses_exact_surface_dimensions(self):
        vertices = [list(map(float,line.split()[1:])) for line in gear.meshbox().splitlines() if line.startswith('v ')]
        self.assertEqual([max(p[k] for p in vertices)-min(p[k] for p in vertices) for k in range(3)],[.02,.02,.01])
        self.assertEqual(sum(line.startswith('vn ') for line in gear.meshbox().splitlines()),len(vertices))


if __name__ == '__main__': unittest.main()
