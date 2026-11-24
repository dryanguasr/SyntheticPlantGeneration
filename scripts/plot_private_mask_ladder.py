"""Plot released validation and historical-development metrics inside the private run."""

import argparse
import json
from pathlib import Path
import statistics


PHASES = (20, 40, 80, 160, 320, 461)
CLASSES = ("Pintona", "Madura", "Sobremadura")
SEEDS = (20261022, 20261023, 20261024)
COLORS = ("#076b78", "#6848a9", "#387444", "#9c6317", "#a94559")
OUTPUTS = Path(__file__).resolve().parents[1] / "outputs"


def series(phases, metric):
    values = {}
    for phase in phases:
        size = phase["size"]
        if size in values or size not in PHASES:
            raise ValueError(f"Unexpected size in released report: {size}")
        by_seed = {row["seed"]: row["metrics"] for row in phase["seeds"]}
        if len(phase["seeds"]) != len(SEEDS) or set(by_seed) != set(SEEDS):
            raise ValueError(f"Incomplete seed evidence for {size} photos")
        values[size] = [metric(by_seed[seed]) for seed in SEEDS]
    return values


def draw_series(ax, values, label, color):
    for index in range(len(SEEDS)):
        seed_trace = [values[size][index] if size in values else None for size in PHASES]
        ax.plot(PHASES, [100 * value if value is not None else float("nan") for value in seed_trace],
                color=color, linewidth=1, marker=".", markersize=3, alpha=.25)
    complete = [size for size in PHASES if size in values and all(v is not None for v in values[size])]
    ax.errorbar(
        complete, [100 * statistics.mean(values[size]) for size in complete],
        yerr=[100 * statistics.stdev(values[size]) for size in complete],
        label=label, color=color, marker="o", linewidth=2, markersize=5, capsize=3,
    )


def plot(root, split):
    from matplotlib.figure import Figure
    from matplotlib.ticker import NullLocator

    root = root.resolve(strict=True)
    if root.parent != OUTPUTS.resolve() or not root.name.startswith("private_mask_ladder_"):
        raise ValueError("Choose a private campaign root directly under outputs")
    summary = json.loads((root / f"{split}_summary.json").read_text(encoding="utf-8"))
    phases = summary["phases"]
    if summary["split"] != split or not phases:
        raise ValueError(f"No complete {split} phase to plot")

    fig = Figure(figsize=(10.5, 4.7), layout="constrained")
    left, right = fig.subplots(1, 2, sharey=True)
    left.set_title("Resumen global")
    right.set_title("Por clase de apariencia")
    draw_series(left, series(phases, lambda row: row["macro_ap50_95"]), "Macro", COLORS[0])
    draw_series(left, series(phases, lambda row: row["class_agnostic"]["ap50_95"]),
                "Sin distinguir clase", COLORS[1])
    for name, color in zip(CLASSES, COLORS[2:], strict=True):
        draw_series(right, series(phases, lambda row: row["by_class"][name]["ap50_95"]), name, color)
    left.set_ylabel("AP50–95 de máscara (%)")
    for ax in (left, right):
        ax.set_xscale("log")
        ax.set_xlim(16, 570)
        ax.set_xticks(PHASES, labels=[str(size) for size in PHASES])
        ax.xaxis.set_minor_locator(NullLocator())
        ax.set_xlabel("Fotos únicas de entrenamiento")
        ax.set_ylim(bottom=0)
        ax.grid(axis="y", alpha=.2)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(frameon=False)

    title = "Validación fija (88 fotos)" if split == "val" else "Desarrollo histórico (94 fotos)"
    fig.suptitle(title + "\nLíneas tenues por semilla · puntos con media y DE", fontsize=13)
    destination = root / f"{split}_learning_curve.png"
    staging = destination.with_suffix(".tmp")
    fig.savefig(staging, format="png", dpi=160)
    staging.replace(destination)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--split", choices=("val", "test"), required=True)
    arguments = parser.parse_args()
    print(plot(arguments.root, arguments.split))
