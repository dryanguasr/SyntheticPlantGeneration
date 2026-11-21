import unittest
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.sparse_pilot import prepare_plant,sparse_morphology_parameters
from uchuva_lsystem.foliage_reference_pilot import foliage_reference_pilot
from uchuva_lsystem.canopy_preference_pilot import canopy_preference_pilot,node_positions
class FoliageReferenceTest(unittest.TestCase):
 def test_splay_preserves_everything_except_axis_directions_and_metadata(self):
  from uchuva_lsystem.foliage_reference_pilot import splay_branch_junctions
  import copy
  source=foliage_reference_pilot(prepare_plant(generate_morphology_tree(814144,sparse_morphology_parameters('individual_dense_crown_v3'))))
  trial=splay_branch_junctions(source)
  self.assertTrue(trial.metadata['junction_splay_review']['changes'])
  a=copy.deepcopy(source.to_dict());b=copy.deepcopy(trial.to_dict())
  b['metadata'].pop('junction_splay_review')
  def strip(axis):
   axis.pop('resolved_direction')
   for child in axis['child_axes']:strip(child)
  for p in [a,b]:
   for axis in p['axes']:strip(axis)
  self.assertEqual(a,b)

 def test_azimuth_spread_changes_only_leaf_direction(self):
  from uchuva_lsystem.foliage_reference_pilot import spread_leaf_azimuths
  source=foliage_reference_pilot(prepare_plant(generate_morphology_tree(814144,sparse_morphology_parameters('individual_dense_crown_v3'))))
  trial=spread_leaf_azimuths(source,140)
  self.assertEqual(trial.to_dict(),spread_leaf_azimuths(source,140).to_dict())
  self.assertEqual(node_positions(source)[0],node_positions(trial)[0])
  for key,axis in node_positions(source)[1].items():
   for old,new in zip(axis.nodes,node_positions(trial)[1][key].nodes):
    self.assertEqual(old.reproductive_unit,new.reproductive_unit)
    if old.leaf:
     a=old.leaf.to_dict();b=new.leaf.to_dict()
     a.pop('azimuth_deg');b.pop('azimuth_deg')
     b['provenance'].pop('azimuth_before_spread_deg')
     self.assertEqual(a,b)

 def test_optional_graded_material_and_historical_fallback(self):
  from uchuva_lsystem.blender_geometry import _review_leaf_material
  m={'leaf':'green','leaf_senescent':'yellow'}
  self.assertEqual(_review_leaf_material(.21,m),'green')
  self.assertEqual(_review_leaf_material(.22,m),'yellow')
  m['leaf_senescence_2']='blend20'
  self.assertEqual(_review_leaf_material(.22,m),'blend20')
 def test_leaf_senescence_option_changes_no_geometry_or_reproductive_state(self):
  source=prepare_plant(generate_morphology_tree(814144,sparse_morphology_parameters('individual_dense_crown_v3')))
  baseline=foliage_reference_pilot(source)
  trial=foliage_reference_pilot(source,preserve_leaf_senescence=True)
  self.assertEqual(node_positions(baseline)[0],node_positions(trial)[0])
  changed=0
  for key,axis in node_positions(baseline)[1].items():
   for old,new in zip(axis.nodes,node_positions(trial)[1][key].nodes):
    self.assertEqual(old.reproductive_unit,new.reproductive_unit)
    if old.leaf:
     old_dict=old.leaf.to_dict();new_dict=new.leaf.to_dict()
     changed+=old_dict.pop('senescence')!=new_dict.pop('senescence')
     self.assertEqual(old_dict,new_dict)
  self.assertGreater(changed,0)
 def test_junction_contract_matches_tree_after_stagger_and_roundtrip(self):
  from uchuva_lsystem.foliage_reference_pilot import stagger_secondary_branches
  from uchuva_lsystem.morphology import Plant
  for seed in (814144,814146):
   p=stagger_secondary_branches(foliage_reference_pilot(prepare_plant(generate_morphology_tree(seed,sparse_morphology_parameters('individual_dense_crown_v3')))))
   expected={(a.id,c.parent_node_id,c.id) for a in node_positions(p)[1].values() for c in a.child_axes}
   actual={(j['parent_axis_id'],j['node_id'],c) for j in p.metadata['branch_junction_contract']['junctions'] for c in j['child_axis_ids']}
   self.assertEqual(actual,expected)
   self.assertEqual(Plant.from_dict(p.to_dict()).metadata['branch_junction_contract'],p.metadata['branch_junction_contract'])
 def test_petiole_trial_preserves_all_other_leaf_fields_and_organs(self):
  from uchuva_lsystem.foliage_reference_pilot import scale_petiole_lengths
  p=foliage_reference_pilot(prepare_plant(generate_morphology_tree(814144,sparse_morphology_parameters('individual_dense_crown_v3'))))
  trial=scale_petiole_lengths(p,.6)
  self.assertEqual(node_positions(p)[0],node_positions(trial)[0])
  for key,axis in node_positions(p)[1].items():
   for old,new in zip(axis.nodes,node_positions(trial)[1][key].nodes):
    self.assertEqual(old.reproductive_unit,new.reproductive_unit)
    if old.leaf:
     self.assertAlmostEqual(new.leaf.petiole_length_cm,old.leaf.petiole_length_cm*.6)
     for field in ('id','node_id','length_cm','width_cm','insertion_angle_deg','azimuth_deg'):
      self.assertEqual(getattr(old.leaf,field),getattr(new.leaf,field))
    else:self.assertIsNone(new.leaf)
 def test_spacing_preserves_structure_reproduction_and_terminal_leaves(self):
  from uchuva_lsystem.foliage_reference_pilot import space_secondary_leaves
  source=prepare_plant(generate_morphology_tree(814146,sparse_morphology_parameters('individual_dense_crown_v3')))
  plant=foliage_reference_pilot(source)
  spaced=space_secondary_leaves(plant,.55)
  self.assertEqual(spaced.to_dict(),space_secondary_leaves(plant,.55).to_dict())
  self.assertEqual(node_positions(plant)[0],node_positions(spaced)[0])
  self.assertEqual(plant.reproductive_unit_count(),spaced.reproductive_unit_count())
  self.assertGreater(len(spaced.metadata['leaf_spacing_review']['removed_leaf_ids']),0)
  original_axes=node_positions(plant)[1]
  for axis in node_positions(spaced)[1].values():
   if not axis.child_axes:self.assertIsNotNone(axis.nodes[-1].leaf)
   for old,new in zip(original_axes[axis.id].nodes,axis.nodes):
    if axis.order<2:self.assertEqual(old.leaf,new.leaf)
    self.assertEqual(old.reproductive_unit,new.reproductive_unit)
  self.assertNotEqual(plant.to_dict(),spaced.to_dict())
 def test_refill_preserves_geometry_and_reproduction(self):
  for seed in (814144,814145,814146):
   source=prepare_plant(generate_morphology_tree(seed,sparse_morphology_parameters('individual_dense_crown_v3')))
   previous=canopy_preference_pilot(source);p=foliage_reference_pilot(source)
   self.assertEqual(node_positions(previous)[0],node_positions(p)[0])
   self.assertEqual(previous.reproductive_unit_count(),p.reproductive_unit_count())
   self.assertEqual(p.to_dict(),foliage_reference_pilot(source).to_dict())
   ids=set();terminal=0
   for axis in node_positions(p)[1].values():
    if not axis.child_axes:
     self.assertIsNotNone(axis.nodes[-1].leaf)
     self.assertTrue(axis.nodes[-1].leaf.provenance['terminal_endpoint'])
    for node in axis.nodes:
     if node.leaf:
      self.assertNotIn(node.leaf.id,ids);ids.add(node.leaf.id)
      self.assertEqual(node.leaf.node_id,node.id)
      terminal+=node.leaf.provenance.get('terminal_leaf',False)
   self.assertGreater(terminal,0)
   self.assertGreater(p.metadata['foliage_reference_pilot']['leaves_added'],0)
 def test_pointed_outline_preserves_broad_base(self):
  from uchuva_lsystem.blender_geometry import _leaf_shape_profile
  for t in (.1,.3,.6):
   self.assertEqual(_leaf_shape_profile('ovate_cordate_acuminate',t),_leaf_shape_profile('ovate_cordate',t))
  widths=[_leaf_shape_profile('ovate_cordate_acuminate',t)[0] for t in (.7,.8,.9,.98,1)]
  self.assertTrue(all(a>b for a,b in zip(widths,widths[1:])))
  self.assertEqual(widths[-1],0)
  self.assertLess(widths[-2],.05)
 def test_basal_foliage_and_terminal_leaf_without_random_refill(self):
  source=prepare_plant(generate_morphology_tree(814144,sparse_morphology_parameters('individual_dense_crown_v3')))
  plant=foliage_reference_pilot(source)
  basal=[n.leaf for a in node_positions(plant)[1].values() if a.order==1 for n in a.nodes if n.leaf]
  self.assertGreater(len(basal),0)
  plant=foliage_reference_pilot(source,density=0)
  for a in node_positions(plant)[1].values():
   if not a.child_axes:self.assertIsNotNone(a.nodes[-1].leaf)
 def test_staggered_connections_preserve_organs(self):
  from uchuva_lsystem.foliage_reference_pilot import stagger_secondary_branches
  for seed in (814144,814146):
   p=foliage_reference_pilot(prepare_plant(generate_morphology_tree(seed,sparse_morphology_parameters('individual_dense_crown_v3'))))
   q=stagger_secondary_branches(p)
   self.assertEqual(p.reproductive_unit_count(),q.reproductive_unit_count())
   self.assertEqual(q.to_dict(),stagger_secondary_branches(p).to_dict())
   old=node_positions(p)[1];new=node_positions(q)[1]
   self.assertEqual({n.leaf.id for a in old.values() for n in a.nodes if n.leaf},{n.leaf.id for a in new.values() for n in a.nodes if n.leaf})
   for a in new.values():
    for child in a.child_axes:
     i=next(i for i,n in enumerate(a.nodes) if n.id==child.parent_node_id)
     self.assertLess(child.internodes[0].radius_cm,a.internodes[i].radius_cm)
if __name__=='__main__':unittest.main()
