"""Pure bank contracts; these tests never import bpy or launch a renderer."""
from copy import deepcopy
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"scripts"))
import render_appearance_bank as bank


def temporary_workspace(*, long_paths=False):
    folder = ROOT/'outputs/appearance_factorial_20261026/bank_test_tmp'
    folder.mkdir(parents=True, exist_ok=True)
    if long_paths and sys.platform == "win32":
        folder = Path("\\\\?\\" + str(folder.resolve()))
    return tempfile.TemporaryDirectory(dir=folder)


def candidate(index):
    return dict(view_id=f"view_{index:03d}", scene_id=f"scene_{index%12:02d}",
                instances=[dict(class_id=index%3, min_side_960=(8,24,48,96)[index%4])])


def paired():
    return dict(view_id="test", geometry_sha256="geometry", camera_sha256="camera", assignments_sha256="classes",
                variants={key: dict(geometry_sha256="geometry", camera_sha256="camera", assignments_sha256="classes",
                                    label_sha256="labels", mask_sha256="mask") for key in bank.BANKS})


class BankSelectionTests(unittest.TestCase):
    def test_complete_available_doses_never_upsample(self):
        for count, expected in ((0,[]),(45,[]),(46,[46]),(114,[46]),(115,[46,115]),(229,[46,115]),(230,[46,115,230])):
            self.assertEqual(bank.available_doses(count), expected)
        with self.assertRaises(ValueError):
            bank.available_doses(-1)

    def test_deterministic_nested_scene_balanced_order(self):
        rows = [candidate(i) for i in range(480)]
        target = [1/12]*12
        selected = bank.select_views(rows,target)
        shuffled = deepcopy(rows)
        random.Random(19).shuffle(shuffled)
        self.assertEqual(selected, bank.select_views(shuffled,target))
        self.assertEqual(len(selected),230)
        self.assertEqual(len({r['view_id'] for r in selected}),230)
        for dose in (46,115,230):
            self.assertEqual(selected[:dose],bank.select_views(rows,target,dose))
            counts = bank.Counter(r['scene_id'] for r in selected[:dose])
            self.assertLessEqual(max(counts.values())-min(counts.values()),1)

    def test_selection_never_duplicates_or_exceeds_camera_limit(self):
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            bank.select_views([candidate(0),candidate(0)],[1/12]*12)
        with self.assertRaisesRegex(ValueError,"budget"):
            bank.select_views([candidate(i) for i in range(481)],[1/12]*12)
        self.assertEqual(bank.select_views([], [1/12]*12),[])

    def test_empty_masks_not_used_to_fabricate_diversity(self):
        rows = [candidate(i) for i in range(47)]
        rows[0]['instances'] = []
        rows[1]['instances'] = []
        selected = bank.select_views(rows,[1/12]*12)
        self.assertEqual(len(selected),45)
        self.assertEqual(bank.available_doses(len(selected)),[])

    def test_size_mismatch_is_descriptive_and_density_not_gate(self):
        row = candidate(1)
        row['instances'] = [dict(class_id=2,min_side_960=.5)]*100
        self.assertEqual(bank.select_views([row],[1/12]*12),[row])

    def test_joint_distribution_and_exact_boundaries(self):
        instances = [dict(class_id=c,min_side_960=size) for c in range(3) for size in (15,16,32,64)]
        self.assertEqual(bank.reference_target(instances),[1/12]*12)
        with self.assertRaises(ValueError):
            bank.reference_target([dict(class_id=4,min_side_960=32)])

    def test_capture_dimensions_preserve_training_aspect(self):
        self.assertEqual(bank.capture_dimensions(1920,1080),(960,540))
        self.assertEqual(bank.capture_dimensions(1080,1920),(540,960))
        self.assertEqual(bank.capture_dimensions(2048,1536),(960,720))
        with self.assertRaises(ValueError):
            bank.capture_dimensions(0,1080)


class AnnotationPairTests(unittest.TestCase):
    def test_all_visible_fragments_and_boundary_boxes_retained(self):
        annotation = dict(items={
            '0':dict(semantic_class='background',visible_pixels=190),
            '1':dict(instance_id='plant:u1',semantic_class='calyx',visible_pixels=1,bbox_xywh=[0,0,1,1]),
            '2':dict(instance_id='plant:u2',semantic_class='calyx',visible_pixels=4,bbox_xywh=[18,8,2,2]),
            '3':dict(instance_id='plant:u3',semantic_class='calyx',visible_pixels=0,bbox_xywh=None)})
        assignments = {f'plant:u{i}':dict(class_id=i-1) for i in range(1,4)}
        labels, instances = bank.labels_from_mask(annotation,assignments,20,10)
        self.assertEqual(len(labels.splitlines()),2)
        self.assertEqual([r['instance_id'] for r in instances],['plant:u1','plant:u2'])
        self.assertEqual(list(map(float,labels.splitlines()[0].split())),[0,.025,.05,.05,.1])
        self.assertEqual(list(map(float,labels.splitlines()[1].split())),[1,.95,.9,.1,.2])
        self.assertEqual(instances[0]['min_side_960'],48)
        self.assertIn('mask_box_fill_ratio', instances[0])
        self.assertNotIn('occlusion',instances[0])

    def test_unknown_instance_cannot_be_silently_unlabelled(self):
        annotation = dict(items={'1':dict(instance_id='unknown',semantic_class='calyx',visible_pixels=1,bbox_xywh=[0,0,1,1])})
        with self.assertRaisesRegex(ValueError,'assignment'):
            bank.labels_from_mask(annotation,{},20,10)

    def test_bad_box_or_duplicate_instance_fails(self):
        item = dict(instance_id='unit',semantic_class='calyx',visible_pixels=1,bbox_xywh=[19,9,2,2])
        with self.assertRaisesRegex(ValueError,'box'):
            bank.labels_from_mask(dict(items={'1':item}),{'unit':dict(class_id=0)},20,10)
        item['bbox_xywh']=[0,0,1,1]
        with self.assertRaisesRegex(ValueError,'duplicate'):
            bank.labels_from_mask(dict(items={'1':item,'2':item}),{'unit':dict(class_id=0)},20,10)

    def test_visual_banks_require_identical_geometry_camera_masks_labels_classes(self):
        self.assertTrue(bank.validate_pair(paired()))
        for key in ('geometry_sha256','camera_sha256','assignments_sha256','label_sha256','mask_sha256'):
            invalid = paired()
            invalid['variants']['L'][key] = 'changed'
            with self.assertRaisesRegex(ValueError,'Unpaired'):
                bank.validate_pair(invalid)
        invalid = paired()
        del invalid['variants']['LT']
        with self.assertRaisesRegex(ValueError,'Incomplete'):
            bank.validate_pair(invalid)

    def test_actual_artifact_hashes_checked(self):
        with temporary_workspace() as folder:
            path = Path(folder)/'artifact'
            path.write_bytes(b'original')
            view = paired()
            for row in view['variants'].values():
                for key in ('image','label','mask'):
                    row[key] = str(path)
                    row[key+'_sha256'] = bank.sha(path)
            bank.verify_view_files(view)
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'Changed paired'):
                bank.verify_view_files(view)


class ReviewGateTests(unittest.TestCase):
    def test_no_bank_mutation_or_process_without_human_review(self):
        with temporary_workspace() as folder, patch.object(bank.subprocess,'Popen') as launch:
            root = Path(folder)
            with self.assertRaises(FileNotFoundError):
                bank.main(['--root',str(root),'--blender','nonexistent.exe'])
            self.assertEqual(list(root.iterdir()),[])
            launch.assert_not_called()

    def test_rejected_or_changed_profile_review_fails_closed(self):
        with temporary_workspace() as folder, patch.object(bank.subprocess,'Popen') as launch:
            root = Path(folder)
            bank.write(root/'profiles.json',dict(version='test'))
            bank.write(root/'review_lock.json',dict(approved=False,human_review='pending'))
            with self.assertRaisesRegex(ValueError,'Human class review'):
                bank.main(['--root',str(root),'--worker'])
            bank.write(root/'review_lock.json',dict(approved=True,human_review='approved',profiles_sha256='wrong'))
            with self.assertRaisesRegex(ValueError,'profiles changed'):
                bank.main(['--root',str(root),'--worker'])
            self.assertFalse((root/'banks').exists())
            launch.assert_not_called()

    def test_launcher_propagates_blender_python_failure(self):
        with temporary_workspace() as folder, patch.object(bank.subprocess,'Popen') as launch, \
             patch.object(bank,'process_identity',return_value={'pid':123,'created':'test'}):
            root = Path(folder)
            bank.write(root/'profiles.json',dict(version='test'))
            bank.write(root/'review_lock.json',dict(approved=True,human_review='approved',profiles_sha256=bank.sha(root/'profiles.json')))
            executable = root/'blender.exe'
            executable.touch()
            launch.return_value.pid = 123
            launch.return_value.poll.return_value = 0
            launch.return_value.returncode = 0
            bank.main(['--root',str(root),'--blender',str(executable)])
            command = launch.call_args.args[0]
            self.assertEqual(command[command.index('--python-exit-code')+1],'1')
            self.assertEqual(launch.call_args.kwargs['creationflags'],bank.subprocess.CREATE_NO_WINDOW if bank.os.name=='nt' else 0)

    def test_budget_watchdog_stops_only_owned_blender_and_preserves_logs(self):
        with temporary_workspace() as folder, patch.object(bank.subprocess,'Popen') as launch, \
             patch.object(bank,'process_identity',return_value={'pid':123,'created':'test'}), \
             patch.object(bank,'remaining_budget',side_effect=[100,0]), patch.object(bank,'awake_seconds',return_value=0):
            process = launch.return_value
            process.pid = 123
            process.poll.side_effect = lambda: -15 if process.terminate.called else None
            with self.assertRaisesRegex(ValueError,'budget exhausted'):
                bank.launch_worker(Path(folder),Path('fake.exe'))
            process.terminate.assert_called_once()
            process.wait.assert_called_once_with(timeout=10)
            records = list((Path(folder)/'banks/launches').glob('*/process.json'))
            self.assertEqual(len(records),1)
            record = bank.read(records[0])
            self.assertEqual(record['state'],'failed')
            self.assertTrue(record['child_confirmed_stopped'])
            self.assertTrue(Path(record['stdout']).exists())
            self.assertTrue(Path(record['stderr']).exists())

    def test_child_startup_hang_does_not_wait_without_accounting_forever(self):
        with temporary_workspace() as folder, patch.object(bank.subprocess,'Popen') as launch, \
             patch.object(bank,'process_identity',return_value={'pid':123,'created':'test'}), \
             patch.object(bank,'remaining_budget',return_value=100), patch.object(bank,'awake_seconds',side_effect=[0,181]):
            process = launch.return_value
            process.pid = 123
            process.poll.side_effect = lambda: -15 if process.terminate.called else None
            with self.assertRaisesRegex(ValueError,'ledger'):
                bank.launch_worker(Path(folder),Path('fake.exe'))
            process.terminate.assert_called_once()


class ReviewedPlantContractTests(unittest.TestCase):
    def profiles(self, preset="trained_trellis_audit_v2"):
        from uchuva_lsystem.parameters import get_morphology_parameters
        parameters = get_morphology_parameters(preset)
        return dict(plant_preset=preset, load_policy="architecture_driven",
                    plant_parameters_sha256=bank.canonical_hash(parameters)), parameters

    def test_registered_versioned_architecture_presets_are_resolved_not_hardcoded(self):
        profile, parameters = self.profiles()
        contract = bank.reviewed_plant_contract(profile)
        self.assertEqual(contract["preset_name"], "trained_trellis_audit_v2")
        self.assertEqual(contract["parameters_sha256"], bank.canonical_hash(parameters))
        # A registered derived profile sharing the audited morphology contract
        # must pass without adding its literal name to the renderer.
        derived = deepcopy(parameters)
        derived.update(preset_name="trained_trellis_bush_audit_v3", architecture_profile_version="bush-development/1")
        derived["axis"]["branch_node_count_range"]["max"] += 1
        profile.update(plant_preset=derived["preset_name"], plant_parameters_sha256=bank.canonical_hash(derived))
        with patch("uchuva_lsystem.parameters.get_morphology_parameters", return_value=derived):
            resolved = bank.reviewed_plant_contract(profile)
        self.assertEqual(resolved["parameters"], derived)
        self.assertEqual(resolved["architecture_profile_version"], "bush-development/1")

    def test_missing_reviewed_hash_legacy_quota_and_unvalidated_contract_rejected(self):
        profile, original = self.profiles()
        profile.pop("plant_parameters_sha256")
        with self.assertRaisesRegex(ValueError, "hash is missing"):
            bank.reviewed_plant_contract(profile)
        for field in ("quota", "policy", "contract", "radius"):
            parameters = deepcopy(original)
            if field == "quota":
                parameters["reproduction"]["target_reproductive_units_range"]["active"] = True
            elif field == "policy":
                parameters["reproduction"]["load_policy"]["value"] = "legacy_fruiting_range"
            elif field == "contract":
                parameters["morphology_contract_version"] = "unvalidated/99"
            else:
                parameters["internode"]["radius_cm_by_order"].pop("3")
            profile["plant_parameters_sha256"] = bank.canonical_hash(parameters)
            with patch("uchuva_lsystem.parameters.get_morphology_parameters", return_value=parameters), self.assertRaises(ValueError):
                bank.reviewed_plant_contract(profile)
        with self.assertRaisesRegex(ValueError, "versioned"):
            bank.reviewed_plant_contract(dict(plant_preset="trained_trellis", load_policy="architecture_driven"))

    def test_prepared_plants_keep_input_and_effective_snapshot_hashes(self):
        profile, _ = self.profiles()
        contract = bank.reviewed_plant_contract(profile)
        with temporary_workspace() as folder:
            plants, records = bank.prepare_plants(20261026, "scene_00", 0,
                [dict(class_id=c) for c in range(3)], Path(folder), plant_contract=contract)
            self.assertEqual(len(plants), 2)
            for plant, record in zip(plants, records):
                self.assertEqual(record["input_parameters_sha256"], profile["plant_parameters_sha256"])
                self.assertEqual(record["effective_parameters_sha256"], bank.canonical_hash(plant.metadata["effective_parameters"]))
                self.assertEqual(record["preset_name"], profile["plant_preset"])
                self.assertEqual(record["counts"], plant.metadata["reproductive_counts_by_stage"]["generated"])
                self.assertNotEqual(record["validation"], "invalid")
            changed = deepcopy(contract)
            changed["parameters"]["axis"]["main_node_count"]["value"] += 1
            with self.assertRaisesRegex(ValueError, "input parameters changed"):
                bank.prepare_plants(1, "scene_01", 0, [dict(class_id=0)], Path(folder), plant_contract=changed)

    def test_registered_bush_v3_generates_from_its_reviewed_parameter_snapshot(self):
        profile, parameters = self.profiles("trained_trellis_bush_audit_v3")
        contract = bank.reviewed_plant_contract(profile)
        with temporary_workspace() as folder:
            plants, records = bank.prepare_plants(20261026, "scene_02", 0,
                [dict(class_id=c) for c in range(3)], Path(folder), plant_contract=contract)
            for plant, record in zip(plants, records):
                self.assertEqual(record["preset_name"], "trained_trellis_bush_audit_v3")
                self.assertEqual(record["input_parameters_sha256"], bank.canonical_hash(parameters))
                self.assertEqual(plant.metadata["effective_parameters"]["axis"]["branch_node_count_range"],
                                 parameters["axis"]["branch_node_count_range"])
                self.assertEqual(record["counts"], plant.metadata["reproductive_counts_by_stage"]["generated"])
                self.assertNotEqual(record["validation"], "invalid")

    def test_source_freeze_includes_derived_parameters_and_reviewed_profile(self):
        profile, parameters = self.profiles()
        with temporary_workspace(long_paths=True) as folder:
            root = Path(folder)
            for relative, value in (("profiles.json", profile), ("review_lock.json", {}), ("real_manifest.json", {}),
                                    ("references/real_instances.json", {}), ("asset_manifest.json", {})):
                bank.write(root/relative, value)
            bank.write(root/"texture_assets.json", dict(files={}, manifest=str(root/"asset_manifest.json"),
                                                        manifest_sha256=bank.sha(root/"asset_manifest.json")))
            signature = bank.source_snapshot(root, root/"profiles.json")
            contract_path = root/"banks/plant_contract.json"
            self.assertEqual(signature["plant_contract_sha256"], bank.sha(contract_path))
            self.assertEqual(bank.read(contract_path)["parameters"], parameters)
            for path in (contract_path, root/"profiles.json", ROOT/"src/uchuva_lsystem/parameters.py"):
                self.assertEqual(signature["files"][str(path.resolve())], bank.sha(path))
            changed = deepcopy(parameters)
            changed["axis"]["main_node_count"]["value"] += 1
            with patch("uchuva_lsystem.parameters.get_morphology_parameters", return_value=changed):
                with self.assertRaisesRegex(ValueError, "resolved plant parameters changed"):
                    bank.source_snapshot(root, root/"profiles.json")

    def test_source_freeze_preserves_bytes_beyond_windows_legacy_path_limit(self):
        profile, _ = self.profiles()
        with temporary_workspace(long_paths=True) as folder:
            repository = Path(folder)/"long_source_fixture"
            while len(str(repository/"src/uchuva_lsystem/parameters.py")) <= 280:
                repository /= "nested_source_directory"
            source_bytes = b"# source fixture: preserve CRLF and exact bytes\r\nVALUE = 7\r\n"
            for relative in ("scripts/render_appearance_bank.py", "scripts/appearance_campaign.py",
                             "scripts/report_appearance_bank.py", "scripts/execute_appearance_pilot.py",
                             "src/uchuva_lsystem/parameters.py"):
                source = repository/relative
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_bytes(source_bytes)
            root = repository/"outputs/source_freeze"
            for relative, value in (("profiles.json", profile), ("review_lock.json", {}),
                                    ("real_manifest.json", {}), ("references/real_instances.json", {}),
                                    ("asset_manifest.json", {})):
                bank.write(root/relative, value)
            bank.write(root/"texture_assets.json", dict(files={}, manifest=str(root/"asset_manifest.json"),
                                                        manifest_sha256=bank.sha(root/"asset_manifest.json")))
            source = repository/"src/uchuva_lsystem/parameters.py"
            snapshot = root/"banks/source_snapshot/src/uchuva_lsystem/parameters.py"
            self.assertGreater(len(str(source)), 260)
            self.assertGreater(len(str(snapshot)), 260)
            with patch.object(bank, "REPO", repository), \
                    patch.object(bank, "__file__", str(repository/"scripts/render_appearance_bank.py")), \
                    patch.object(bank.shutil, "copy2", side_effect=AssertionError("Metadata copying is not needed")):
                signature = bank.source_snapshot(root, root/"profiles.json")
                self.assertEqual(snapshot.read_bytes(), source_bytes)
                self.assertEqual(bank.sha(snapshot), signature["files"][str(source.resolve())])
                self.assertEqual(bank.source_snapshot(root, root/"profiles.json"), signature)
                snapshot.write_bytes(b"changed snapshot bytes")
                with self.assertRaisesRegex(ValueError, "Snapshot differs"):
                    bank.source_snapshot(root, root/"profiles.json")

    def test_richer_canopy_cannot_relax_physical_or_terrain_gate(self):
        mesh = dict(status="valid", tolerate_only_leaf_leaf=True, physical_collision_count=0,
                    clearance_violation_count=0, soft_occupancy_intersection_count=100)
        ground = dict(status="valid", physical_collision_count=0)
        self.assertTrue(bank.scene_physically_admitted(mesh, ground))
        for field, value in (("physical_collision_count", 1), ("clearance_violation_count", 1),
                             ("tolerate_only_leaf_leaf", False), ("status", "invalid")):
            self.assertFalse(bank.scene_physically_admitted(dict(mesh, **{field:value}), ground))
        self.assertFalse(bank.scene_physically_admitted(mesh, dict(ground, physical_collision_count=1)))
        self.assertFalse(bank.scene_physically_admitted(mesh, {}))


if __name__ == '__main__':
    unittest.main()
