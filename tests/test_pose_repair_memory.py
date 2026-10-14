import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uchuva_lsystem.blender_pose_repair import _remove_pose_objects


class Mesh:
    def __init__(self,users):self.users=users


class Curve:
    def __init__(self,users):self.users=users


class PoseMemoryTests(unittest.TestCase):
    def test_trial_datablock_released_but_shared_geometry_preserved(self):
        removed_meshes=[];removed_curves=[]
        def remove_object(obj,do_unlink):obj.data.users-=1
        mesh=Mesh(1);shared=Mesh(2);curve=Curve(1)
        fake=SimpleNamespace(types=SimpleNamespace(Mesh=Mesh,Curve=Curve),data=SimpleNamespace(
            objects=SimpleNamespace(remove=remove_object),meshes=SimpleNamespace(remove=removed_meshes.append),
            curves=SimpleNamespace(remove=removed_curves.append)))
        with patch.dict(sys.modules,bpy=fake):
            _remove_pose_objects([SimpleNamespace(data=mesh),SimpleNamespace(data=shared),SimpleNamespace(data=curve)])
        self.assertEqual(removed_meshes,[mesh]);self.assertEqual(shared.users,1)
        self.assertEqual(removed_curves,[curve])


if __name__=='__main__':unittest.main()
