"""Audit and supplement the frozen evaluation, without training or new inference.

Only persisted test predictions are used. The selected winner remains the one
chosen using mean validation AP before test evaluation. Frozen evaluators and
their historical bootstrap outputs are never modified.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import statistics
import time

import numpy as np


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def mean_sd(values):
    return {"mean": statistics.mean(values), "sd": statistics.stdev(values) if len(values) > 1 else 0.0}


def checked_groups(records, replicates=200, seed=20261022):
    """Keep macro AP's three-class denominator fixed, documenting rejected draws."""
    groups = sorted({row["group"] for row in records})
    presence = {group: set() for group in groups}
    for row in records:
        presence[row["group"]].update(row["stats"]["target_cls"])
    assert set().union(*presence.values()) == {0, 1, 2}
    generator = np.random.default_rng(seed)
    accepted, rejected = [], []
    attempts = 0
    while len(accepted) < replicates:
        sampled = generator.choice(groups, len(groups), replace=True).tolist()
        classes = set().union(*(presence[group] for group in sampled))
        if classes == {0, 1, 2}:
            accepted.append(sampled)
        else:
            rejected.append({"draw_index": attempts, "groups": sampled, "missing_classes": sorted({0, 1, 2} - classes)})
        attempts += 1
        if attempts > 100000:
            raise RuntimeError("Unable to construct bootstrap draws containing all classes")
    return {"seed": seed, "replicates": replicates, "groups": groups,
            "group_image_counts": dict(Counter(row["group"] for row in records)),
            "draws": accepted, "rejected": rejected, "attempts": attempts,
            "conditioning": "All three truth classes represented; fixed three trained seeds; common draws for every contrast"}


def audit(root):
    protocol = read(root / "protocol.json")
    lock = read(root / "evaluation_lock.json")
    finalist_lock = root / "finalists_lock.json"
    assert lock["finalists_sha256"] == sha(finalist_lock)
    assert lock["selection_used_test"] is False
    assert read(finalist_lock)["test_read"] is False
    names = lock["runs"]
    assert len(names) == len(set(names)) == 39, "Expected 36 final runs plus three repetition controls"
    assert set(lock["weights"]) == set(names)
    for path, digest in read(root / "training_source_lock.json")["files"].items():
        assert sha(path) == digest, path
    assert sha(protocol["weights"]) == protocol["weights_sha256"]
    screenings = list((root / "training").glob("screen_*/completion.json"))
    assert len(screenings) == 24
    for path in screenings:
        value = read(path)
        assert value["completed"] and value["steps"] == 2000
        assert sha(path.parent / "weights/best.pt") == value["best_sha256"]
    runs, grouped, predictions, summaries, inputs = {}, defaultdict(list), {}, {}, {}
    test = [row for row in read(root / "real_manifest.json")["rows"] if row["split"] == "test"]
    expected_rows = {row["source_row"]: row["group_id"] for row in test}
    assert len(expected_rows) == 94
    common_truth = None
    for name in names:
        directory = root / "training" / name
        done = read(directory / "completion.json")
        cfg = done["config"]
        assert done["completed"] and done["steps"] == cfg["steps"] == 4000
        assert cfg["seed"] in protocol["seeds"] and cfg["name"] == name
        assert sum(done["exposure"].values()) == 8000
        assert cfg["protocol_sha256"] == sha(root / "protocol.json")
        assert cfg["dataset_sha256"] == sha(Path(cfg["dataset"]).parent / "manifest.json")
        for filename, digest in [("best.pt", done["best_sha256"]), ("last.pt", done["last_sha256"])]:
            assert sha(directory / "weights" / filename) == digest
        assert lock["weights"][name] == done["best_sha256"]
        sequence = read(directory / "sampling_sequences.json")
        assert len(sequence) == 8 and all(len(epoch["actual_source_ids"]) == 1000 for epoch in sequence)
        repeated = bool(cfg.get("repeat_control"))
        key = ("repeat_" if repeated else "") + cfg["arm"]
        grouped[key].append(name)
        if repeated:
            original_name = name.removeprefix("repeat_")
            pair = read(directory / "repetition_pair_check.json")
            assert pair["passed"] and pair["original"] == original_name
            original = read(root / "training" / original_name / "sampling_sequences.json")
            assert len(original) == len(sequence)
            for first, second in zip(original, sequence):
                assert first["planned_source_ids"] == second["planned_source_ids"]
                assert all(left == right for left, right in zip(first["actual_source_ids"], second["actual_source_ids"]) if left.startswith("row_"))
                assert all(value.startswith("row_") for value in second["actual_source_ids"])
            assert done["exposure"].get("synthetic", 0) == 0 and done["exposure"]["real"] == 8000
        predicted_path = root / "evaluation" / name / "predictions.json"
        summary_path = root / "evaluation" / name / "summary.json"
        records = read(predicted_path)
        assert len(records) == 94 and len({row["source_row"] for row in records}) == 94
        assert {row["source_row"]: row["group"] for row in records} == expected_rows
        truth = {row["source_row"]: row["truth"] for row in records}
        if common_truth is None:
            common_truth = truth
        else:
            assert truth == common_truth, "Prediction runs must share identical truth"
        predictions[name] = [{key: row[key] for key in ("source_row", "group", "stats")} for row in records]
        summaries[name] = read(summary_path)
        assert {row["class_id"] for row in summaries[name]["ap"]["per_class"]} == {0, 1, 2}
        inputs[name] = {"predictions_sha256": sha(predicted_path), "summary_sha256": sha(summary_path),
                        "completion_sha256": sha(directory / "completion.json"), "best_sha256": done["best_sha256"]}
        runs[name] = done
    for arm, arm_names in grouped.items():
        assert len(arm_names) == 3 and {runs[name]["config"]["seed"] for name in arm_names} == set(protocol["seeds"]), arm
    assert len(grouped) == 13
    synthetic = {arm: arm_names for arm, arm_names in grouped.items() if not arm.startswith("repeat_") and runs[arm_names[0]]["config"]["synthetic_images"] > 0}
    assert len(synthetic) == 6
    winner = max(synthetic, key=lambda arm: statistics.mean(runs[name]["best_validation_ap"] for name in synthetic[arm]))
    assert "repeat_" + winner in grouped
    threshold = read(root / "evaluation_threshold.json")
    assert threshold["split"] == "val" and threshold["test_used"] is False
    assert all(value["threshold"] == threshold["value"] for value in summaries.values())
    inputs.update(evaluation_lock_sha256=sha(root / "evaluation_lock.json"),
                  finalists_sha256=sha(finalist_lock), protocol_sha256=sha(root / "protocol.json"),
                  threshold_sha256=sha(root / "evaluation_threshold.json"), script_sha256=sha(__file__))
    return runs, dict(grouped), synthetic, winner, summaries, predictions, inputs


def supplement(root, output, runs, grouped, synthetic, winner, summaries, predictions):
    # Import the frozen scoring implementation only after the root environment is set.
    import torch
    from evaluate_augmentation_campaign import ap_summary
    torch.set_num_threads(4)
    bootstrap = checked_groups(next(iter(predictions.values())))
    write(output / "bootstrap_design.json", bootstrap)
    contrasts = [(arm, f"r{runs[names[0]]['config']['real_fraction']}_s0_c{int(runs[names[0]]['config']['classical'])}") for arm, names in synthetic.items()]
    contrasts.append((winner, "repeat_" + winner))
    needed = sorted({name for pair in contrasts for arm in pair for name in grouped[arm]})
    draws = {}
    for index, name in enumerate(needed):
        cache = output / "bootstrap_cache" / f"{name}.json"
        if cache.exists():
            values = read(cache)
            assert len(values) == bootstrap["replicates"]
        else:
            by_group = {group: [row for row in predictions[name] if row["group"] == group] for group in bootstrap["groups"]}
            values = [ap_summary([row for group in draw for row in by_group[group]])["map50_95"] for draw in bootstrap["draws"]]
            write(cache, values)
        draws[name] = np.asarray(values)
        print(f"Bootstrap persisted {index + 1}/{len(needed)}: {name}", flush=True)
    results = []
    for candidate, baseline in contrasts:
        first = {runs[name]["config"]["seed"]: name for name in grouped[candidate]}
        second = {runs[name]["config"]["seed"]: name for name in grouped[baseline]}
        seed_rows, paired_draws = [], []
        for seed in sorted(first):
            a, b = first[seed], second[seed]
            delta = summaries[a]["ap"]["map50_95"] - summaries[b]["ap"]["map50_95"]
            sampled = draws[a] - draws[b]
            paired_draws.append(sampled)
            seed_rows.append({"seed": seed, "candidate_run": a, "baseline_run": b,
                              "candidate_ap": summaries[a]["ap"]["map50_95"], "baseline_ap": summaries[b]["ap"]["map50_95"],
                              "delta": delta, "group_bootstrap_95": np.quantile(sampled, [.025, .975]).tolist()})
        average_draws = np.mean(paired_draws, axis=0)
        results.append({"candidate": candidate, "baseline": baseline, "seeds": seed_rows,
                        "paired_delta": mean_sd([row["delta"] for row in seed_rows]),
                        "group_bootstrap_mean_delta_95": np.quantile(average_draws, [.025, .975]).tolist(),
                        "replicates": bootstrap["replicates"], "groups": len(bootstrap["groups"]),
                        "interval_scope": "Mean of three fixed trained seeds, paired group resampling conditional on all truth classes; not independent-session or new-seed uncertainty"})
    per_arm = {}
    for arm, names in grouped.items():
        rows = []
        for name in sorted(names, key=lambda n: runs[n]["config"]["seed"]):
            done, value = runs[name], summaries[name]
            rows.append({"run": name, "seed": done["config"]["seed"], "validation_ap": done["best_validation_ap"],
                         "test_ap": value["ap"]["map50_95"], "per_class": value["ap"]["per_class"],
                         "collapsed_ap": value["collapsed_ap"]["map50_95"],
                         "precision": value["fixed"]["class_aware"]["precision"], "recall": value["fixed"]["class_aware"]["recall"],
                         "exposure": done["exposure"], "instance_exposure": done["instance_exposure"],
                         "wall_seconds": done["seconds"], "best_sha256": done["best_sha256"]})
        per_arm[arm] = {"runs": rows, "test_ap": mean_sd([row["test_ap"] for row in rows]),
                        "validation_ap": mean_sd([row["validation_ap"] for row in rows])}
    payload = {"validation_selected_winner": winner, "winner_selection_used_test": False,
               "test_status": "Historically consulted development test, not external validation",
               "contrasts": results, "arms": per_arm, "bootstrap_design": str(output / "bootstrap_design.json")}
    write(output / "paired_comparisons.json", payload)
    return payload


def plot(output, payload):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rows = payload["contrasts"]
    fig, ax = plt.subplots(figsize=(11, 6))
    for index, row in enumerate(rows):
        values = [100 * seed["delta"] for seed in row["seeds"]]
        lo, hi = [100 * x for x in row["group_bootstrap_mean_delta_95"]]
        avg = 100 * row["paired_delta"]["mean"]
        ax.plot([lo, hi], [index, index], color="#3274a1", linewidth=2)
        ax.scatter(values, [index] * len(values), color="#df8f44", marker="x", zorder=3)
        ax.scatter([avg], [index], color="#3274a1", zorder=4)
    ax.axvline(0, color="black", linewidth=.8)
    ax.set_yticks(range(len(rows)), [f"{row['candidate']} vs {row['baseline']}" for row in rows])
    ax.invert_yaxis()
    ax.set(xlabel="Diferencia AP50–95 (puntos porcentuales)", title="Test de desarrollo: semillas (×), media (●) e intervalo por grupos")
    ax.grid(axis="x", alpha=.2)
    fig.text(.5, .015, "Seis grupos; intervalo condicional a tres semillas y a presencia de las tres clases. No prueba significación.", ha="center", fontsize=8)
    fig.tight_layout(rect=(0, .04, 1, 1))
    fig.savefig(output / "paired_test_comparisons.png", dpi=180)
    plt.close(fig)


def report(root, output, payload, summaries, runs):
    repo = Path(__file__).resolve().parents[1]
    destination = repo / "docs/reports/piloto_aumentacion_sintetica_exploratoria_2026-10-22.md"
    archived = output / "automatic_report_before_supplement.md"
    if not archived.exists():
        archived.write_bytes(destination.read_bytes())
    text = archived.read_text(encoding="utf-8").replace(
        "El presupuesto de 24 horas original se mantiene.",
        "El presupuesto inicial se amplió por autorización del usuario el 23 de octubre y nuevamente el 26 de octubre para completar tres repeticiones y la evaluación; los presupuestos, cierres e intentos anteriores se conservaron.")
    winner = payload["validation_selected_winner"]
    lines = ["", "## Confirmación final con tres controles de repetición", "",
             "Se verificaron 24 screenings de 2.000 actualizaciones, 18 finalistas sintéticos, 18 controles reales heredados y tres controles de repetición, estos últimos 39 entrenamientos de 4.000 actualizaciones. Todos conservan la inicialización, receta, datos y calendario de aprendizaje congelados. Las tres semillas son 20261022, 20261023 y 20261024.", "",
             f"La mezcla seleccionada antes del test por mayor AP medio de validación fue `{winner}`. No se cambió el ganador al consultar el test. La autorización del 26 de octubre permite terminar los pendientes; no aporta nuevas imágenes ni cambia el protocolo. Los cierres incompletos y el primer control truncado permanecen archivados.", "",
             "En cada repetición se conservaron los 8.000 puestos planificados y las muestras reales originales de su mezcla emparejada. Cada puesto sintético se sustituyó por una imagen real: exposición sintética efectiva cero y exposición real 8.000. El campo nominal `synthetic_images` de su configuración identifica la mezcla de referencia, no imágenes sintéticas realmente consumidas.", "",
             "### Diferencias emparejadas con la misma receta clásica", "",
             "| Mezcla | Referencia | Δ semillas (puntos AP) | Δ medio ± DE | Intervalo por grupos de la media |",
             "|---|---|---|---:|---:|"]
    for row in payload["contrasts"]:
        deltas = ", ".join(f"{100 * seed['delta']:+.2f}" for seed in row["seeds"])
        lo, hi = [100 * x for x in row["group_bootstrap_mean_delta_95"]]
        lines.append(f"| {row['candidate']} | {row['baseline']} | {deltas} | {100 * row['paired_delta']['mean']:+.2f} ± {100 * row['paired_delta']['sd']:.2f} | [{lo:+.2f}, {hi:+.2f}] |")
    lines += ["", "La DE resume variación entre las tres diferencias de semillas emparejadas. El intervalo percentil usa 200 remuestreos comunes de seis grupos y promedia las diferencias de esas tres semillas ya entrenadas. No es un intervalo para nuevas semillas ni para sesiones independientes. Los grupos contienen 25, 48, 15, 3, 2 y 1 imágenes; son pocos y muy desiguales.", "",
              "El remuestreo complementario conserva las tres clases en cada réplica, rechazando y registrando sorteos sin alguna clase para evitar que cambie el denominador del AP macro. El bootstrap original del evaluador congelado se preserva por separado; incluye una réplica sin Madura y solo compara con real sin clásica. Ninguno de estos intervalos demuestra significación confirmatoria ni independencia por sesión.", "",
              f"![Diferencias emparejadas]({(output / 'paired_test_comparisons.png').as_posix()})", "",
              "### Resultados por semilla y clase", "",
              "AP50–95, AP colapsado y valores por clase están expresados en porcentaje. P/R usan el umbral común elegido exclusivamente en validación.", "",
              "| Ejecución | AP | Pintona | Madura | Sobremadura | Colapsado | P | R | Exposición real/sintética |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for arm in payload["arms"].values():
        for row in arm["runs"]:
            classes = {value["class_id"]: value["map50_95"] for value in row["per_class"]}
            values = [row["test_ap"], classes[0], classes[1], classes[2], row["collapsed_ap"], row["precision"], row["recall"]]
            lines.append(f"| {row['run']} | " + " | ".join(f"{100 * value:.2f}" for value in values) + f" | {row['exposure'].get('real', 0)}/{row['exposure'].get('synthetic', 0)} |")
    lines += ["", "### Errores y prioridades para el siguiente piloto", "",
              "Las siguientes observaciones describen el test de desarrollo de la mezcla seleccionada; las causas propuestas requieren otra ablación. Las confusiones completas, incluyendo fondo, se conservan para cada semilla en `evaluation/<ejecución>/summary.json`.", ""]
    names = [row["run"] for row in payload["arms"][winner]["runs"]]
    class_means = {class_id: statistics.mean(next(c["map50_95"] for c in summaries[name]["ap"]["per_class"] if c["class_id"] == class_id) for name in names) for class_id in range(3)}
    labels = ["Pintona", "Madura", "Sobremadura"]
    lowest = min(class_means, key=class_means.get)
    lines.append(f"- **Clase:** el AP medio menor del ganador corresponde a {labels[lowest]} ({100 * class_means[lowest]:.2f} %). Priorizar revisión de correspondencia de apariencia, textura y color de capacho con ejemplos reales; no interpretar estas etiquetas como madurez interna validada.")
    for prefix, label in [("size:", "Tamaño"), ("density:", "Densidad")]:
        keys = sorted({key for name in names for key in summaries[name]["strata"] if key.startswith(prefix)})
        values = []
        for key in keys:
            truths = sum(summaries[name]["strata"].get(key, {}).get("truth", 0) for name in names)
            correct = sum(summaries[name]["strata"].get(key, {}).get("correct_class", 0) for name in names)
            if truths:
                values.append((key.removeprefix(prefix), correct / truths, truths // len(names)))
        if values:
            detail = "; ".join(f"{key}: {100 * recall:.1f} % (n={truths} instancias)" for key, recall, truths in values)
            lines.append(f"- **{label}:** recall de localización con clase correcta, promedio entre semillas: {detail}. Es recall por estrato, no AP por estrato ni estimación de oclusión física.")
    lines += ["- **Geometría y exposición:** el banco mantiene exceso de objetos diminutos y distinta mezcla de clases; las 389 imágenes proceden de cuatro plantas. Igualar actualizaciones no iguala exposición a reales ni a instancias. Ensayar cámaras y visibilidad por clase, y más plantas con menos vistas repetidas, sin agrandar órganos ni eliminar etiquetas visibles.",
              "- **Fondos y maleza:** las escenas reales de plantas descuidadas contienen espacios abiertos, maleza y distractores. Su importancia causal no se aisló aquí. Próxima ablación: cruzar follaje del cultivo denso/ralo con maleza escasa/abundante, manteniendo el resto fijo y anotando cobertura real antes de ajustar.",
              "- **Texturas e iluminación:** la revisión visual previa detectó vegetación virtual oscura, fondos más uniformes y diferencias en apariencia de capachos maduros/sobremaduros. Comparar materiales bajo luz neutra común y después bajo luz de campo separa hipótesis de material y exposición. Un aumento global de brillo no demuestra equivalencia de apariencia.",
              "- **Validación futura:** repetir con nuevas plantas y sesiones separadas antes de afirmar generalización externa. No seleccionar la siguiente proporción por estos resultados de test; conservar una nueva evaluación independiente para el siguiente experimento.", "",
              "### Evidencia del cierre", "",
              f"Auditoría, entradas por hash, comparaciones, diseños de remuestreo y gráfico: `{output}`. Los pesos siguen en `training/<ejecución>/weights/best.pt`; `paired_comparisons.json` registra sus hashes y exposición por imágenes e instancias. Las duraciones guardadas son tiempo de pared y pueden incluir suspensiones; no se presentan como cómputo efectivo.", "",
              "La revisión visual de curvas y muestras y la validación del grafo se documentan en el cierre del controlador. Esta posproducción no vuelve a entrenar, no ejecuta inferencia y no promueve modelos.", ""]
    destination.write_text(text.rstrip() + "\n" + "\n".join(lines), encoding="utf-8")
    metadata = {"path": str(destination), "sha256": sha(destination), "size_gate_waived": True,
                "supplement": str(output), "test_used_for_selection": False}
    write(output / "report_manifest.json", metadata)
    write(root / "report.json", metadata)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    os.environ["UCHUVA_AUGMENTATION_ROOT"] = str(root)
    output = root / "confirmation_evaluation_20261026"
    runs, grouped, synthetic, winner, summaries, predictions, inputs = audit(root)
    previous = output / "inputs.json"
    if previous.exists():
        assert read(previous) == inputs, "Supplement cache belongs to different inputs; preserve it and use a new revision"
    else:
        write(previous, inputs)
    payload = supplement(root, output, runs, grouped, synthetic, winner, summaries, predictions)
    plot(output, payload)
    report(root, output, payload, summaries, runs)
    write(output / "audit.json", {"complete": True, "verified_at": time.time(), "screenings": 24,
                                  "synthetic_finals": 18, "real_finals": 18, "repetition_controls": 3,
                                  "steps": 4000, "winner": winner, "selection_used_test": False,
                                  "repetition_sequences_verified": True, "frozen_hashes_verified": True,
                                  "test_rows": 94, "test_groups": 6})
    print(output, flush=True)


if __name__ == "__main__":
    main()
