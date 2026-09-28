"""Re-render only identity masks from preserved Blender scenes; keep prior evidence."""
import argparse
import json
from pathlib import Path
import sys
import time
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from uchuva_lsystem.blender_annotations import render_crisp_calyx_annotations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    for folder in sorted(args.root.resolve().glob("scene_*")):
        start = time.perf_counter()
        bpy.ops.wm.open_mainfile(filepath=str(folder/"cultivation.blend"))
        for path in sorted(folder.glob("*/capture.json")):
            original = path.with_name("capture_eevee_diagnostic.json")
            if (path.parent/"mask_calyx_crisp_v2.png").exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            camera = bpy.data.objects[path.parent.name]
            mask = render_crisp_calyx_annotations(camera,path.parent,width=1280,height=960)
            if not original.exists(): original.write_bytes(path.read_bytes())
            path.with_name("capture_before_crisp_v2.json").write_bytes(path.read_bytes())
            data["mask"] = mask
            data["mask_correction"] = "single_sample_identity_raster_no_RGB_change"
            path.write_text(json.dumps(data,indent=2),encoding="utf-8")
            print(f"MASK {folder.name}/{path.parent.name}",flush=True)
        (folder/"mask_repair.json").write_text(json.dumps({"seconds":time.perf_counter()-start,
            "engine":"BLENDER_WORKBENCH","anti_aliasing":"OFF","originals_preserved":True},indent=2),encoding="utf-8")


if __name__=="__main__": main()
