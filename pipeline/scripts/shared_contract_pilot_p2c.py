#!/usr/bin/env python3
"""P2c: GATE R re-check + realistic-size shared-contract pilot.

Seeds: primary 20261336 (proteomes); aux 20261338 (timing probe), 20261339 reserved.
Scratch: ~/tmp/tare_sharedcontract_p2c/. Constraints: --cpu 2, nice -n 10, ≤3 GB.
No CARC. Laptop walls are shape only.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(PIPE))
sys.path.insert(0, str(SCRIPTS))

# Reuse P2 helpers / GATE R harness.
import shared_contract_pilot_p2 as p2  # noqa: E402

from acts.reference_run import ReferenceIncremental  # noqa: E402

SCRATCH = Path(os.path.expanduser("~/tmp/tare_sharedcontract_p2c"))
P2_SCRATCH = Path(os.path.expanduser("~/tmp/tare_sharedcontract_p2"))
OUT = PIPE / "results" / "shared_contract"
DATA = PIPE / "data"
PFAM_GZ = DATA / "hmmer" / "Pfam-A.hmm.gz"
PROTEOME_DIR = DATA / "recurrence" / "A"

SEED_PROTEOME = 20261336  # P2c realistic primary (also P2 update-ref seed; recorded)
SEED_STOCK_PROBE = 20261338
# 20261339 reserved unused this pilot
N_PROTEINS = 500
N_GENOMES_TARGET = 5
CPU = "2"
HMMSCAN = shutil.which("hmmscan") or "/opt/homebrew/bin/hmmscan"
HMMPRESS = shutil.which("hmmpress") or "/opt/homebrew/bin/hmmpress"
STOCK_WALL_CAP_S = 20 * 60


def nice_self() -> None:
    try:
        os.nice(10)
    except OSError:
        pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def decompress_pfam(dest: Path) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 0:
        return {"path": str(dest), "sha256": sha256_file(dest), "reused": True}
    print(f"decompress {PFAM_GZ} → {dest} …")
    with gzip.open(PFAM_GZ, "rb") as src, dest.open("wb") as out:
        shutil.copyfileobj(src, out)
    return {"path": str(dest), "sha256": sha256_file(dest), "reused": False}


def press_hmm(hmm: Path) -> None:
    subprocess.run([HMMPRESS, "-f", str(hmm)], check=True, capture_output=True)


def choose_genomes(n: int, seed: int) -> list[Path]:
    rng = random.Random(seed)
    all_p = sorted(PROTEOME_DIR.glob("*.faa.gz"))
    if len(all_p) < n:
        raise SystemExit(f"need {n} proteomes, found {len(all_p)}")
    return sorted(rng.sample(all_p, n), key=lambda p: p.name)


def subset_faa(src: Path, n: int, seed: int, dest: Path) -> dict:
    return p2.subset_faa(src, n, seed, dest)


def run_stock(faa: Path, hmm: Path, out_tbl: Path, out_dom: Path) -> dict:
    out_tbl.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        HMMSCAN,
        "--cut_ga",
        "--noali",
        "--cpu",
        CPU,
        "--tblout",
        str(out_tbl),
        "--domtblout",
        str(out_dom),
        str(hmm),
        str(faa),
    ]
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    wall = time.perf_counter() - t0
    if proc.returncode != 0:
        raise SystemExit(f"stock hmmscan failed: {proc.stderr[-800:]}")
    return {
        "wall_s": wall,
        "tbl_sha256": p2.body_sha256(out_tbl),
        "domtbl_sha256": p2.body_sha256(out_dom),
        "returncode": proc.returncode,
    }


def _scrub_call_trees(out_dir: Path) -> None:
    """Drop subset-reference scratch (multi-GB on full Pfam) after tables exist."""
    for name in ("calls", "calls_pinned", "calls_infer", "calls_slack"):
        path = out_dir / name
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)


def run_tare(
    *,
    faa: Path,
    hmm: Path,
    out_dir: Path,
    cache: Path,
    contract_store: Path | None,
) -> dict:
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
        prep=f"{HMMPRESS} -f {{reference}}",
        contract_store=contract_store,
    ).run()
    wall = time.perf_counter() - t0
    meta = p2.parse_decision(out_dir)
    meta["wall_s"] = wall
    meta["decision"] = result.decision
    meta["reason"] = result.reason
    meta["extra"] = dict(result.extra)
    # Flatten contract_* keys from StrategyResult.extra (authoritative).
    for key, value in result.extra.items():
        if key.startswith("contract_") or key in {"phases", "probe_phases"}:
            meta[key] = value
    _scrub_call_trees(out_dir)
    return meta


def bodies_equal_stock(out_dir: Path, stock_tbl: Path, stock_dom: Path) -> dict:
    tables = out_dir / "tables"
    got_tbl = tables / "tbl"
    got_dom = tables / "domtbl"
    return {
        "tbl": p2.body_sha256(got_tbl) == p2.body_sha256(stock_tbl) if got_tbl.is_file() else False,
        "domtbl": p2.body_sha256(got_dom) == p2.body_sha256(stock_dom)
        if got_dom.is_file()
        else False,
    }


def gate_r() -> dict:
    """Re-run GATE R using P2 subset + main checkout at b3cd9ad."""
    man_path = P2_SCRATCH / "manifest.json"
    if not man_path.is_file():
        raise SystemExit(f"P2 manifest missing: {man_path}")
    manifest = json.loads(man_path.read_text())
    # Ensure main code present (P2 checked out b3cd9ad).
    if not (p2.MAIN_ACTS / "acts").is_dir():
        raise SystemExit(f"main code missing at {p2.MAIN_ACTS}")
    return p2.gate_r(manifest)


def default_import_check() -> dict:
    code = r"""
import sys
from pathlib import Path
sys.path.insert(0, %r)
from acts.reference_run import ReferenceIncremental
print("imported", "acts.contract_store" in sys.modules)
""" % str(PIPE)
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "ok": proc.returncode == 0 and "imported False" in proc.stdout,
    }


def stock_timing_probe(hmm: Path, genomes: list[dict]) -> dict:
    """One stock hmmscan; if >20 min, caller should drop to N=3."""
    g = genomes[0]
    dest = SCRATCH / "timing" / g["accession"]
    dest.mkdir(parents=True, exist_ok=True)
    press_hmm(hmm)
    row = run_stock(
        Path(g["path"]),
        hmm,
        dest / "stock.tbl",
        dest / "stock.domtbl",
    )
    row["accession"] = g["accession"]
    row["over_cap"] = row["wall_s"] > STOCK_WALL_CAP_S
    return row


def _load_completed_row(g: dict, gdir: Path) -> dict | None:
    """Resume helper: rebuild a batch row if arm_c decision exists."""
    dec = gdir / "arm_c" / "decision.txt"
    stock_tbl = gdir / "stock.tbl"
    if not dec.is_file() or not stock_tbl.is_file():
        return None
    arm_b_meta = p2.parse_decision(gdir / "arm_b") if (gdir / "arm_b" / "decision.txt").is_file() else {}
    arm_c_meta = p2.parse_decision(gdir / "arm_c")
    # Wall times from phases.total_s when resume lacks wall_s.
    def wall_of(meta: dict) -> float:
        phases = meta.get("phases") or {}
        return float(phases.get("total_s") or meta.get("wall_s") or 0.0)

    stock_wall = 0.0
    timing = SCRATCH / "timing" / g["accession"] / "stock.tbl"
    # Prefer per-genome stock body compare; wall unknown on resume → 0.
    row = {
        "accession": g["accession"],
        "sha256": g["sha256"],
        "arm_a_stock_s": stock_wall,
        "resumed": True,
        "arm_b": {
            "wall_s": wall_of(arm_b_meta),
            "decision": arm_b_meta.get("decision"),
            "phases": arm_b_meta.get("phases"),
            "probe_phases": arm_b_meta.get("probe_phases"),
            "vs_stock": bodies_equal_stock(
                gdir / "arm_b", gdir / "stock.tbl", gdir / "stock.domtbl"
            ),
        },
        "arm_c": {
            "wall_s": wall_of(arm_c_meta),
            "decision": arm_c_meta.get("decision"),
            "phases": arm_c_meta.get("phases"),
            "probe_phases": arm_c_meta.get("probe_phases"),
            "contract_store": arm_c_meta.get("contract_store"),
            "contract_confirm_wall_s": arm_c_meta.get("contract_confirm_wall_s"),
            "contract_refside_parse": arm_c_meta.get("contract_refside_parse"),
            "contract_refside_prep": arm_c_meta.get("contract_refside_prep"),
            "contract_layer_b": arm_c_meta.get("contract_layer_b"),
            "contract_layer_c": arm_c_meta.get("contract_layer_c"),
            "vs_stock": bodies_equal_stock(
                gdir / "arm_c", gdir / "stock.tbl", gdir / "stock.domtbl"
            ),
        },
    }
    return row


def realistic_batch(hmm: Path, genomes: list[dict], *, resume: bool = True) -> dict:
    store = SCRATCH / "pilot" / "contract_store"
    if not resume and store.exists():
        shutil.rmtree(store)
    store.mkdir(parents=True, exist_ok=True)
    batch = {
        "genomes": [],
        "order": [g["accession"] for g in genomes],
        "n": len(genomes),
    }
    reused = 0
    after_first = 0
    for i, g in enumerate(genomes):
        faa = Path(g["path"])
        gdir = SCRATCH / "pilot" / g["accession"]
        if resume:
            prior = _load_completed_row(g, gdir)
            if prior is not None:
                status = prior["arm_c"].get("contract_store")
                if i > 0:
                    after_first += 1
                    if status == "reused":
                        reused += 1
                batch["genomes"].append(prior)
                print(
                    f"  {g['accession']}: RESUMED store={status} "
                    f"stock_id={prior['arm_c']['vs_stock']}"
                )
                continue
        if gdir.exists() and not resume:
            shutil.rmtree(gdir)
        gdir.mkdir(parents=True, exist_ok=True)
        stock = run_stock(faa, hmm, gdir / "stock.tbl", gdir / "stock.domtbl")
        arm_b = run_tare(
            faa=faa,
            hmm=hmm,
            out_dir=gdir / "arm_b",
            cache=gdir / "b_cache.sqlite",
            contract_store=None,
        )
        arm_b["vs_stock"] = bodies_equal_stock(
            gdir / "arm_b", gdir / "stock.tbl", gdir / "stock.domtbl"
        )
        arm_c = run_tare(
            faa=faa,
            hmm=hmm,
            out_dir=gdir / "arm_c",
            cache=gdir / "c_cache.sqlite",
            contract_store=store,
        )
        arm_c["vs_stock"] = bodies_equal_stock(
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
            f"store={row['arm_c']['contract_store']} "
            f"stock_id={arm_c['vs_stock']}"
        )
        # Persist partial after each genome so a disk kill is not total loss.
        (OUT / "p2c_realistic_partial.json").write_text(
            json.dumps(batch, indent=2) + "\n"
        )
    batch["q"] = (reused / after_first) if after_first else None
    batch["reused"] = reused
    batch["after_first"] = after_first
    return batch


def project_rho(batch: dict, timing: dict) -> dict:
    """Project ρ(N) on W5x numbers with measured laptop q and layer costs."""
    # W5x MEASURED (SHARED_CONTRACT_DESIGN.md / PILOT): stock T, first-run F.
    T = 1013.7 / 4.20  # 241.36 s — W5x stock
    F = 1013.7  # W5x first-run total
    # Laptop-measured shapes for V and L.
    rows = batch["genomes"]
    if not rows:
        return {"error": "no genomes"}
    f1_laptop = rows[0]["arm_c"]["wall_s"]
    # G ≈ arm_c wall on reused genomes minus V; fall back to arm_c - confirm.
    reused_rows = [r for r in rows[1:] if r["arm_c"].get("contract_store") == "reused"]
    fail_rows = [r for r in rows[1:] if r["arm_c"].get("contract_store") != "reused"]
    V_vals = [
        float(r["arm_c"].get("contract_confirm_wall_s") or 0.0)
        for r in rows[1:]
        if r["arm_c"].get("contract_confirm_wall_s") is not None
    ]
    V_laptop = sum(V_vals) / len(V_vals) if V_vals else 0.0
    # Layer A saving: parse+prep difference hit vs stored on later genomes.
    # Approximate L from parse_s on first vs later when prep/parse hit.
    parse_first = float((rows[0]["arm_c"].get("phases") or {}).get("parse_s") or 0.0)
    parse_later = [
        float((r["arm_c"].get("phases") or {}).get("parse_s") or 0.0)
        for r in rows[1:]
        if r["arm_c"].get("contract_refside_parse") == "hit"
    ]
    L_laptop = (
        max(0.0, parse_first - (sum(parse_later) / len(parse_later)))
        if parse_later
        else 0.0
    )
    # Scale V and L to W5x by probe ratio when available.
    probe_b = [
        float((r["arm_b"].get("phases") or {}).get("probe_wall_s") or 0.0) for r in rows
    ]
    probe_b = [p for p in probe_b if p > 0]
    mean_probe_laptop = sum(probe_b) / len(probe_b) if probe_b else None
    P_w5x = 538.5
    scale = (P_w5x / mean_probe_laptop) if mean_probe_laptop else 1.0
    V = V_laptop * scale
    L = L_laptop * scale
    # G: per-genome remainder when reused ≈ F - P (probe skipped), W5x conservative.
    G = F - P_w5x  # 475.2 — share probe only; pin still paid (matches pilot)
    q = batch.get("q")
    if q is None:
        q = 0.0
    F1 = F  # first genome pays full first run on server

    def batch_n(n: int) -> float:
        return F1 + (n - 1) * (q * (G + V) + (1 - q) * (F + V)) - (n - 1) * L

    def rho(n: int) -> float:
        return batch_n(n) / (n * T)

    return {
        "sources": {
            "T": "W5x stock = 1013.7/4.20 (DESIGN/PILOT)",
            "F": "W5x first-run total_s 1013.7",
            "F1": "same as F (first genome full first run)",
            "G": "F - P = 1013.7 - 538.5 (probe shared; pin per genome)",
            "P": "W5x probe_phases sum 538.5",
            "V": f"laptop mean confirm_wall_s {V_laptop:.3f} × scale {scale:.3f}",
            "L": f"laptop parse_s saving {L_laptop:.3f} × scale {scale:.3f}",
            "q": f"laptop reuse fraction {q} ({batch.get('reused')}/{batch.get('after_first')})",
            "scale": f"P_w5x/mean_laptop_probe = {P_w5x}/{mean_probe_laptop}",
        },
        "values": {
            "T": T,
            "F": F,
            "F1": F1,
            "G": G,
            "V": V,
            "L": L,
            "q": q,
            "V_laptop": V_laptop,
            "L_laptop": L_laptop,
            "scale": scale,
            "f1_laptop": f1_laptop,
            "stock_timing_s": timing.get("wall_s"),
        },
        "rho": {str(n): rho(n) for n in (1, 5, 20, 100)},
        "batch": {str(n): batch_n(n) for n in (1, 5, 20, 100)},
        "gate_rho20_le_2_5": rho(20) <= 2.5,
    }


def main() -> int:
    # Soft budget: nice + 2 threads. Do not RLIMIT_AS — full Pfam-A exceeds 3 GB.
    nice_self()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "seeds": {
            "proteomes": SEED_PROTEOME,
            "stock_probe": SEED_STOCK_PROBE,
            "reserved": 20261339,
            "note": "20261336 also used as P2 SEED_UPDATE_REF; reused here as P2c primary by prompt",
        }
    }

    print("== default import check ==")
    report["default_import"] = default_import_check()
    print(report["default_import"])

    print("== GATE R ==")
    report["gate_r"] = gate_r()
    print("GATE_R", report["gate_r"]["GATE_R"])
    (OUT / "p2c_gate_r.json").write_text(json.dumps(report["gate_r"], indent=2) + "\n")

    print("== prepare full Pfam-A ==")
    hmm = SCRATCH / "pfam" / "Pfam-A.hmm"
    report["pfam"] = decompress_pfam(hmm)
    press_hmm(hmm)
    report["pfam"]["pressed"] = True

    print("== draw proteomes ==")
    paths = choose_genomes(N_GENOMES_TARGET, SEED_PROTEOME)
    genomes = []
    for src in paths:
        dest = SCRATCH / "genomes" / src.name.replace(".gz", "")
        # strip .gz → .faa
        if dest.suffix != ".faa":
            dest = dest.with_suffix(".faa")
        meta = subset_faa(src, N_PROTEINS, SEED_PROTEOME, dest)
        genomes.append(meta)
        print(f"  {meta['accession']} sha256={meta['sha256'][:12]}…")
    report["genomes"] = genomes

    print("== stock timing probe ==")
    timing_path = OUT / "p2c_stock_timing.json"
    if timing_path.is_file():
        timing = json.loads(timing_path.read_text())
        print(f"reused timing wall={timing['wall_s']:.1f}s")
    else:
        timing = stock_timing_probe(hmm, genomes)
        timing_path.write_text(json.dumps(timing, indent=2) + "\n")
    report["stock_timing"] = timing
    print(f"stock wall={timing['wall_s']:.1f}s over_cap={timing['over_cap']}")
    # Full-Pfam subset writes ~10–20 GB/genome on this laptop; cap N=3 for disk.
    n_use = 3
    report["n_reduced_reason"] = (
        "N=3: full-Pfam probe subset writes exhausted disk at genome 2 of 5 "
        "(Errno 28); stock wall was under 20 min"
    )
    if timing["over_cap"]:
        report["n_reduced_reason"] += "; also stock > 20 min"
    genomes = genomes[:n_use]
    report["n"] = len(genomes)

    print(f"== realistic batch N={len(genomes)} ==")
    batch = realistic_batch(hmm, genomes)
    report["batch"] = batch
    report["projection"] = project_rho(batch, timing)

    stock_ok = all(
        r["arm_b"]["vs_stock"]["tbl"]
        and r["arm_b"]["vs_stock"]["domtbl"]
        and r["arm_c"]["vs_stock"]["tbl"]
        and r["arm_c"]["vs_stock"]["domtbl"]
        for r in batch["genomes"]
    )
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
    report["GATE"] = {
        "verdict": "GO" if go else "NO-GO",
        "reason": "all criteria met" if go else "; ".join(reasons),
        "q": q,
        "rho20": rho20,
        "stock_identical": stock_ok,
        "gate_r": report["gate_r"]["GATE_R"],
    }
    out = OUT / "p2c_realistic.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {out}")
    print("GATE", report["GATE"])
    return 0 if go else 1


if __name__ == "__main__":
    raise SystemExit(main())
