import math
import unittest
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.sparse_pilot import prepare_plant,sparse_morphology_parameters
from uchuva_lsystem.curved_basal_pilot import curved_basal_pilot,CURVATURES


class CurvedBasalTest(unittest.TestCase):
    def test_curve_identity_and_interpreter_limits(self):
        base=prepare_plant(generate_morphology_tree(814140,sparse_morphology_parameters('individual_dense_crown_v3')))
        for variant in CURVATURES:
            plant=curved_basal_pilot(base,5,variant)
            self.assertEqual(base.reproductive_unit_count(),plant.reproductive_unit_count())
            for axis in plant.axes[0].child_axes:
                angle=math.radians(8);radial=height=0;points=[]
                self.assertEqual(len(axis.nodes),len(axis.internodes))
                for segment in axis.internodes:
                    self.assertGreaterEqual(segment.bend_angle_deg,0)
                    self.assertLess(segment.bend_angle_deg,12)
                    angle+=math.radians(segment.bend_angle_deg)
                    radial+=segment.length_cm*math.sin(angle)
                    height+=segment.length_cm*math.cos(angle)
                    points.append((radial,height))
                slope=math.tan(math.radians(8))
                curvature=(math.tan(math.radians(CURVATURES[variant]))-slope)/2
                for x,z in points:
                    t=z/height
                    self.assertAlmostEqual(x,height*(slope*t+curvature*t*t),places=8)
                for child in axis.child_axes:
                    self.assertIn(child.parent_node_id,{n.id for n in axis.nodes})

    def test_inward_concavity_for_all_branch_counts(self):
        base=prepare_plant(generate_morphology_tree(814140,sparse_morphology_parameters('individual_dense_crown_v3')))
        for variant in CURVATURES:
            for count in (2,3,4,5):
                plant=curved_basal_pilot(base,count,variant,inward=True)
                self.assertEqual(base.reproductive_unit_count(),plant.reproductive_unit_count())
                for axis in plant.axes[0].child_axes:
                    angle=math.radians(CURVATURES[variant])
                    radial=height=0;points=[]
                    for segment in axis.internodes:
                        self.assertLess(segment.bend_angle_deg,0)
                        self.assertLess(abs(segment.bend_angle_deg),12)
                        angle+=math.radians(segment.bend_angle_deg)
                        radial+=segment.length_cm*math.sin(angle)
                        height+=segment.length_cm*math.cos(angle)
                        points.append((radial,height))
                    slope=math.tan(math.radians(CURVATURES[variant]))
                    curvature=(math.tan(math.radians(8))-slope)/2
                    for x,z in points:
                        t=z/height
                        self.assertAlmostEqual(x,height*(slope*t+curvature*t*t),places=8)


if __name__=='__main__':unittest.main()
