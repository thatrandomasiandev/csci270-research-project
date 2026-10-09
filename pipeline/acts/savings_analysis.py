"""Analysis primitives for accumulated-savings measurements."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

PROBE_SIZES = (8, 8, 8, 8, 1, 1, 1, 1, 1, 1, 1, 1)


@dataclass(frozen=True)
class StockTask:
    collection: str
    position: int
    accession: str
    input_path: str


def load_job(path: Path) -> dict[str, Any]:
    import json

    raw = json.loads(path.read_text())
    collection = raw.get("collection")
    if collection not in {"A", "B"} or raw.get("mode") != "hmmsearch":
        raise ValueError(f"{path}: expected A/B hmmsearch savings JSON")
    if raw.get("stopped") or raw.get("decision"):
        raise ValueError(f"{path}: stopped savings run")
    rows = raw.get("genomes")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{path}: no genome rows")
    positions = [int(row["position"]) for row in rows]
    if positions != list(range(1, len(rows) + 1)):
        raise ValueError(f"{path}: positions are not a complete ordered prefix")
    return raw


def stock_tasks(jobs: Iterable[dict[str, Any]]) -> list[StockTask]:
    tasks: list[StockTask] = []
    for job in sorted(jobs, key=lambda item: item["collection"]):
        for row in job["genomes"]:
            if row.get("stock_wall_s") is not None:
                continue
            tasks.append(
                StockTask(
                    collection=job["collection"],
                    position=int(row["position"]),
                    accession=str(row["accession"]),
                    input_path=str(row["path"]),
                )
            )
    return tasks


def probe_cost_s(job: dict[str, Any]) -> float:
    fit = job["fit"]
    a, b = float(fit["a"]), float(fit["b"])
    return sum(a + b * n for n in PROBE_SIZES)


def sensitivity(job: dict[str, Any]) -> dict[str, Any]:
    sampled = [row for row in job["genomes"] if row.get("stock_wall_s") is not None]
    if not sampled:
        raise ValueError(f"{job['collection']}: no measured stock samples")
    measured_sum = sum(float(row["stock_wall_s"]) for row in sampled)
    predicted_sample_sum = sum(float(row["stock_predicted_s"]) for row in sampled)
    if predicted_sample_sum <= 0:
        raise ValueError(f"{job['collection']}: non-positive sampled prediction")
    ratio = measured_sum / predicted_sample_sum
    corrected_stock = sum(
        float(row["stock_wall_s"])
        if row.get("stock_wall_s") is not None
        else ratio * float(row["stock_predicted_s"])
        for row in job["genomes"]
    )
    cached = sum(float(row["cached_wall_s"]) for row in job["genomes"])
    probe = probe_cost_s(job)
    return {
        "collection": job["collection"],
        "n_genomes": len(job["genomes"]),
        "n_sampled_stock": len(sampled),
        "measured_over_predicted_ratio": ratio,
        "corrected_stock_wall_s": corrected_stock,
        "cached_wall_s": cached,
        "probe_wall_s": probe,
        "cum_speedup_wall": corrected_stock / cached,
        "cum_speedup_wall_with_P": corrected_stock / (cached + probe),
    }


def _completion_index(
    completions: Iterable[dict[str, Any]],
) -> dict[tuple[str, int], dict[str, Any]]:
    indexed: dict[tuple[str, int], dict[str, Any]] = {}
    for row in completions:
        key = (str(row.get("collection")), int(row.get("position", 0)))
        if key in indexed:
            raise ValueError(f"duplicate stock completion {key}")
        if row.get("returncode") != 0 or float(row.get("stock_wall_s", 0)) <= 0:
            raise ValueError(f"incomplete stock completion {key}")
        indexed[key] = row
    return indexed


def fully_measured(
    job: dict[str, Any], completions: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    indexed = _completion_index(completions)
    expected = {
        (task.collection, task.position): task for task in stock_tasks([job])
    }
    missing = sorted(set(expected) - set(indexed))
    extra = sorted(set(indexed) - set(expected))
    if missing or extra:
        raise ValueError(f"{job['collection']}: missing={missing}, extra={extra}")

    stock_total = 0.0
    for row in job["genomes"]:
        measured = row.get("stock_wall_s")
        if measured is not None:
            stock_total += float(measured)
            continue
        key = (job["collection"], int(row["position"]))
        completion = indexed[key]
        if completion.get("accession") != row.get("accession"):
            raise ValueError(f"{key}: accession mismatch")
        stock_total += float(completion["stock_wall_s"])

    cached = sum(float(row["cached_wall_s"]) for row in job["genomes"])
    probe = probe_cost_s(job)
    return {
        "collection": job["collection"],
        "n_genomes": len(job["genomes"]),
        "n_original_stock": len(job["genomes"]) - len(expected),
        "n_completed_stock": len(expected),
        "stock_wall_s": stock_total,
        "cached_wall_s": cached,
        "probe_wall_s": probe,
        "cum_speedup_wall": stock_total / cached,
        "cum_speedup_wall_with_P": stock_total / (cached + probe),
        "stock_model": "fully measured; no fitted stock times",
    }
