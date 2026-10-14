"""Comprueba que los cuatro inventarios de eliminación quedaron ejecutados."""

import json

from prune_historical_generated_data import ROOT


records = [ROOT / "outputs/archive" / name for name in (
    "depuracion_20261006", "depuracion_reciente_20261006",
    "depuracion_emulador_20261006", "depuracion_vuelos_20261006")]
total_files = 0
total_bytes = 0
for record in records:
    plan = json.loads((record / "plan.json").read_text(encoding="utf-8"))
    result = json.loads((record / "result.json").read_text(encoding="utf-8"))
    entries = plan if isinstance(plan, list) else plan.get("candidates", plan.get("deleted", []))
    assert len(entries) == result["deleted_files"], record
    assert sum(e["bytes"] for e in entries) == result["released_bytes"], record
    remaining = [e["path"] for e in entries if (ROOT / e["path"]).exists()]
    assert not remaining, remaining[:10]
    if isinstance(plan, dict):
        for key in ("evidence", "protected", "verified_originals"):
            assert all((ROOT / e["path"]).is_file() for e in plan.get(key, [])), (record, key)
        assert all((ROOT / p).is_file() for p in plan.get("samples", [])), record
    total_files += len(entries)
    total_bytes += result["released_bytes"]
assert len(list((ROOT / "outputs/new_real_dataset/captura_20260912_v6/images").rglob("*.jpg"))) == 488
assert (ROOT / "outputs/experiments/checkpoint_interpolation_scale80_seed_1000_v1/interpolated_checkpoints/natural_hybrid_alpha_045.pt").is_file()
assert not list((ROOT / "tmp/hybrid_original_staging").glob("*"))
print(json.dumps({"deleted_files_verified": total_files, "released_GiB": total_bytes/1024**3,
                  "pending_inventory_files": 0, "selected_real_images": 488}))
