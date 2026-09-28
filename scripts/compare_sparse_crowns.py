"""Measure foliage changes between preserved pilots, without claiming field calibration."""
import argparse
import json
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.sparse_pilot import walk_axes


def counts(plant_dict):
    axes=list(walk_axes(Plant.from_dict(plant_dict).axes))
    leaves=[n.leaf for a in axes for n in a.nodes if n.leaf]
    return {"axes":len(axes),"leaves":len(leaves),
            "leaf_area_proxy_cm2":sum(l.length_cm*l.width_cm for l in leaves),
            "calyxes":sum(bool(n.reproductive_unit and n.reproductive_unit.calyx) for a in axes for n in a.nodes)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old",type=Path,required=True)
    parser.add_argument("--new",type=Path,required=True)
    args=parser.parse_args()
    rows=[]
    for folder in sorted(args.new.glob("scene_*")):
        old=json.loads((args.old/folder.name/"input.json").read_text())
        new=json.loads((folder/"input.json").read_text())
        assert len(old["plants"])==len(new["plants"])==36
        assert [p["position"] for p in old["scene"]["plant_instances"]]==[p["position"] for p in new["scene"]["plant_instances"]]
        for identifier,plant in new["plants"].items():
            before,after=counts(old["plants"][identifier]),counts(plant)
            rows.append({"scene":folder.name,"plant_id":identifier,"old":before,"new":after,
                         "leaf_count_ratio":after["leaves"]/before["leaves"]})
    totals={revision:{key:sum(r[revision][key] for r in rows) for key in ("axes","leaves","calyxes","leaf_area_proxy_cm2")}
            for revision in ("old","new")}
    result={"plants":len(rows),"totals":totals,
            "ratios":{key:totals["new"][key]/totals["old"][key] for key in totals["old"]},
            "minimum_plant_leaf_ratio":min(r["leaf_count_ratio"] for r in rows),
            "field_layout":"unchanged_6x6_positions",
            "status":"synthetic_geometry_comparison_not_field_validation",
            "area_warning":"Length times width is a rectangular proxy, not measured leaf surface or projected coverage.",
            "per_plant":rows}
    (args.new/"density_comparison.json").write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!="per_plant"}))


if __name__=="__main__":main()
