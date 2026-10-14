"""Extract a small, motion-adaptive reconstruction selection from an audited input."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uchuva_reconstruction.frames import select_frames


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", type=float, required=True)
    parser.add_argument("--end", type=float, required=True)
    parser.add_argument("--step", type=float, default=1.)
    parser.add_argument("--long-side", type=int, default=960)
    parser.add_argument("--motion-pixels", type=float, default=18.)
    parser.add_argument("--max-gap", type=float, default=4.)
    args = parser.parse_args()
    select_frames(ROOT, args.manifest, args.output, args.start, args.end,
                  args.step, args.long_side, args.motion_pixels, args.max_gap)


if __name__ == "__main__":
    main()
