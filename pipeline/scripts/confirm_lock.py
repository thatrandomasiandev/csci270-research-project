#!/usr/bin/env python3
"""Select, download, and lock confirmatory predictions.

Reads the existing E. coli assembly summary and collection C FASTAs.
Writes new E. coli FASTAs under data_confirm/ (gitignored).
Writes results/confirm_predictions.json. No HMMER timing.
"""

from __future__ import annotations

import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from confirm_predict import (  # noqa: E402
    PRIMARY_MODE,
    PROTOCOL as PREDICT_PROTOCOL,
    SCREEN_N,
    arm_prediction,
    criteria_verbatim,
    locked_params,
)
from confirm_select import (  # noqa: E402
    CONFIRM_E_SEED,
    C_ORDERING0_PREFIX30,
    K12_RE,
    N_GENOMES,
    PROTOCOL,
    STOCK_POS,
    c_prefix_indices,
    confirm_e_pool,
    draw_confirm_e,
    excluded_accessions,
    faa_keys,
    miss_along_order,
    run_order_indices,
)
from run_recurrence_curves import (  # noqa: E402
    MAX_BYTES,
    UNKNOWN_LEN,
    download_rows,
    file_md5,
    head_length,
    parse_summary,
    probe_urls,
    record_assembly,
)

DATA = ROOT / "data" / "recurrence"
DATA_CONFIRM = ROOT / "data_confirm"
OUT = ROOT / "results" / "confirm_predictions.json"
SCREEN_PATH = ROOT / "results" / "headline_screen.json"
ACC_PATH = ROOT / "results" / "recurrence_accessions.json"
CURVES_PATH = ROOT / "results" / "recurrence_curves.json"
SUMMARY_ECOLI = DATA / "assembly_summary_ecoli.txt"

CURL_STOP = 2


def n_records(path: Path) -> int:
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as fh:
        return sum(1 for line in fh if line.startswith(">"))


def genome_payload(row, path: Path, index: int) -> dict:
    rec = record_assembly(row, path, n_unique=0, planned_bytes=path.stat().st_size)
    keys = faa_keys(path)
    rec["n_unique"] = len(keys)
    rec["n_records"] = n_records(path)
    rec["index"] = index
    rec["path"] = str(path.relative_to(ROOT))
    return rec, keys


def genome_payload_from_locked(raw: dict, path: Path, index: int) -> dict:
    keys = faa_keys(path)
    rec = dict(raw)
    rec["index"] = index
    rec["path"] = str(path.relative_to(ROOT))
    rec["n_unique"] = len(keys)
    rec["n_records"] = n_records(path)
    rec["bytes"] = path.stat().st_size
    rec["file_md5"] = file_md5(path)
    return rec, keys


def fill_confirm_e(pool):
    picked = draw_confirm_e(pool, N_GENOMES, CONFIRM_E_SEED)
    ok, miss, _ = probe_urls(picked)
    head_failed = list(miss)
    kept = list(ok)
    picked_acc = {row.accession for row in picked}
    rest = [row for row in pool if row.accession not in picked_acc]
    for row in rest:
        if len(kept) >= N_GENOMES:
            break
        exists, nbytes = head_length(row.protein_url)
        if not exists:
            head_failed.append(
                {"accession": row.accession, "url": row.protein_url, "reason": "HEAD failed"}
            )
            continue
        kept.append(row)
        print(f"replace {row.accession} ({nbytes} bytes)", flush=True)
    if len(kept) < N_GENOMES:
        print(
            f"STOP: only {len(kept)} confirm_E proteomes after replacements. Ask Josh.",
            file=sys.stderr,
        )
        raise SystemExit(CURL_STOP)
    kept = sorted(kept, key=lambda x: x.accession)
    ok2, miss2, planned = probe_urls(kept)
    head_failed.extend(miss2)
    if len(ok2) < N_GENOMES:
        print("STOP: a replacement lost its protein FASTA on re-HEAD. Ask Josh.", file=sys.stderr)
        raise SystemExit(CURL_STOP)
    if planned > MAX_BYTES:
        print(
            f"STOP: planned confirm_E download {planned} bytes exceeds 1 GiB. Ask Josh.",
            file=sys.stderr,
        )
        raise SystemExit(CURL_STOP)
    return ok2, planned, head_failed, len(pool), len(picked)


def snapshots_m(m_along: list[float]) -> dict:
    out = {}
    for k in (1, 10, 29):
        if 1 <= k <= len(m_along):
            out[str(k)] = m_along[k - 1]
    return out


def arm_block(*, genomes_run: list[dict], keysets_run: list[set[str]], params: dict) -> dict:
    order = list(range(len(genomes_run)))
    m_along = miss_along_order(keysets_run, order)
    n_list = [float(g["n_records"]) for g in genomes_run]
    n_standin = [SCREEN_N] * len(genomes_run)
    modes = {}
    for name, p in params.items():
        primary = arm_prediction(mode=name, params=p, n_list=n_list, m_along=m_along)
        standin = arm_prediction(mode=name, params=p, n_list=n_standin, m_along=m_along)
        modes[name] = {
            **primary,
            "standin_N_4192": {
                "cum_speedup": standin["cum_speedup"],
                "cum_speedup_with_P": standin["cum_speedup_with_P"],
                "cum_stock_s": standin["cum_stock_s"],
                "cum_cached_s": standin["cum_cached_s"],
                "note": "Part 2 convention; confirmation uses per-genome N_i",
            },
        }
    return {
        "K": len(genomes_run),
        "m": m_along,
        "m_snapshots": snapshots_m(m_along),
        "modes": modes,
    }


def main() -> int:
    started = datetime.now(timezone.utc).isoformat()
    if not SUMMARY_ECOLI.is_file():
        print(f"STOP: missing {SUMMARY_ECOLI} (read via data/ symlink).", file=sys.stderr)
        return CURL_STOP

    acc = json.loads(ACC_PATH.read_text())
    curves = json.loads(CURVES_PATH.read_text())
    screen = json.loads(SCREEN_PATH.read_text())
    params = locked_params(screen)
    excluded = excluded_accessions(acc)

    ecoli_rows = parse_summary(SUMMARY_ECOLI)
    pool = confirm_e_pool(ecoli_rows, excluded)
    print(f"confirm_E pool={len(pool)} excluded_AB={len(excluded)}", flush=True)
    ondisk, planned, head_failed, pool_n, n_sampled = fill_confirm_e(pool)
    print(f"confirm_E planned_bytes={planned} n={len(ondisk)}", flush=True)

    dest = DATA_CONFIRM / "E"
    paths = download_rows(ondisk, dest)
    order_idx = run_order_indices(len(ondisk), CONFIRM_E_SEED)
    e_recs = []
    e_keys = []
    for pos, idx in enumerate(order_idx, start=1):
        row = ondisk[idx]
        rec, keys = genome_payload(row, paths[row.accession], idx)
        rec["position"] = pos
        rec["ondisk_index"] = idx
        e_recs.append(rec)
        e_keys.append(keys)
        print(
            f"confirm_E pos={pos} {row.accession} N={rec['n_records']} unique={rec['n_unique']}",
            flush=True,
        )

    prefix = c_prefix_indices(curves, N_GENOMES)
    if prefix != C_ORDERING0_PREFIX30:
        raise RuntimeError("C prefix drifted from CONFIRM_PROTOCOL.md")
    c_listed = acc["collections"]["C"]["genomes"]
    c_recs = []
    c_keys = []
    missing_c = []
    for pos, idx in enumerate(prefix, start=1):
        raw = c_listed[idx]
        path = ROOT / raw["path"]
        if not path.is_file():
            missing_c.append(raw["accession"])
            continue
        rec, keys = genome_payload_from_locked(raw, path, idx)
        rec["position"] = pos
        rec["ondisk_index"] = idx
        c_recs.append(rec)
        c_keys.append(keys)
        print(
            f"confirm_C pos={pos} {raw['accession']} N={rec['n_records']} unique={rec['n_unique']}",
            flush=True,
        )
    if missing_c:
        print(
            f"STOP: collection C FASTAs missing (do not copy into data_confirm/): {missing_c}",
            file=sys.stderr,
        )
        return CURL_STOP

    e_block = arm_block(genomes_run=e_recs, keysets_run=e_keys, params=params)
    c_block = arm_block(genomes_run=c_recs, keysets_run=c_keys, params=params)

    payload = {
        "protocol": PROTOCOL,
        "predict_protocol": PREDICT_PROTOCOL,
        "locked_before_timing": True,
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "primary": PRIMARY_MODE,
        "seed_confirm_E": CONFIRM_E_SEED,
        "stock_positions": list(STOCK_POS),
        "probe_n": 8,
        "probe_account": "singleton_8",
        "key": "MD5 of uppercase AA, whitespace ignored, '*' stripped, headers ignored",
        "fit_source": "results/headline_screen.json",
        "P_source": "results/hmmer_predicted_speedup_with_probe.json",
        "formula": "stock_i=a+b*N_i; cached_1=stock_1; cached_i=a+b*m(i-1)*N_i+w; P=sum(a+b*n_j)",
        "criteria": criteria_verbatim(),
        "criteria_note": (
            "Evaluated at k=30 on hmmscan only. meas = cum_stock / (P + Σ cached_i) "
            "with locked singleton_8 P. cached_frac = (Σ cached_i) / cum_stock."
        ),
        "selection": {
            "confirm_E": {
                "summary": str(SUMMARY_ECOLI.relative_to(ROOT)),
                "pool_unique_strain": pool_n,
                "sampled": n_sampled,
                "with_protein": len(ondisk),
                "planned_bytes": planned,
                "head_failed": head_failed,
                "run_order_indices": order_idx,
                "exclusions": {
                    "A_and_B_accessions": len(excluded),
                    "k12_regex": K12_RE.pattern,
                },
            },
            "confirm_C": {
                "source": "results/recurrence_accessions.json collections.C",
                "ordering": "results/recurrence_curves.json collections.C.orderings[0][:30]",
                "run_order_indices": prefix,
                "resampled": False,
            },
        },
        "modes": {
            name: {"a": p["a"], "b": p["b"], "w": p["w"]} for name, p in params.items()
        },
        "arms": {
            "confirm_E": {
                "id": "confirm_E",
                "label": "new diverse E. coli, seed 20260927",
                "genomes": e_recs,
                **e_block,
            },
            "confirm_C": {
                "id": "confirm_C",
                "label": "S. aureus collection C, first 30 of seed-20260926 ordering",
                "genomes": c_recs,
                **c_block,
            },
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}", flush=True)
    for cid, block in payload["arms"].items():
        m = block["m_snapshots"]
        scan = block["modes"]["hmmscan"]
        print(
            f"  {cid} hmmscan PRIMARY m(k=1,10,29)="
            f"{m.get('1'):.4f},{m.get('10'):.4f},{m.get('29'):.4f} "
            f"cum_speedup={scan['cum_speedup']:.3f}× "
            f"with_P={scan['cum_speedup_with_P']:.3f}× "
            f"cached_frac={scan['cached_frac_at_k30']:.3f} "
            f"--time {scan['time_request_h']}h",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
