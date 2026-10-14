"""Check selected temporal bridges with existing OpenCV, without claiming 3D."""
import argparse
import json
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uchuva_dataset_curation import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("selection", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cv2.setNumThreads(4)
    cv2.setRNGSeed(20261001)
    selection = json.loads((args.selection / "selection.json").read_text(encoding="utf-8"))
    rows = [r for r in selection["rows"] if r.get("selected")]
    sift = cv2.SIFT_create(nfeatures=2500)
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    previous = None
    results = []
    for index, row in enumerate(rows):
        frame = cv2.imdecode(np.fromfile(args.selection / "images" / row["image"], dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        keys, desc = sift.detectAndCompute(frame, None)
        current = (row, np.float32([k.pt for k in keys]), desc)
        if previous is not None:
            old, p, d = previous
            pairs = matcher.knnMatch(d, desc, k=2) if d is not None and desc is not None and len(desc) >= 2 else []
            good = [m for pair in pairs if len(pair) == 2 for m, n in [pair] if m.distance < .75*n.distance]
            a = np.float32([p[m.queryIdx] for m in good])
            b = np.float32([current[1][m.trainIdx] for m in good])
            fundamental, mask = (None, None)
            if len(good) >= 12:
                fundamental, mask = cv2.findFundamentalMat(a, b, cv2.USAC_MAGSAC, 1.5, .999, 10000)
            inliers = np.zeros(len(good), dtype=bool) if mask is None else mask.ravel().astype(bool)
            count = int(inliers.sum())
            cells = len({(min(3, int(x/frame.shape[1]*4)), min(3, int(y/frame.shape[0]*4))) for x, y in a[inliers]})
            result = dict(image_a=old["image"], image_b=row["image"],
                time_a=old["decoder_seconds"], time_b=row["decoder_seconds"],
                ratio_test_matches=len(good), fundamental_inliers=count, spatial_cells_4x4=cells,
                median_displacement_pixels=float(np.median(np.linalg.norm(a[inliers]-b[inliers], axis=1))) if count else None,
                weak_bridge=count < 30 or cells < 4)
            results.append(result)
        previous = current
        if index % 20 == 0:
            print(f"Pair diagnostics {index}/{len(rows)}", flush=True)
    report = dict(script_version="reconstruction-pilot/0.1", seed=20261001,
        parameter_preset="pilot_2h", method="OpenCV SIFT + ratio 0.75 + fundamental USAC_MAGSAC 1.5px",
        thresholds="engineering_heuristic", claim="Pairwise diagnostic only; not camera poses, triangulation or proof of correct loop closure",
        pairs=results, weak_pair_count=sum(p["weak_bridge"] for p in results))
    write_json(args.output, report)
    print(json.dumps({k:v for k,v in report.items() if k != "pairs"}))


if __name__ == "__main__":
    main()
