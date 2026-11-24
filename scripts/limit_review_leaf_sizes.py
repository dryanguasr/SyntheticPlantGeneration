"""Limit blade-size outliers in a saved morphology without changing architecture."""
import argparse
import copy
import hashlib
import json
from pathlib import Path


def limit_sizes(plant, max_length=12.0, max_width=9.0):
    """Engineering review limits in cm, not measured botanical bounds."""
    result = copy.deepcopy(plant)
    changes = []
    def visit(value):
        if isinstance(value, dict):
            leaf = value.get("leaf")
            if isinstance(leaf, dict):
                length, width = leaf["length_cm"], leaf["width_cm"]
                factor = min(1.0, max_length / length, max_width / width)
                if factor < 1.0:
                    leaf["length_cm"] *= factor
                    leaf["width_cm"] *= factor
                    changes.append(dict(id=leaf["id"], before_cm=[length, width],
                                        after_cm=[leaf["length_cm"], leaf["width_cm"]]))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(result)
    # Prove the only modified fields are the recorded blade dimensions.
    restored = copy.deepcopy(result)
    originals = {x["id"]: x["before_cm"] for x in changes}
    def restore(value):
        if isinstance(value, dict):
            if value.get("id") in originals:
                value["length_cm"], value["width_cm"] = originals[value["id"]]
            for child in value.values():
                restore(child)
        elif isinstance(value, list):
            for child in value:
                restore(child)
    restore(restored)
    assert restored == plant
    return result, changes


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    raw = args.input.read_bytes()
    corrected, changes = limit_sizes(json.loads(raw))
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "morphology.json").write_text(json.dumps(corrected, indent=2))
    (args.output / "changes.json").write_text(json.dumps(dict(
        version="leaf-tail-limit/173", parameter_status="engineering_heuristic",
        source=str(args.input.resolve()), source_sha256=hashlib.sha256(raw).hexdigest(),
        max_length_cm=12, max_width_cm=9, changed_count=len(changes), changes=changes,
        architecture_and_all_other_fields_exactly_preserved=True,
        accepted_for_training=False), indent=2))
    print(len(changes), "blades changed; all other fields identical")
