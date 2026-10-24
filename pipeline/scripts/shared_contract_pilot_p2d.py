#!/usr/bin/env python3
"""P2d: GATE R + realistic re-pilot after verification sibling-count fix.

Same design as P2c (full Pfam-A, 500 proteins, seed 20261336, arms A/B/C,
layers A–C on). Shares the single pressed Pfam from P2c scratch. N=5 if
disk allows (≥15 GB free); else reduce with recorded reason.
Scratch: ~/tmp/tare_sharedcontract_p2d/. No CARC. Laptop walls are shape only.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(PIPE))
sys.path.insert(0, str(SCRIPTS))

import shared_contract_pilot_p2 as p2  # noqa: E402
import shared_contract_pilot_p2c as p2c  # noqa: E402

from acts.reference_run import ReferenceIncremental  # noqa: E402

SCRATCH = Path(os.path.expanduser("~/tmp/tare_sharedcontract_p2d"))
P2C_SCRATCH = Path(os.path.expanduser("~/tmp/tare_sharedcontract_p2c"))
OUT = PIPE / "results" / "shared_contract"
SEED_PROTEOME = 20261336
SEED_STOCK_PROBE = 20261338
N_PROTEINS = 500
N_GENOMES_TARGET = 5
CPU = "2"
DISK_FLOOR_GB = 15.0


def nice_self() -> None:
    try:
        os.nice(10)
    except OSError:
        pass


def free_gb(path: Path) -> float:
    usage = shutil.disk_usage(path if path.exists() else path.parent)
    return usage.free / (1024**3)


def ensure_pfam() -> Path:
    """One pressed Pfam: reuse P2c's copy via symlink into p2d scratch."""
    src = P2C_SCRATCH / "pfam" / "Pfam-A.hmm"
    if not src.is_file():
        raise SystemExit(f"P2c pressed Pfam missing: {src}")
    dest_dir = SCRATCH / "pfam"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "Pfam-A.hmm"
    if dest.is_symlink() or dest.is_file():
        if dest.resolve() != src.resolve() and not dest.samefile(src):
            dest.unlink()
            dest.symlink_to(src)
    else:
        dest.symlink_to(src)
    # Pressed sidecars live next to the real file.
    for ext in (".h3f", ".h3i", ".h3m", ".h3p"):
        side = Path(str(src) + ext)
        if not side.is_file():
            p2c.press_hmm(src)
            break
    return dest


def prepare_genomes(n: int) -> list[dict]:
    """Reuse P2c proteome subsets (same seed 20261336); else rebuild."""
    paths = p2c.choose_genomes(n, SEED_PROTEOME)
    genomes = []
    gdir = SCRATCH / "genomes"
    gdir.mkdir(parents=True, exist_ok=True)
    for src in paths:
        # P2c wrote GCF_*_protein.faa from *.faa.gz
        base = src.name[: -len(".gz")] if src.name.endswith(".gz") else src.name
        if not base.endswith(".faa"):
            base = str(Path(base).with_suffix(".faa"))
        p2c_dest = P2C_SCRATCH / "genomes" / base
        dest = gdir / base
        if p2c_dest.is_file():
            if dest.exists() or dest.is_symlink():
                dest.unlink()
            dest.symlink_to(p2c_dest)
            acc = base[: -len("_protein.faa")] if base.endswith("_protein.faa") else Path(base).stem
            meta = {
                "accession": acc,
                "path": str(dest),
                "sha256": p2c.sha256_file(p2c_dest),
                "n_proteins": N_PROTEINS,
                "reused_p2c": True,
            }
        else:
            meta = p2c.subset_faa(src, N_PROTEINS, SEED_PROTEOME, dest)
            meta["reused_p2c"] = False
        genomes.append(meta)
        print(
            f"  {meta['accession']} sha256={meta['sha256'][:12]}… "
            f"reused_p2c={meta['reused_p2c']}"
        )
    return genomes


def run_tare(*, faa, hmm, out_dir, cache, contract_store):
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    t0 = time.perf_counter()
    result = ReferenceIncremental(
        argv=p2.hmmscan_argv(CPU),
        input_path=faa,
        out_dir=out_dir,
        reference=hmm,
        cache_path=cache,
        verify="audit",
        audit_bound=True,
        audit_size=299,
        pin="-Z {entry_count}",
        prep=f"{p2c.HMMPRESS} -f {{reference}}",
        contract_store=contract_store,
    ).run()
    wall = time.perf_counter() - t0
    meta = p2.parse_decision(out_dir)
    meta["wall_s"] = wall
    meta["decision"] = result.decision
    meta["reason"] = result.reason
    meta["extra"] = dict(result.extra)
    for key, value in result.extra.items():
        if key.startswith("contract_") or key in {"phases", "probe_phases"}:
            meta[key] = value
    p2c._scrub_call_trees(out_dir)
    return meta


def realistic_batch(hmm: Path, genomes: list[dict]) -> dict:
    store = SCRATCH / "pilot" / "contract_store"
    if store.exists():
        shutil.rmtree(store)
    store.mkdir(parents=True, exist_ok=True)
    batch = {
        "genomes": [],
        "order": [g["accession"] for g in genomes],
        "n": len(genomes),
        "disk_free_gb_start": free_gb(SCRATCH),
    }
    reused = 0
    after_first = 0
    for i, g in enumerate(genomes):
        free = free_gb(SCRATCH)
        print(f"  disk free before {g['accession']}: {free:.1f} GB")
        if free < DISK_FLOOR_GB:
            batch["stopped_early"] = {
                "reason": f"free disk {free:.1f} GB < {DISK_FLOOR_GB} GB floor",
                "at_genome": g["accession"],
                "completed": len(batch["genomes"]),
            }
            print(f"STOP: {batch['stopped_early']}")
            break
        faa = Path(g["path"])
        gdir = SCRATCH / "pilot" / g["accession"]
        if gdir.exists():
            shutil.rmtree(gdir)
        gdir.mkdir(parents=True, exist_ok=True)
        stock = p2c.run_stock(faa, hmm, gdir / "stock.tbl", gdir / "stock.domtbl")
        arm_b = run_tare(
            faa=faa,
            hmm=hmm,
            out_dir=gdir / "arm_b",
            cache=gdir / "b_cache.sqlite",
            contract_store=None,
        )
        arm_b["vs_stock"] = p2c.bodies_equal_stock(
            gdir / "arm_b", gdir / "stock.tbl", gdir / "stock.domtbl"
        )
        arm_c = run_tare(
            faa=faa,
            hmm=hmm,
            out_dir=gdir / "arm_c",
            cache=gdir / "c_cache.sqlite",
            contract_store=store,
        )
        arm_c["vs_stock"] = p2c.bodies_equal_stock(
            gdir / "arm_c", gdir / "stock.tbl", gdir / "stock.domtbl"
        )
        status = arm_c.get("contract_store")
        if i > 0:
            after_first += 1
            if status == "reused":
                reused += 1
        row = {
            "accession": g["accession"],
            "sha256": g["sha256"],
            "arm_a_stock_s": stock["wall_s"],
            "arm_b": {
                "wall_s": arm_b["wall_s"],
                "decision": arm_b.get("decision"),
                "phases": arm_b.get("phases"),
                "probe_phases": arm_b.get("probe_phases"),
                "vs_stock": arm_b["vs_stock"],
            },
            "arm_c": {
                "wall_s": arm_c["wall_s"],
                "decision": arm_c.get("decision"),
                "phases": arm_c.get("phases"),
                "probe_phases": arm_c.get("probe_phases"),
                "contract_store": arm_c.get("contract_store"),
                "contract_store_reason": arm_c.get("contract_store_reason"),
                "contract_confirm_wall_s": arm_c.get("contract_confirm_wall_s"),
                "contract_refside_parse": arm_c.get("contract_refside_parse"),
                "contract_refside_prep": arm_c.get("contract_refside_prep"),
                "contract_layer_b": arm_c.get("contract_layer_b"),
                "contract_layer_c": arm_c.get("contract_layer_c"),
                "vs_stock": arm_c["vs_stock"],
            },
        }
        batch["genomes"].append(row)
        print(
            f"  {g['accession']}: stock={stock['wall_s']:.1f}s "
            f"B={arm_b['wall_s']:.1f}s C={arm_c['wall_s']:.1f}s "
            f"store={status} reason={arm_c.get('contract_store_reason')!r} "
            f"stock_id={arm_c['vs_stock']}"
        )
        (OUT / "p2d_realistic_partial.json").write_text(
            json.dumps(batch, indent=2) + "\n"
        )
        # Scrub any leftover probe-subset files under this genome.
        for arm in ("arm_b", "arm_c"):
            p2c._scrub_call_trees(gdir / arm)
    batch["q"] = (reused / after_first) if after_first else None
    batch["reused"] = reused
    batch["after_first"] = after_first
    batch["disk_free_gb_end"] = free_gb(SCRATCH)
    return batch


def main() -> int:
    nice_self()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    disk0 = free_gb(SCRATCH)
    print(f"disk free start: {disk0:.1f} GB")
    if disk0 < DISK_FLOOR_GB:
        raise SystemExit(f"not enough disk: {disk0:.1f} GB < {DISK_FLOOR_GB}")

    report: dict = {
        "seeds": {
            "proteomes": SEED_PROTEOME,
            "stock_probe": SEED_STOCK_PROBE,
            "reserved": 20261339,
            "new_randomness": 20261337,
        },
        "disk_free_gb_start": disk0,
        "confirm_n": 10,
        "confirm_n_source": "pipeline/results/shared_contract/p2d_confirm_n.json",
    }

    print("== default import check ==")
    report["default_import"] = p2c.default_import_check()
    print(report["default_import"])

    print("== GATE R ==")
    report["gate_r"] = p2c.gate_r()
    print("GATE_R", report["gate_r"]["GATE_R"])
    (OUT / "p2d_gate_r.json").write_text(json.dumps(report["gate_r"], indent=2) + "\n")

    print("== share pressed Pfam from P2c ==")
    hmm = ensure_pfam()
    report["pfam"] = {
        "path": str(hmm),
        "resolved": str(hmm.resolve()),
        "sha256": p2c.sha256_file(hmm.resolve()),
        "shared_from_p2c": True,
    }

    print("== draw proteomes ==")
    genomes = prepare_genomes(N_GENOMES_TARGET)
    report["genomes_drawn"] = genomes

    print("== stock timing probe ==")
    timing = p2c.stock_timing_probe(hmm, genomes)
    # Redirect timing artifact under p2d
    timing_dest = SCRATCH / "timing"
    timing_dest.mkdir(parents=True, exist_ok=True)
    report["stock_timing"] = timing
    print(f"stock wall={timing['wall_s']:.1f}s over_cap={timing['over_cap']}")

    n_use = N_GENOMES_TARGET
    free = free_gb(SCRATCH)
    report["n_reduced_reason"] = None
    if free < 40:
        # Heuristic: P2c needed ~disk headroom for N=3; try N=5 only if ≥40 GB.
        n_use = 3 if free < 40 else 5
        if n_use < N_GENOMES_TARGET:
            report["n_reduced_reason"] = (
                f"N={n_use}: free disk {free:.1f} GB; keep headroom for "
                f"full-Pfam probe subset writes (P2c hit Errno 28 at N=5)"
            )
    # With aggressive scrubbing and shared Pfam, attempt N=5 when free ≥25 GB.
    if free >= 25:
        n_use = 5
        report["n_reduced_reason"] = None
    else:
        n_use = 3
        report["n_reduced_reason"] = (
            f"N=3: free disk {free:.1f} GB < 25 GB safety for N=5"
        )
    genomes = genomes[:n_use]
    report["n"] = len(genomes)
    print(f"== realistic batch N={len(genomes)} (free={free:.1f} GB) ==")

    batch = realistic_batch(hmm, genomes)
    report["batch"] = batch
    report["projection"] = p2c.project_rho(batch, timing)
    report["disk_free_gb_end"] = free_gb(SCRATCH)

    stock_ok = all(
        r["arm_b"]["vs_stock"]["tbl"]
        and r["arm_b"]["vs_stock"]["domtbl"]
        and r["arm_c"]["vs_stock"]["tbl"]
        and r["arm_c"]["vs_stock"]["domtbl"]
        for r in batch["genomes"]
    ) if batch["genomes"] else False
    q = batch.get("q") or 0.0
    rho20 = report["projection"]["rho"]["20"]
    gate_r_pass = report["gate_r"]["GATE_R"] == "PASS"
    import_ok = report["default_import"]["ok"]
    go = (
        gate_r_pass
        and import_ok
        and stock_ok
        and q >= 0.8
        and rho20 <= 2.5
        and not batch.get("stopped_early")
    )
    reasons = []
    if not gate_r_pass:
        reasons.append("GATE R fail")
    if not import_ok:
        reasons.append("default path imports contract_store")
    if not stock_ok:
        reasons.append("output not stock-identical")
    if q < 0.8:
        reasons.append(f"q={q} < 0.8")
    if rho20 > 2.5:
        reasons.append(f"rho(20)={rho20:.3f} > 2.5")
    if batch.get("stopped_early"):
        reasons.append(batch["stopped_early"]["reason"])
    report["GATE"] = {
        "verdict": "GO" if go else "NO-GO",
        "reason": "all criteria met" if go else "; ".join(reasons),
        "q": q,
        "rho20": rho20,
        "stock_identical": stock_ok,
        "gate_r": report["gate_r"]["GATE_R"],
    }
    out = OUT / "p2d_realistic.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {out}")
    print("GATE", report["GATE"])
    print(f"disk free end: {report['disk_free_gb_end']:.1f} GB")
    return 0 if go else 1


if __name__ == "__main__":
    raise SystemExit(main())
