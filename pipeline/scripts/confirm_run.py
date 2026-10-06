#!/usr/bin/env python3
"""Confirmatory hmmscan runner (docs/CONFIRM_PROTOCOL.md).

Wraps scripts/run_hmmer_savings.py by import. Does not edit that file.
Collection ids are confirm_E / confirm_C. PRIMARY is hmmscan.
"""

from __future__ import annotations

import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("ACTS_PIPELINE_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from acts.infer_fasta import contract_satisfies, layout_is_pinned  # noqa: E402

import run_hmmer_savings as sav  # noqa: E402

PROTOCOL = "pipeline/docs/CONFIRM_PROTOCOL.md"
COLLECTIONS = ("confirm_E", "confirm_C")
PRIMARY_MODE = "hmmscan"
STOCK_POS = {1, 2, 5, 10, 20, 30}
PRED_PATH = ROOT / "results" / "confirm_predictions.json"


def load_pred() -> dict:
    return json.loads(PRED_PATH.read_text())


def genomes_spec(collection: str) -> list[dict]:
    raw = load_pred()
    out = []
    for genome in raw["arms"][collection]["genomes"]:
        out.append(
            {
                "position": genome["position"],
                "index": genome["ondisk_index"],
                "accession": genome["accession"],
                "strain": genome.get("strain"),
                "path": genome["path"],
                "n_unique_listed": genome.get("n_unique"),
            }
        )
    return out


def predicted_speedup(collection: str, mode: str, k: int) -> float | None:
    raw = load_pred()
    for row in raw["arms"][collection]["modes"][mode]["per_genome"]:
        if row.get("k") == k:
            return row.get("speedup_this_genome")
    return None


def summarize(payload: dict, fit: dict, collection: str, mode: str) -> None:
    sav.summarize(payload, fit, collection, mode)
    rows = payload.get("genomes") or []
    if not rows or mode != PRIMARY_MODE:
        return
    cached = (payload.get("cumulative") or {}).get("cached_wall_s")
    stock = (payload.get("cumulative") or {}).get("stock_wall_s")
    if not cached or not stock:
        return
    frac = cached / stock
    pred = load_pred()
    locked = pred["arms"][collection]["modes"][mode]
    p_s = locked["P"]["P_s"]
    meas = stock / (p_s + cached)
    payload["kill"] = {
        "rule": "cached wall must be < 50% of stock wall at k=30 for hmmscan",
        "cached_over_stock": frac,
        "fails": frac >= 0.50,
    }
    payload["confirmation"] = {
        "pred_cum_speedup_with_P": locked["cum_speedup_with_P"],
        "meas_cum_speedup_with_P": meas,
        "cached_frac": frac,
        "P_s": p_s,
        "rel_err": abs(meas / locked["cum_speedup_with_P"] - 1.0),
        "band_ok": abs(meas / locked["cum_speedup_with_P"] - 1.0) <= 0.20,
        "frac_ok": frac < 0.50,
    }
    payload["confirmation"]["confirmed"] = (
        payload["confirmation"]["band_ok"] and payload["confirmation"]["frac_ok"]
    )
    payload["primary"] = True
    payload["post_hoc"] = False
    payload["scored"] = True


def patch_savings(collection: str) -> None:
    sav.PROTOCOL = PROTOCOL
    sav.STOCK_POS[collection] = set(STOCK_POS)
    sav.ORDER[collection] = [g["index"] for g in genomes_spec(collection)]
    sav.genomes_spec = genomes_spec
    sav.predicted_speedup = predicted_speedup
    sav.summarize = summarize


def main() -> int:
    collection = os.environ.get("ACTS_CONFIRM_COLLECTION", "")
    mode = os.environ.get("ACTS_CONFIRM_MODE", PRIMARY_MODE)
    if collection not in COLLECTIONS:
        raise SystemExit("set ACTS_CONFIRM_COLLECTION={confirm_E,confirm_C}")
    if mode not in sav.EXPECTED_MATCH:
        raise SystemExit("set ACTS_CONFIRM_MODE={hmmscan,hmmsearch}")
    if mode != PRIMARY_MODE:
        print("WARNING: hmmsearch is secondary / not scored on this confirmation", flush=True)

    os.environ.setdefault("ACTS_SAVINGS_OUT", str(ROOT / "results" / "confirm"))
    patch_savings(collection)

    cpu = sav.nproc()
    fit = sav.screen_fit(mode)
    specs = genomes_spec(collection)
    paths = sav.paths_for(collection, mode)
    paths["base"].mkdir(parents=True, exist_ok=True)
    work = Path(os.environ.get("ACTS_SAVINGS_WORK", f"/tmp/acts_confirm_{os.getpid()}"))
    work.mkdir(parents=True, exist_ok=True)
    out_json = paths["json"]

    flagged = sav.stop_if_flagged(paths["stop"])
    if flagged:
        print(f"STOP already set: {flagged}")
        return 2

    bins = sav.which_hmmer()
    pfam_src = Path(os.environ.get("ACTS_PFAM", str(ROOT / "data" / "hmmer" / "Pfam-A.hmm.gz")))
    hmm = sav.ensure_pressed(sav.stage_pfam(pfam_src, work / "hmmer"), bins["hmmpress"])
    argv = sav.wrapper_argv(mode, bins[mode], hmm, cpu)
    commit = sav.git_hash()

    skeleton = {
        "protocol": PROTOCOL,
        "git": commit,
        "collection": collection,
        "mode": mode,
        "path": "paired",
        "paper": "token / whitespace-normalized identity, not byte identity",
        "primary": mode == PRIMARY_MODE,
        "post_hoc": False,
        "scored": mode == PRIMARY_MODE,
        "label": "PRIMARY" if mode == PRIMARY_MODE else "secondary / not scored",
        "host": sav.host_info(),
        "hmmer": bins["version_head"],
        "pfam": str(hmm),
        "cpu": cpu,
        "fit": fit,
        "argv_wrapper": argv,
        "genomes": [],
        "stopped": None,
        "decision": None,
        "predictions": str(PRED_PATH.relative_to(ROOT)) if PRED_PATH.is_file() else None,
    }
    payload = sav.load_or_init(out_json, skeleton)
    payload["host"] = sav.host_info()
    payload["git"] = commit
    payload["protocol"] = PROTOCOL
    payload["primary"] = mode == PRIMARY_MODE
    payload["post_hoc"] = False
    payload["scored"] = mode == PRIMARY_MODE
    payload["resumed"] = bool(payload.get("genomes"))
    by_pos = {row["position"]: row for row in payload.get("genomes") or []}

    cache_path = paths["cache_dir"] / "cache.jsonl"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = sav.RecordCache(cache_path, argv=argv, kind="fasta")
    contract = None
    rng = random.Random(sav.AUDIT_SEED)

    for spec in specs:
        flagged = sav.stop_if_flagged(paths["stop"])
        if flagged:
            return sav.halt(payload, fit, collection, mode, out_json, flagged)
        existing = by_pos.get(spec["position"])
        if sav.genome_complete(existing, collection):
            continue

        sampled = spec["position"] in sav.STOCK_POS[collection]
        recs = sav.load_faa(ROOT / spec["path"])
        gwork = work / f"g{spec['position']:02d}"
        gwork.mkdir(parents=True, exist_ok=True)
        row = {
            **(existing or spec),
            **spec,
            "N_i": len(recs),
            "n_unique": len({r.key for r in recs}),
        }
        if not sampled and row.get("stock_wall_s") is None:
            row["stock_source"] = "predicted a+b*N_i"

        if contract is None:
            print("inferring table contract (probe_n=8) …", flush=True)
            contract = sav.ensure_contract(argv, recs, cache.path, gwork)
            ok, reason = contract_satisfies(contract, sav.EXPECTED_MATCH[mode])
            if not ok:
                sav.write_stop(
                    paths["stop"],
                    {
                        "stopped": True,
                        "where": "contract",
                        "mode": mode,
                        "match": contract.match,
                        "match_ws": contract.match_ws,
                        "pinned": layout_is_pinned(contract),
                        "expected": sav.EXPECTED_MATCH[mode],
                        "reason": reason,
                    },
                )
                return sav.halt(payload, fit, collection, mode, out_json, json.loads(paths["stop"].read_text()))

        if sampled and row.get("stock_wall_s") is None:
            print(f"stock {collection} {mode} genome {spec['position']} {spec['accession']}", flush=True)
            stock_row = sav.run_stock_genome(
                spec=spec,
                recs=recs,
                mode=mode,
                bins=bins,
                hmm=hmm,
                cpu=cpu,
                work=gwork,
                paths=paths,
                collection=collection,
                contract=contract,
            )
            row.update(stock_row)
            sav.upsert_genome(payload, row)
            by_pos[spec["position"]] = row
            sav.persist(payload, fit, collection, mode, out_json)
            if row.get("match") is False:
                return sav.halt(
                    payload,
                    fit,
                    collection,
                    mode,
                    out_json,
                    sav.stop_if_flagged(paths["stop"]) or {"decision": "STOP_MATCH", "where": "stock MATCH"},
                )

        if row.get("cached_wall_s") is None:
            print(f"cached {collection} {mode} genome {spec['position']} {spec['accession']}", flush=True)
            cached_row = sav.run_cached_genome(
                spec=spec,
                recs=recs,
                mode=mode,
                argv=argv,
                cache=cache,
                contract=contract,
                work=gwork,
                paths=paths,
                collection=collection,
                rng=rng,
            )
            row.update(cached_row)
            sav.upsert_genome(payload, row)
            by_pos[spec["position"]] = row
            sav.persist(payload, fit, collection, mode, out_json)
            if row.get("match") is False or (row.get("audit") and not row["audit"]["ok"]):
                return sav.halt(
                    payload,
                    fit,
                    collection,
                    mode,
                    out_json,
                    sav.stop_if_flagged(paths["stop"])
                    or {
                        "decision": "STOP_MATCH" if row.get("match") is False else "STOP_AUDIT",
                        "where": "cached MATCH" if row.get("match") is False else "audit",
                    },
                )

    payload["finished_utc"] = datetime.now(timezone.utc).isoformat()
    sav.persist(payload, fit, collection, mode, out_json)
    print(f"wrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
