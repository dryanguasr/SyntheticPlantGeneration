"""Generate only the pre-reserved final morphologies, without rendering or metrics."""
import argparse,json,random,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import write,check_deadline,CLASSES
from uchuva_lsystem.sparse_pilot import sparse_morphology_parameters,prepare_plant,walk_axes
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.bouquet import train_bouquet
from uchuva_lsystem.clearance_bouquet import clear_branch_axes
from uchuva_lsystem.validation import validate_morphology_tree


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    run=json.loads((a.root/'run.json').read_text())
    for seed in run['final_seeds']:
        check_deadline(a.root);path=a.root/'reserved_morphologies'/f'{seed}.json'
        if path.exists():continue
        plant=train_bouquet(prepare_plant(generate_morphology_tree(seed,sparse_morphology_parameters('individual_dense_crown_v3'))))
        rng=random.Random(seed+719)
        for axis in walk_axes(plant.axes):
            for node in axis.nodes:
                if node.leaf:
                    node.leaf.curl=rng.uniform(.12,.32);node.leaf.twist_deg=rng.uniform(-22,22);node.leaf.insertion_angle_deg=rng.uniform(95,155)
                    node.leaf.provenance['appearance_cycle_pose']='manual_initial_guess_preserved_from_previous_campaign'
        plant.metadata['segmentation_contract']=dict(version='localization-pilot/1.0',classes=CLASSES,green_in_pintona=True,agronomic_maturity='unknown',group='final')
        clearance=clear_branch_axes(plant)
        write(path,plant.to_dict());write(path.with_name(f'{seed}_validation.json'),dict(seed=seed,parameter_preset=plant.parameter_preset,**validate_morphology_tree(plant),axis_clearance=clearance))
        print('RESERVED_MORPHOLOGY',seed,'unresolved_axes',len(clearance['unresolved']),flush=True)


if __name__=='__main__':main()
