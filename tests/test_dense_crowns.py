"""Regression contracts for individual density without denser planting."""
import copy
import statistics
import unittest
import tempfile
from pathlib import Path
from uchuva_lsystem.sparse_pilot import sparse_morphology_parameters, prepare_plant, walk_axes, create_sparse_scene
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.collisions import resolve_global_collisions, build_scene_proxies

class DenseCrownTests(unittest.TestCase):
    def test_individual_material_catalog_preserves_geometry(self):
        from uchuva_gazebo.field import prepare_mesh_assets
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'leaf.obj'
            path.write_text('o leaf\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
            prepare_mesh_assets(folder,[{'uri':'meshes/leaf.obj','color':(.1,.3,.1,1)}],individual_material_files=True)
            self.assertIn('mtllib leaf.mtl',path.read_text())
            self.assertIn('f 1//1 2//1 3//1',path.read_text())
            self.assertEqual((Path(folder)/'leaf.mtl').read_text().count('newmtl'),1)

    def test_reproducible_density_and_reproduction_policy(self):
        oldp=sparse_morphology_parameters();newp=sparse_morphology_parameters('individual_dense_crown_v3')
        self.assertEqual(oldp['leaf'],newp['leaf'])
        self.assertEqual(oldp['reproduction'],newp['reproduction'])
        counts=[]
        for seed in (23092600,23092612,23092623):
            old=generate_morphology_tree(seed,oldp)
            new=prepare_plant(generate_morphology_tree(seed,newp))
            self.assertEqual(new.to_dict(),prepare_plant(generate_morphology_tree(seed,newp)).to_dict())
            self.assertEqual(new.to_dict(),Plant.from_dict(new.to_dict()).to_dict())
            axes=list(walk_axes(new.axes));ids=[n.id for a in axes for n in a.nodes]
            self.assertEqual(len(ids),len(set(ids)))
            for a in axes:
                for child in a.child_axes:
                    self.assertEqual(child.order,a.order+1)
                    self.assertIn(child.parent_node_id,[n.id for n in a.nodes])
            counts.append((len(list(walk_axes(old.axes))),len(axes),old.node_count(),new.node_count()))
        self.assertGreater(statistics.median(r[1] for r in counts),2*statistics.median(r[0] for r in counts))
        self.assertGreater(statistics.median(r[3] for r in counts),2*statistics.median(r[2] for r in counts))

    def test_old_default_and_invalid_selection(self):
        self.assertEqual(sparse_morphology_parameters(),sparse_morphology_parameters('sparse_overhead_dense_crown_v2'))
        with self.assertRaises(ValueError):sparse_morphology_parameters('missing')

    def test_overlap_policy_preserves_organs_and_layout(self):
        scene=create_sparse_scene(1);scene.plant_instances=scene.plant_instances[:1];scene.support_system=None
        params=sparse_morphology_parameters();params['axis']['main_node_count']['value']=4
        plant=prepare_plant(generate_morphology_tree(100,params));count=plant.node_count()
        layout=copy.deepcopy(scene.to_dict())
        kinds={p.proxy_id:p.kind for p in build_scene_proxies(scene,{'plant_00':plant})}
        result=resolve_global_collisions(scene,{'plant_00':plant},iterations=1,optimize_poses=False,allow_leaf_leaf_overlap=True)
        self.assertEqual(count,plant.node_count());self.assertEqual(layout,scene.to_dict())
        self.assertTrue(result['allow_leaf_leaf_overlap'])
        for adjustment in result['adjustments']:
            self.assertFalse(all(kinds[k]=='leaf' for k in adjustment['trigger_pair']))

if __name__=='__main__':unittest.main()
