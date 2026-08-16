"""Stub for future batch generation.

The initial migration intentionally avoids generating large batches. This file
exists to reserve the expected entry point for later work.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


def planned_output_paths(seeds: Iterable[int], output_dir: Path) -> list[Path]:
    """Return the JSON paths a future batch run would create."""
    return [output_dir / f"morphology_tree_seed_{seed}.json" for seed in seeds]


def main() -> None:
    print("Batch generation is intentionally deferred until validation is stronger.")


if __name__ == "__main__":
    main()
