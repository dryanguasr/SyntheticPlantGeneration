"""The native adapter must conserve CAD rigid inertia and moving-joint data."""
import copy
import unittest
import xml.etree.ElementTree as ET

from uchuva_gazebo.closed_loops import adapt_loop_joint


def fixture():
    return ET.fromstring('''<model name="closed">
      <link name="housing"/><link name="rocker"><pose>1 2 3 .1 .2 .3</pose>
      <inertial><pose>.01 .02 .03 0 0 0</pose><mass>2.75</mass><inertia>
      <ixx>.7</ixx><iyy>.8</iyy><izz>.9</izz><ixy>.03</ixy><ixz>-.02</ixz><iyz>.01</iyz>
      </inertia></inertial><visual name="cad"/><collision name="cad_collision"/></link>
      <link name="coupler"/>
      <joint name="pivot" type="revolute"><parent>housing</parent><child>rocker</child></joint>
      <joint name="closure" type="revolute"><parent>coupler</parent><child>rocker</child>
      <pose relative_to="__model__">1 2 3 0 0 0</pose><axis><xyz>0 1 0</xyz>
      <limit><lower>-.4</lower><upper>.4</upper><effort>.02</effort></limit>
      <dynamics><damping>.002</damping></dynamics></axis></joint></model>''')


class ClosedLoopAdapterTests(unittest.TestCase):
    def test_split_conserves_inertia_geometry_and_joint_axis(self):
        model=fixture();original=copy.deepcopy(model)
        result=adapt_loop_joint(model,'closure',mass_fraction=.37)
        body=model.find("link[@name='rocker']")
        auxiliary=model.find(f"link[@name='{result['auxiliary']}']")
        before=original.find("link[@name='rocker']/inertial")
        for path in ('mass','inertia/ixx','inertia/iyy','inertia/izz','inertia/ixy','inertia/ixz','inertia/iyz'):
            self.assertAlmostEqual(float(before.findtext(path)),
                float(body.findtext('inertial/'+path))+float(auxiliary.findtext('inertial/'+path)),places=15)
        for path in ('pose','inertial/pose'):
            self.assertEqual(body.findtext(path),auxiliary.findtext(path))
        self.assertEqual(len(model.findall('.//visual')),1)
        self.assertEqual(len(model.findall('.//collision')),1)
        joint=model.find("joint[@name='closure']")
        expected=original.find("joint[@name='closure']")
        expected.find('child').text=result['auxiliary']
        self.assertEqual(ET.tostring(joint),ET.tostring(expected))
        self.assertEqual(result['original_body_mass_kg'],result['mass_after_kg'])

    def test_ordinary_tree_joint_is_not_mistaken_for_a_closure(self):
        model=fixture();model.remove(model.find("joint[@name='pivot']"))
        before=ET.tostring(model)
        with self.assertRaises(ValueError):adapt_loop_joint(model,'closure')
        self.assertEqual(before,ET.tostring(model))

    def test_fraction_and_duplicate_fail_before_modifying_source(self):
        for fraction in (0,1,-.1,float('nan')):
            model=fixture();before=ET.tostring(model)
            with self.assertRaises(ValueError):adapt_loop_joint(model,'closure',mass_fraction=fraction)
            self.assertEqual(before,ET.tostring(model))
        model=fixture();adapt_loop_joint(model,'closure');before=ET.tostring(model)
        with self.assertRaises(ValueError):adapt_loop_joint(model,'closure')
        self.assertEqual(before,ET.tostring(model))


if __name__=='__main__':unittest.main()
