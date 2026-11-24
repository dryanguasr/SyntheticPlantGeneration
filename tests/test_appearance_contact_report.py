"""Evidence gates for the visual contact review; no Blender or GPU."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from report_appearance_contact_check import capture_comparability,physical_summary,report,tree_counts


class ContactReportTests(unittest.TestCase):
    def setUp(self):
        self.capture={"effective_profile":{"lighting":{"exposure":0}},
            "lighting_geometry":{"fill":{"type":"AREA","matrix_world":[[1,0,0,0],[0,1,0,-3],[0,0,1,4],[0,0,0,1]]}},
            "light_target_source_sha256":"target"}
        self.camera={"name":"Camera","width":960,"height":720,"lens_mm":55,"matrix_world":[[1,0,0,2]]}

    def test_camera_or_actual_light_change_prevents_comparability(self):
        self.assertEqual(capture_comparability(self.capture,self.capture,self.camera,self.camera),[])
        changed=deepcopy(self.camera);changed["lens_mm"]=54
        self.assertTrue(capture_comparability(self.capture,self.capture,self.camera,changed))
        changed=deepcopy(self.capture);changed["lighting_geometry"]["fill"]["matrix_world"][1][3]=-4
        self.assertTrue(capture_comparability(self.capture,changed,self.camera,self.camera))

    def test_matching_stale_fill_matrices_are_not_accepted(self):
        stale=deepcopy(self.capture)
        stale["lighting_geometry"]["fill"]["matrix_world"]=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]
        self.assertTrue(capture_comparability(stale,stale,self.camera,self.camera))

    def fixture(self):
        return {"morphology":{"fruits":1,"calyces":1,"leaves":1,"flowers":0},
            "mesh":{"tolerate_only_leaf_leaf":True,"status":"valid","physical_collision_count":0,"clearance_violation_count":0},
            "ground":{"version":"plant-evaluated-terrain/2","status":"valid","physical_collision_count":0,"clearance_violation_count":0,"coverage_failure_count":0,
                      "objects":[{"semantic":s} for s in ("fruit","calyx","leaf")]}}

    def test_hidden_fruit_coverage_is_required(self):
        side=self.fixture();self.assertTrue(physical_summary(side)["physically_admitted"])
        side["ground"]["objects"].pop(0)
        result=physical_summary(side)
        self.assertFalse(result["evidence_complete"])
        self.assertFalse(result["physically_admitted"])

    def test_duplicate_residual_fruit_prevents_admission(self):
        side=self.fixture();side["ground"]["objects"].append({"semantic":"fruit"})
        self.assertFalse(physical_summary(side)["physically_admitted"])

    def test_loose_mesh_or_legacy_ground_does_not_imply_admission(self):
        side=self.fixture();side["mesh"]["tolerate_only_leaf_leaf"]=False
        self.assertFalse(physical_summary(side)["physically_admitted"])
        side=self.fixture();side["ground"]["version"]="0.1.0-evaluated-terrain-clearance"
        self.assertFalse(physical_summary(side)["physically_admitted"])

    def test_counts_detect_real_failure_even_if_status_field_says_valid(self):
        side=self.fixture();side["ground"]["coverage_failure_count"]=1
        self.assertFalse(physical_summary(side)["physically_admitted"])

    def test_tree_count_does_not_infer_visible_annotations(self):
        tree={"axes":[{"nodes":[{"leaf":{"id":"l"},"reproductive_unit":{"stage":"flower","fruit":None,"calyx":None}}],"child_axes":[]}]}
        counts=tree_counts(tree)
        self.assertEqual(counts["leaves"],1)
        self.assertEqual(counts["flowers"],1)
        self.assertEqual(counts["fruits"],0)

    def test_complete_report_preserves_pixels_and_cannot_approve_training(self):
        from PIL import Image
        base=Path(__file__).resolve().parents[1]/"outputs/appearance_factorial_20261026/test_tmp"
        base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temporary:
            root=Path(temporary)
            def save(path,value):
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(json.dumps(value),encoding="utf-8")
            digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
            for label in ("before","after"):
                folder=root/label;view=folder/"plant_00_view0_LT";view.mkdir(parents=True)
                snapshot=folder/"source_snapshot"
                module=snapshot/"src/example.py";module.parent.mkdir(parents=True);module.write_text("# unchanged\n")
                runner=snapshot/"scripts/render_appearance_calibration.py";runner.parent.mkdir(parents=True);runner.write_text("# unchanged renderer\n")
                save(folder/"profiles.json",{"purpose":"fixture"})
                tree={"axes":[{"nodes":[{"leaf":{"id":"leaf0"},"reproductive_unit":None}],"child_axes":[]}]}
                tree_path=folder/"plant.json";save(tree_path,tree)
                save(folder/"plants.json",{"plants":[{"index":0,"path":str(tree_path),"sha256":digest(tree_path)}]})
                save(folder/"source_lock.json",{"runner":digest(runner),"sources":{"src/example.py":digest(module)},"assets":"same","profiles":digest(folder/"profiles.json")})
                Image.new("RGB",(20,12),(20,130,40)).save(view/"rgb.png")
                Image.new("RGB",(20,12),(0,0,0)).save(view/"mask_calyx_crisp_v2.png")
                capture={**deepcopy(self.capture),"view_id":"plant_00_view0_LT","kind":"context","plant_index":0,
                    "morphology_sha256":digest(tree_path),"rgb_sha256":digest(view/"rgb.png"),
                    "mask_sha256":digest(view/"mask_calyx_crisp_v2.png"),"assignments":{}}
                save(view/"capture.json",capture);save(view/"camera.json",self.camera);save(view/"annotations.json",{"items":{}})
                save(folder/"plant_00_environment.json",{"seed":5})
                side=self.fixture();side["ground"]["objects"]=[{"semantic":"leaf"}]
                save(folder/"plant_00_mesh_audit.json",side["mesh"]);save(folder/"plant_00_ground_audit.json",side["ground"])
            original=digest(root/"before/plant_00_view0_LT/rgb.png")
            result=report(root/"before",root/"after",root/"review")
            self.assertTrue(result["visual_comparison_verified"])
            self.assertFalse(result["training_eligible"])
            self.assertEqual(result["human_review"],"pending")
            self.assertTrue((root/"review/plant_00_view0_LT_before_after.png").is_file())
            self.assertEqual(digest(root/"before/plant_00_view0_LT/rgb.png"),original)
            with self.assertRaises(FileExistsError):
                report(root/"before",root/"after",root/"review")


if __name__=="__main__":
    unittest.main()
