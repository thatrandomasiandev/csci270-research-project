#!/usr/bin/env python3
"""Laptop pilot for --contract-store (P2). Shape only; not paper results.

Seeds: primary 20261332 (also reserved in tests as SEED_B); aux 20261334–20261337.
Scratch: ~/tmp/tare_sharedcontract_p2/. Constraints: --cpu 2, nice -n 10.
"""
from __future__ import annotations

import ast
import gzip
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
ROOT = PIPE.parent
sys.path.insert(0, str(PIPE))

from acts.reference_formats import read_records  # noqa: E402
from acts.reference_run import ReferenceIncremental, body_lines  # noqa: E402

SCRATCH = Path(os.path.expanduser("~/tmp/tare_sharedcontract_p2"))
DATA = PIPE / "data"
PFAM_GZ = DATA / "hmmer" / "Pfam-A.hmm.gz"
PROTEOME_DIR = DATA / "recurrence" / "A"
OUT = PIPE / "results" / "shared_contract"
MAIN_ACTS = SCRATCH / "main_code" / "pipeline"

SEED = 20261332
SEED_PROTEOME_SUBSET = 20261334
SEED_PFAM_SUBSET = 20261335
SEED_UPDATE_REF = 20261336
SEED_CONTRADICTION = 20261337
# 20261333 reserved (P1 smoke); 20261338–39 reserved unused this pilot

N_GENOMES = 5
N_PROTEINS = 300
N_MODELS = 3000
CPU = "2"
WALL_KEYS = re.compile(r"(_s|wall|total_s|probe_wall):", re.I)
HMMSCAN = shutil.which("hmmscan") or "/opt/homebrew/bin/hmmscan"
HMMPRESS = shutil.which("hmmpress") or "/opt/homebrew/bin/hmmpress"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def strip_wall_lines(text: str) -> str:
    keep = []
    for line in text.splitlines():
        if WALL_KEYS.search(line) or line.startswith("phases:") or line.startswith("probe_phases:"):
            continue
        keep.append(line)
    return "\n".join(keep) + ("\n" if keep else "")


def iter_hmm_blocks(src: Path):
    opener = gzip.open if str(src).endswith(".gz") else open
    with opener(src, "rt") as handle:
        buf: list[str] = []
        for line in handle:
            buf.append(line)
            if line.startswith("//"):
                yield "".join(buf)
                buf = []


def extract_seeded_models(src: Path, n: int, seed: int, dest: Path) -> dict:
    """Reservoir-sample n HMM blocks; write uncompressed .hmm. Disclosed subset."""
    rng = random.Random(seed)
    reservoir: list[str] = []
    total = 0
    for block in iter_hmm_blocks(src):
        total += 1
        if len(reservoir) < n:
            reservoir.append(block)
        else:
            j = rng.randrange(total)
            if j < n:
                reservoir[j] = block
    if len(reservoir) < n:
        raise SystemExit(f"only {len(reservoir)} models in {src}, need {n}")
    # stable order by NAME for reproducibility of file bytes given same set
    def name_of(b: str) -> str:
        for line in b.splitlines():
            if line.startswith("NAME "):
                return line.split()[1]
        return ""

    reservoir.sort(key=name_of)
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(reservoir)
    dest.write_text(text)
    names = [name_of(b) for b in reservoir]
    return {
        "path": str(dest),
        "n_models": len(reservoir),
        "source_total_seen": total,
        "seed": seed,
        "sha256": sha256_file(dest),
        "first5_names": names[:5],
        "last5_names": names[-5:],
    }


def list_proteomes() -> list[Path]:
    return sorted(PROTEOME_DIR.glob("*.faa.gz"))


def choose_genomes(n: int, seed: int) -> list[Path]:
    rng = random.Random(seed)
    all_p = list_proteomes()
    if len(all_p) < n:
        raise SystemExit(f"need {n} proteomes, found {len(all_p)}")
    return sorted(rng.sample(all_p, n), key=lambda p: p.name)


def subset_faa(src: Path, n: int, seed: int, dest: Path) -> dict:
    """Seeded subset of n records from gzipped proteome."""
    # Read all headers+seqs (proteomes are a few MB uncompressed)
    records: list[tuple[str, str]] = []
    opener = gzip.open if str(src).endswith(".gz") else open
    with opener(src, "rt") as handle:
        header = None
        seq: list[str] = []
        for line in handle:
            if line.startswith(">"):
                if header is not None:
                    records.append((header, "".join(seq)))
                header = line.rstrip("\n")
                seq = []
            else:
                seq.append(line.strip())
        if header is not None:
            records.append((header, "".join(seq)))
    if len(records) < n:
        raise SystemExit(f"{src} has {len(records)} proteins, need {n}")
    rng = random.Random(f"{seed}:{src.name}")
    picked = rng.sample(records, n)
    picked.sort(key=lambda r: r[0])
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w") as out:
        for h, s in picked:
            out.write(h + "\n")
            for i in range(0, len(s), 60):
                out.write(s[i : i + 60] + "\n")
    return {
        "source": src.name,
        "accession": src.name.replace("_protein.faa.gz", ""),
        "n_proteins": n,
        "source_n": len(records),
        "seed": seed,
        "path": str(dest),
        "sha256": sha256_file(dest),
    }


def hmmscan_argv(cpu: str = CPU) -> list[str]:
    return [
        HMMSCAN,
        "--cut_ga",
        "--noali",
        "--cpu",
        cpu,
        "--tblout",
        "{output:tbl}",
        "--domtblout",
        "{output:domtbl}",
        "{reference}",
        "{input}",
    ]


def run_stock(faa: Path, hmm: Path, out_tbl: Path, out_dom: Path) -> dict:
    out_tbl.parent.mkdir(parents=True, exist_ok=True)
    # Ensure pressed
    subprocess.run([HMMPRESS, "-f", str(hmm)], check=True, capture_output=True)
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
        "tbl_sha256": sha256_file(out_tbl),
        "domtbl_sha256": sha256_file(out_dom),
        "returncode": proc.returncode,
    }


def body_lines(path: Path) -> list[str]:
    """Non-comment lines, whitespace-normalized (hmmscan footers embed paths/dates)."""
    lines = []
    for line in path.read_text().splitlines():
        if line.startswith("#"):
            continue
        lines.append(" ".join(line.split()))
    return lines


def body_sha256(path: Path) -> str:
    return sha256_bytes(("\n".join(body_lines(path)) + "\n").encode())


def collect_tables(out_dir: Path) -> dict[str, str]:
    """Body sha256 per table (ignores hmmscan comment headers with paths/dates)."""
    tables = {}
    tdir = out_dir / "tables"
    if not tdir.is_dir():
        return tables
    for p in sorted(tdir.iterdir()):
        if p.is_file() and not p.name.endswith(".json"):
            tables[p.name] = body_sha256(p)
    return tables


def parse_decision(out_dir: Path) -> dict:
    path = out_dir / "decision.txt"
    text = path.read_text() if path.is_file() else ""
    meta = {
        "decision_txt": text,
        "stripped": strip_wall_lines(text),
        "stripped_sha256": sha256_bytes(strip_wall_lines(text).encode()),
        "tables": collect_tables(out_dir),
    }
    for line in text.splitlines():
        if line.startswith("phases:"):
            try:
                meta["phases"] = ast.literal_eval(line[len("phases:") :].strip())
            except (SyntaxError, ValueError):
                pass
            continue
        if line.startswith("probe_phases:"):
            try:
                meta["probe_phases"] = ast.literal_eval(line[len("probe_phases:") :].strip())
            except (SyntaxError, ValueError):
                pass
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            k = k.strip()
            v = v.strip()
            if k in {
                "decision",
                "why",
                "reason",
                "contract_store",
                "contract_key",
                "contract_confirmations",
                "contract_store_reason",
                "contract_confirm_wall_s",
            }:
                meta[k if k != "why" else "reason"] = v
    return meta


def run_tare(
    *,
    code_root: Path,
    faa: Path,
    hmm: Path,
    out_dir: Path,
    cache: Path,
    contract_store: Path | None,
    label: str,
) -> dict:
    """Run TARE via subprocess so PYTHONPATH selects main vs branch code."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(code_root)
    argv = [
        "nice",
        "-n",
        "10",
        sys.executable,
        "-m",
        "acts",
        "run",
        "--strategy",
        "reference",
        "--input",
        str(faa),
        "--reference",
        str(hmm),
        "--out",
        str(out_dir),
        "--cache",
        str(cache),
        "--verify",
        "audit",
        "--pin",
        "-Z {entry_count}",
        "--prep",
        "hmmpress -f {reference}",
    ]
    if contract_store is not None:
        argv.extend(["--contract-store", str(contract_store)])
    argv.append("--")
    argv.extend(hmmscan_argv())
    log = SCRATCH / "logs" / f"{label}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    with log.open("w") as lf:
        proc = subprocess.run(
            argv,
            cwd=str(code_root.parent if (code_root / "acts").is_dir() else code_root),
            env=env,
            stdout=lf,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    wall = time.perf_counter() - t0
    # Prefer reading phases from decision / a side JSON if present.
    # Re-import is wrong across code roots; parse decision.txt + optional phases file.
    meta = parse_decision(out_dir)
    phases = {}
    probe_phases = {}
    for line in meta["decision_txt"].splitlines():
        if line.startswith("phases:"):
            try:
                phases = ast.literal_eval(line[len("phases:") :].strip())
            except (SyntaxError, ValueError):
                pass
        if line.startswith("probe_phases:"):
            try:
                probe_phases = ast.literal_eval(line[len("probe_phases:") :].strip())
            except (SyntaxError, ValueError):
                pass
    return {
        "label": label,
        "wall_s": wall,
        "returncode": proc.returncode,
        "log": str(log),
        "decision": meta.get("decision"),
        "reason": meta.get("reason"),
        "contract_store": meta.get("contract_store"),
        "contract_key": meta.get("contract_key"),
        "contract_confirmations": meta.get("contract_confirmations"),
        "contract_confirm_wall_s": meta.get("contract_confirm_wall_s"),
        "contract_store_reason": meta.get("contract_store_reason"),
        "stripped_sha256": meta["stripped_sha256"],
        "tables": meta["tables"],
        "phases": phases,
        "probe_phases": probe_phases,
        "code_root": str(code_root),
    }


def run_tare_inprocess(
    *,
    faa: Path,
    hmm: Path,
    out_dir: Path,
    cache: Path,
    contract_store: Path | None,
    label: str,
) -> dict:
    """Branch-code in-process run (captures phases from StrategyResult)."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    t0 = time.perf_counter()
    rec = ReferenceIncremental(
        argv=hmmscan_argv(),
        input_path=faa,
        out_dir=out_dir,
        reference=hmm,
        cache_path=cache,
        verify="audit",
        pin="-Z {entry_count}",
        prep="hmmpress -f {reference}",
        contract_store=contract_store,
    ).run()
    wall = time.perf_counter() - t0
    meta = parse_decision(out_dir)
    return {
        "label": label,
        "wall_s": wall,
        "decision": rec.decision,
        "reason": rec.reason,
        "contract_store": (rec.extra or {}).get("contract_store") or meta.get("contract_store"),
        "contract_key": (rec.extra or {}).get("contract_key") or meta.get("contract_key"),
        "contract_confirmations": (rec.extra or {}).get("contract_confirmations")
        or meta.get("contract_confirmations"),
        "contract_confirm_wall_s": (rec.extra or {}).get("contract_confirm_wall_s")
        or meta.get("contract_confirm_wall_s"),
        "contract_store_reason": (rec.extra or {}).get("contract_store_reason")
        or meta.get("contract_store_reason"),
        "stripped_sha256": meta["stripped_sha256"],
        "tables": meta["tables"],
        "phases": dict((rec.extra or {}).get("phases") or {}),
        "probe_phases": dict((rec.extra or {}).get("probe_phases") or {}),
        "extra_contract": {
            k: (rec.extra or {}).get(k)
            for k in (
                "contract_store",
                "contract_key",
                "contract_confirmations",
                "contract_confirm_wall_s",
                "contract_store_reason",
                "contract_store_write",
            )
            if (rec.extra or {}).get(k) is not None
        },
    }


def bodies_equal_stock(tare_dir: Path, stock_tbl: Path, stock_dom: Path) -> dict:
    """Compare TARE table bodies to stock (whitespace-normalized, comment-stripped)."""
    tdir = tare_dir / "tables"
    out = {}
    for name, stock_path in (("tbl", stock_tbl), ("domtbl", stock_dom)):
        cand = tdir / name
        if not cand.is_file() and tdir.is_dir():
            matches = [p for p in tdir.iterdir() if p.is_file() and name in p.name]
            cand = matches[0] if matches else cand
        if not cand.is_file():
            out[name] = {"ok": False, "reason": f"missing tare table {name}", "dir": sorted(p.name for p in tdir.iterdir()) if tdir.is_dir() else []}
            continue

        sb, tb = body_lines(stock_path), body_lines(cand)
        out[name] = {
            "ok": sb == tb,
            "stock_body_sha256": body_sha256(stock_path),
            "tare_body_sha256": body_sha256(cand),
            "stock_nrows": len(sb),
            "tare_nrows": len(tb),
        }
    return out


def prepare_data() -> dict:
    data_dir = SCRATCH / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    hmm_meta = extract_seeded_models(PFAM_GZ, N_MODELS, SEED_PFAM_SUBSET, data_dir / "pfam_subset.hmm")
    # update reference: drop 40, add 40 other models (for GATE R update)
    rng = random.Random(SEED_UPDATE_REF)
    blocks = list(iter_hmm_blocks(PFAM_GZ))
    # build update set: take subset names, replace 40
    subset_text = Path(hmm_meta["path"]).read_text()
    subset_blocks = []
    buf: list[str] = []
    for line in subset_text.splitlines(keepends=True):
        buf.append(line)
        if line.startswith("//"):
            subset_blocks.append("".join(buf))
            buf = []

    def name_of(b: str) -> str:
        for line in b.splitlines():
            if line.startswith("NAME "):
                return line.split()[1]
        return ""

    subset_names = {name_of(b) for b in subset_blocks}
    others = [b for b in blocks if name_of(b) not in subset_names]
    drop_idx = sorted(rng.sample(range(len(subset_blocks)), 40), reverse=True)
    kept = [b for i, b in enumerate(subset_blocks) if i not in set(drop_idx)]
    add = rng.sample(others, 40)
    update_blocks = kept + add
    update_blocks.sort(key=name_of)
    update_path = data_dir / "pfam_subset_update.hmm"
    update_path.write_text("".join(update_blocks))
    update_meta = {
        "path": str(update_path),
        "n_models": len(update_blocks),
        "seed": SEED_UPDATE_REF,
        "sha256": sha256_file(update_path),
        "n_dropped": 40,
        "n_added": 40,
    }
    genomes = choose_genomes(N_GENOMES, SEED)
    genome_metas = []
    for g in genomes:
        dest = data_dir / "genomes" / f"{g.name.replace('.faa.gz', '')}.faa"
        meta = subset_faa(g, N_PROTEINS, SEED_PROTEOME_SUBSET, dest)
        genome_metas.append(meta)
    # GATE R genome = first
    return {
        "pfam_subset": hmm_meta,
        "pfam_update": update_meta,
        "genomes": genome_metas,
        "seeds": {
            "primary": SEED,
            "proteome_subset": SEED_PROTEOME_SUBSET,
            "pfam_subset": SEED_PFAM_SUBSET,
            "update_ref": SEED_UPDATE_REF,
            "contradiction": SEED_CONTRADICTION,
            "p1_smoke_reserved": 20261333,
            "test_SEED_B_overlap_note": "20261332 also used in tests/test_shared_contract.py as SEED_B",
        },
        "full_pfam_note": (
            "Full Pfam-A has 30134 models; laptop stock of one full proteome "
            "vs full Pfam exceeds 10 min at 2 threads (not timed to completion; "
            "using seeded 3000-model subset per protocol)."
        ),
        "n_proteins_per_genome": N_PROTEINS,
        "cpu": CPU,
    }


def calibrate_stock(faa: Path, hmm: Path) -> dict:
    d = SCRATCH / "calib"
    d.mkdir(parents=True, exist_ok=True)
    return run_stock(faa, hmm, d / "stock.tbl", d / "stock.domtbl")


def gate_r(manifest: dict) -> dict:
    """Fill+update without --contract-store: main (b3cd9ad) vs branch."""
    faa = Path(manifest["genomes"][0]["path"])
    hmm = Path(manifest["pfam_subset"]["path"])
    hmm2 = Path(manifest["pfam_update"]["path"])
    branch_root = PIPE
    main_root = MAIN_ACTS
    if not (main_root / "acts").is_dir():
        raise SystemExit(f"main code missing at {main_root}")

    results = {"genome": manifest["genomes"][0]["accession"], "arms": {}}
    for tag, code in (("main", main_root), ("branch", branch_root)):
        base = SCRATCH / "gate_r" / tag
        if base.exists():
            shutil.rmtree(base)
        base.mkdir(parents=True)
        cache = base / "cache.sqlite"
        fill = run_tare(
            code_root=code,
            faa=faa,
            hmm=hmm,
            out_dir=base / "fill",
            cache=cache,
            contract_store=None,
            label=f"gate_r_{tag}_fill",
        )
        update = run_tare(
            code_root=code,
            faa=faa,
            hmm=hmm2,
            out_dir=base / "update",
            cache=cache,
            contract_store=None,
            label=f"gate_r_{tag}_update",
        )
        results["arms"][tag] = {"fill": fill, "update": update}

    # Compare stripped decision + table hashes
    cmp = {}
    for kind in ("fill", "update"):
        m = results["arms"]["main"][kind]
        b = results["arms"]["branch"][kind]
        cmp[kind] = {
            "stripped_match": m["stripped_sha256"] == b["stripped_sha256"],
            "tables_match": m["tables"] == b["tables"],
            "main_stripped": m["stripped_sha256"],
            "branch_stripped": b["stripped_sha256"],
            "main_tables": m["tables"],
            "branch_tables": b["tables"],
            "main_decision": m.get("decision"),
            "branch_decision": b.get("decision"),
        }
    results["compare"] = cmp
    results["GATE_R"] = (
        "PASS"
        if all(cmp[k]["stripped_match"] and cmp[k]["tables_match"] for k in cmp)
        else "FAIL"
    )
    return results


def pilot_batch(manifest: dict) -> dict:
    hmm = Path(manifest["pfam_subset"]["path"])
    store = SCRATCH / "pilot" / "contract_store"
    if store.exists():
        shutil.rmtree(store)
    store.mkdir(parents=True)
    batch = {"genomes": [], "order": [g["accession"] for g in manifest["genomes"]]}
    for i, g in enumerate(manifest["genomes"]):
        faa = Path(g["path"])
        gdir = SCRATCH / "pilot" / g["accession"]
        gdir.mkdir(parents=True, exist_ok=True)
        # Arm A: stock
        stock = run_stock(faa, hmm, gdir / "stock.tbl", gdir / "stock.domtbl")
        # Arm B: TARE no store (fresh cache)
        b_cache = gdir / "b_cache.sqlite"
        if b_cache.exists():
            b_cache.unlink()
        arm_b = run_tare_inprocess(
            faa=faa,
            hmm=hmm,
            out_dir=gdir / "arm_b",
            cache=b_cache,
            contract_store=None,
            label=f"pilot_B_{g['accession']}",
        )
        arm_b["vs_stock"] = bodies_equal_stock(gdir / "arm_b", gdir / "stock.tbl", gdir / "stock.domtbl")
        # Arm C: TARE with store (shared across genomes, fixed order)
        c_cache = gdir / "c_cache.sqlite"
        if c_cache.exists():
            c_cache.unlink()
        arm_c = run_tare_inprocess(
            faa=faa,
            hmm=hmm,
            out_dir=gdir / "arm_c",
            cache=c_cache,
            contract_store=store,
            label=f"pilot_C_{g['accession']}",
        )
        arm_c["vs_stock"] = bodies_equal_stock(gdir / "arm_c", gdir / "stock.tbl", gdir / "stock.domtbl")
        arm_c["genome_index"] = i
        batch["genomes"].append(
            {
                "accession": g["accession"],
                "faa_sha256": g["sha256"],
                "arm_A_stock": stock,
                "arm_B": arm_b,
                "arm_C": arm_c,
            }
        )
    # byte-identical gate
    batch["all_byte_identical_to_stock"] = all(
        all(v.get("ok") for v in g["arm_B"]["vs_stock"].values())
        and all(v.get("ok") for v in g["arm_C"]["vs_stock"].values())
        for g in batch["genomes"]
    )
    return batch


def safety_checks(manifest: dict, pilot: dict) -> dict:
    hmm = Path(manifest["pfam_subset"]["path"])
    out: dict = {}
    # 1. Contradiction: genome whose probe sample contradicts stored roles.
    # Build a tiny genome with constant-looking then varying column behavior is hard
    # with real hmmscan. Instead: poison the store with a wrong fit signature by
    # saving a corrupted roles payload, then run a real genome — expect confirm_fail
    # and stock-identical output.
    from acts.contract_store import ContractStore, contract_key, shareable_payload

    store = SCRATCH / "safety" / "contradiction_store"
    if store.exists():
        shutil.rmtree(store)
    store.mkdir(parents=True)
    g0 = Path(manifest["genomes"][0]["path"])
    # First: honest store from genome 0
    cache0 = SCRATCH / "safety" / "c0.sqlite"
    if cache0.exists():
        cache0.unlink()
    r0 = run_tare_inprocess(
        faa=g0,
        hmm=hmm,
        out_dir=SCRATCH / "safety" / "c0",
        cache=cache0,
        contract_store=store,
        label="safety_store_seed",
    )
    # Corrupt the stored fit: flip a column member if present
    st = ContractStore(store)
    key = r0.get("contract_key") or (r0.get("extra_contract") or {}).get("contract_key")
    # discover key from store files
    files = list(store.glob("*.json"))
    assert files, "no store files after seed"
    payload_path = files[0]
    payload = json.loads(payload_path.read_text())
    fit = payload.get("fit") or payload
    tables = fit.get("tables") or []
    flipped = False
    for t in tables:
        for c in t.get("columns") or []:
            if c.get("member") == "identity":
                c["member"] = "entry_count"
                flipped = True
                break
            if c.get("role") == "numeric" and c.get("member"):
                c["member"] = "identity" if c["member"] != "identity" else "entry_count"
                flipped = True
                break
        if flipped:
            break
    if not flipped and tables:
        # force a bogus record_col
        tables[0]["record_col"] = 99
        flipped = True
    payload_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    # Run genome 1 against poisoned store
    g1 = Path(manifest["genomes"][1]["path"])
    cache1 = SCRATCH / "safety" / "c1.sqlite"
    if cache1.exists():
        cache1.unlink()
    r1 = run_tare_inprocess(
        faa=g1,
        hmm=hmm,
        out_dir=SCRATCH / "safety" / "c1",
        cache=cache1,
        contract_store=store,
        label="safety_contradiction",
    )
    stock1 = run_stock(
        g1, hmm, SCRATCH / "safety" / "c1_stock.tbl", SCRATCH / "safety" / "c1_stock.domtbl"
    )
    vs = bodies_equal_stock(
        SCRATCH / "safety" / "c1",
        SCRATCH / "safety" / "c1_stock.tbl",
        SCRATCH / "safety" / "c1_stock.domtbl",
    )
    status = r1.get("contract_store") or (r1.get("extra_contract") or {}).get("contract_store")
    out["contradiction"] = {
        "seed_run": {"decision": r0.get("decision"), "contract_store": r0.get("contract_store")},
        "poisoned_flipped": flipped,
        "followup": {
            "decision": r1.get("decision"),
            "contract_store": status,
            "reason": r1.get("contract_store_reason") or r1.get("reason"),
            "vs_stock": vs,
        },
        "pass": status == "confirm_fail"
        and r1.get("decision") in {"SHIP", "FALLBACK"}
        and all(v.get("ok") for v in vs.values()),
    }

    # 2. Key isolation: different argv must not reuse
    store2 = SCRATCH / "safety" / "key_store"
    if store2.exists():
        shutil.rmtree(store2)
    store2.mkdir(parents=True)
    # seed with --cut_ga path via normal run
    cache_k = SCRATCH / "safety" / "key.sqlite"
    if cache_k.exists():
        cache_k.unlink()
    seed_k = run_tare_inprocess(
        faa=g0,
        hmm=hmm,
        out_dir=SCRATCH / "safety" / "key_seed",
        cache=cache_k,
        contract_store=store2,
        label="safety_key_seed",
    )
    # Different argv: -E 10 instead of --cut_ga
    if (SCRATCH / "safety" / "key_e.sqlite").exists():
        (SCRATCH / "safety" / "key_e.sqlite").unlink()
    t0 = time.perf_counter()
    rec_e = ReferenceIncremental(
        argv=[
            HMMSCAN,
            "-E",
            "10",
            "--noali",
            "--cpu",
            CPU,
            "--tblout",
            "{output:tbl}",
            "--domtblout",
            "{output:domtbl}",
            "{reference}",
            "{input}",
        ],
        input_path=g0,
        out_dir=SCRATCH / "safety" / "key_e",
        reference=hmm,
        cache_path=SCRATCH / "safety" / "key_e.sqlite",
        verify="audit",
        pin="-Z {entry_count}",
        prep="hmmpress -f {reference}",
        contract_store=store2,
    ).run()
    wall_e = time.perf_counter() - t0
    status_e = (rec_e.extra or {}).get("contract_store")
    # Different Pfam release (update hmm)
    hmm_u = Path(manifest["pfam_update"]["path"])
    if (SCRATCH / "safety" / "key_rel.sqlite").exists():
        (SCRATCH / "safety" / "key_rel.sqlite").unlink()
    rec_rel = ReferenceIncremental(
        argv=hmmscan_argv(),
        input_path=g0,
        out_dir=SCRATCH / "safety" / "key_rel",
        reference=hmm_u,
        cache_path=SCRATCH / "safety" / "key_rel.sqlite",
        verify="audit",
        pin="-Z {entry_count}",
        prep="hmmpress -f {reference}",
        contract_store=store2,
    ).run()
    status_rel = (rec_rel.extra or {}).get("contract_store")
    out["key_isolation"] = {
        "seed_contract_store": seed_k.get("contract_store"),
        "argv_E10": {
            "contract_store": status_e,
            "decision": rec_e.decision,
            "wall_s": wall_e,
            "must_not_be_reused": status_e != "reused",
        },
        "different_release": {
            "contract_store": status_rel,
            "decision": rec_rel.decision,
            "must_not_be_reused": status_rel != "reused",
        },
        "pass": status_e != "reused" and status_rel != "reused",
    }

    # 3. Pin-check sharing evidence from pilot arm C
    pin_ok = []
    for g in pilot.get("genomes") or []:
        phases = g["arm_C"].get("phases") or {}
        pin_ok.append(
            {
                "accession": g["accession"],
                "pin_check_s": phases.get("pin_check_s"),
                "decision": g["arm_C"].get("decision"),
                "contract_store": g["arm_C"].get("contract_store"),
            }
        )
    out["pin_check_evidence"] = {
        "per_genome": pin_ok,
        "note": (
            "Code always re-runs pin check per genome (never publishes pin_checks). "
            "Evidence only: compare pin_check_s presence and SHIP across genomes."
        ),
        "argument_for_sharing": (
            "On W5x pin_check is 151.8 s; if conclusion is identical for the same "
            "(binary, argv, release) and only depends on help-derived pin template "
            "+ size members already confirmed, sharing would cut rho(20) toward 1.29."
        ),
        "argument_against_sharing": (
            "Pin check samples this genome's records and compares whole vs pinned "
            "body bytes; empty or sparse samples, different hit sets, or layout "
            "width can flip ok. Design table already marks pin_checks as "
            "cross-genome-unsafe without re-check."
        ),
    }
    return out


def project_rho(pilot: dict) -> dict:
    """PROJECTED rho(N) on W5x walls; laptop supplies confirm/probe ratio."""
    # W5x numbers from design doc
    T = 1013.7 / 4.20  # stock
    probe = 538.5
    pin = 151.8
    parse = 48.9
    total = 1013.7
    # Policy as built: share probe facts only (with confirm); re-pay pin every genome;
    # parse is MIXED — conservatively re-pay full parse_s each genome (as in design
    # conservative case that matches code: pin always re-run; parse not shared as
    # a skipped phase today).
    # Code: on reuse, skips full probe, runs confirm (reduced-n probe), always pin_check.
    S_optimistic = parse + probe + pin  # design headline (wrong for code)
    G_optimistic = total - S_optimistic
    S_code = probe  # only full probe skipped on reuse (confirm still paid)
    G_code = total - S_code  # includes pin+parse every time

    # confirmation tax ratio from laptop
    confirm_walls = []
    probe_walls = []
    for g in pilot.get("genomes") or []:
        c = g["arm_C"]
        b = g["arm_B"]
        cw = c.get("contract_confirm_wall_s")
        if cw is not None:
            try:
                confirm_walls.append(float(cw))
            except (TypeError, ValueError):
                pass
        pw = (b.get("probe_phases") or {})
        # probe wall from arm B (full first run)
        bphases = b.get("phases") or {}
        if "probe_wall_s" in bphases:
            probe_walls.append(float(bphases["probe_wall_s"]))
        elif b.get("probe_phases"):
            pp = b["probe_phases"]
            probe_walls.append(sum(float(pp.get(k, 0) or 0) for k in ("prep_s", "tool_s", "subref_build_s", "read_output_s")))

    if confirm_walls and probe_walls:
        ratio = (sum(confirm_walls) / len(confirm_walls)) / (sum(probe_walls) / len(probe_walls))
    else:
        ratio = CONFIRM_N_RATIO_FALLBACK  # CONFIRM_N / typical PROBE_N

    confirm_tax_w5x = probe * ratio  # scale full probe wall by laptop ratio

    def rho_code(n: int) -> float:
        # genome 1 pays S_code+G_code stuff: actually first genome pays full total
        # For N genomes with store: 1 full (total) + (N-1) * (G_code + confirm_tax)
        # where G_code = total - probe (still pays pin, parse, discovery, ...)
        # First genome: total; subsequent: (total - probe) + confirm_tax
        if n <= 0:
            return float("nan")
        batch = total + (n - 1) * ((total - probe) + confirm_tax_w5x)
        return (batch / n) / T

    def rho_optimistic_shared_pin(n: int) -> float:
        # headline design (incorrect for code): share parse+probe+pin once, no confirm tax
        return (G_optimistic + S_optimistic / n) / T

    def rho_conservative_no_confirm(n: int) -> float:
        # design conservative: S=probe only, no confirm tax
        return ((total - probe) + probe / n) / T

    ns = [1, 5, 20, 100]
    return {
        "assumptions": {
            "W5x_total_s": total,
            "W5x_ratio": 4.20,
            "W5x_stock_T_s": T,
            "W5x_probe_s": probe,
            "W5x_pin_check_s": pin,
            "W5x_parse_s": parse,
            "laptop_confirm_walls_s": confirm_walls,
            "laptop_probe_walls_s": probe_walls,
            "confirm_to_probe_ratio": ratio,
            "confirm_tax_projected_w5x_s": confirm_tax_w5x,
            "code_policy": (
                "On reuse: skip full probe, pay reduced-n confirm, always re-run "
                "pin_check; parse still runs; discovery/replay/IC2/audit per genome."
            ),
            "headline_rho20_1_29_assumes_shared_pin": True,
            "code_implements": "conservative re-pay pin every genome (+ confirm tax)",
        },
        "formula_code": (
            "batch(N)= total + (N-1)*((total-probe)+confirm_tax); "
            "rho(N)=(batch/N)/T; confirm_tax=probe*ratio_laptop"
        ),
        "rho_headline_shared_pin_no_confirm": {str(n): rho_optimistic_shared_pin(n) for n in ns},
        "rho_conservative_share_probe_only_no_confirm": {str(n): rho_conservative_no_confirm(n) for n in ns},
        "rho_code_as_built_with_confirm_tax": {str(n): rho_code(n) for n in ns},
    }


CONFIRM_N_RATIO_FALLBACK = 50 / 300


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    stage = (sys.argv[1] if len(sys.argv) > 1 else "all").lower()
    manifest_path = SCRATCH / "manifest.json"
    pilot_path = OUT / "pilot.json"

    if stage in {"prep", "all"}:
        print("== prepare_data ==")
        manifest = prepare_data()
        # calibrate one stock
        print("== calibrate stock ==")
        calib = calibrate_stock(
            Path(manifest["genomes"][0]["path"]),
            Path(manifest["pfam_subset"]["path"]),
        )
        manifest["calibration_stock"] = calib
        print(json.dumps({"calib_wall_s": calib["wall_s"], "n_models": N_MODELS, "n_proteins": N_PROTEINS}, indent=2))
        if calib["wall_s"] > 600:
            print("WARNING: stock >10 min; subset should already be 3000 models", file=sys.stderr)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        if stage == "prep":
            return 0
    else:
        manifest = json.loads(manifest_path.read_text())

    payload: dict = {
        "pilot": True,
        "not_a_result": True,
        "branch": "exp/shared-contract",
        "started_note": "laptop pilot P2",
    }
    if stage in {"gate_r", "all"}:
        print("== GATE R ==")
        payload["gate_r"] = gate_r(manifest)
        print("GATE_R", payload["gate_r"]["GATE_R"])
        (SCRATCH / "gate_r_result.json").write_text(json.dumps(payload["gate_r"], indent=2) + "\n")
        if payload["gate_r"]["GATE_R"] != "PASS":
            print("GATE R FAIL — stopping before pilot batch", file=sys.stderr)
            (OUT / "pilot_partial.json").write_text(json.dumps({**payload, "manifest": manifest}, indent=2) + "\n")
            return 1

    if stage in {"pilot", "all"}:
        print("== pilot batch ==")
        if "gate_r" not in payload and (SCRATCH / "gate_r_result.json").is_file():
            payload["gate_r"] = json.loads((SCRATCH / "gate_r_result.json").read_text())
        payload["pilot_batch"] = pilot_batch(manifest)
        (SCRATCH / "pilot_batch.json").write_text(json.dumps(payload["pilot_batch"], indent=2) + "\n")

    if stage in {"safety", "all"}:
        print("== safety ==")
        pilot = payload.get("pilot_batch") or json.loads((SCRATCH / "pilot_batch.json").read_text())
        payload["pilot_batch"] = pilot
        payload["safety"] = safety_checks(manifest, pilot)
        (SCRATCH / "safety_result.json").write_text(json.dumps(payload["safety"], indent=2) + "\n")

    if stage in {"project", "all"}:
        print("== project ==")
        pilot = payload.get("pilot_batch") or json.loads((SCRATCH / "pilot_batch.json").read_text())
        payload["projection"] = project_rho(pilot)

    payload["manifest"] = manifest if stage == "all" or "manifest" not in payload else manifest
    if stage == "all" or stage in {"project", "safety", "pilot"}:
        # merge pieces from scratch if needed
        if "gate_r" not in payload and (SCRATCH / "gate_r_result.json").is_file():
            payload["gate_r"] = json.loads((SCRATCH / "gate_r_result.json").read_text())
        if "pilot_batch" not in payload and (SCRATCH / "pilot_batch.json").is_file():
            payload["pilot_batch"] = json.loads((SCRATCH / "pilot_batch.json").read_text())
        if "safety" not in payload and (SCRATCH / "safety_result.json").is_file():
            payload["safety"] = json.loads((SCRATCH / "safety_result.json").read_text())
        if "projection" not in payload and payload.get("pilot_batch"):
            payload["projection"] = project_rho(payload["pilot_batch"])
        payload["manifest"] = manifest
        pilot_path.write_text(json.dumps(payload, indent=2) + "\n")
        print("wrote", pilot_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
