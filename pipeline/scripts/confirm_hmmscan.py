#!/usr/bin/env python3
"""One real-hmmscan confirmation per coupling form.

TARE wraps this program with the hmmscan argv. The program presses the HMM
file it was given, runs HMMER 3.4 hmmscan, then applies the same coupling
rules as the synthetic shim to the printed tables. Affected records stay
outside TARE's probe sample. The 50-trial grid is the measurement. These
trials only check that the shipped check still fires on hmmscan's own tables.

The reference is the first 24 profiles of Pfam-A, copied out of the
read-only gzip. Sequences are emitted from the anchor profile (file index
22) with hmmemit --seed 20261113.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

_PIPELINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PIPELINE))
sys.path.insert(0, str(_PIPELINE / "scripts"))

import coupling_shim as shim  # noqa: E402

HMMER = os.environ.get("HMMER_BIN", "/opt/homebrew/bin/hmmscan")
HMMEMIT = os.environ.get("HMMEMIT_BIN", "/opt/homebrew/bin/hmmemit")
HMMPRESS = os.environ.get("HMMPRESS_BIN", "/opt/homebrew/bin/hmmpress")
PFAM = Path(
    os.environ.get(
        "TARE_PFAM",
        "/Users/joshuaterranova/Desktop/CSCI270/ACTS/pipeline/data/hmmer/Pfam-A.hmm.gz",
    )
)
N_MODELS = 24
N_RECORDS = 320
ANCHOR_INDEX = 22
PRESENCE_INDEX = 5
EMIT_SEED = 20261113


def _order(hmm_text: str) -> list[str]:
    names = []
    for line in hmm_text.splitlines():
        parts = line.split()
        if parts and parts[0] == "NAME" and len(parts) > 1:
            names.append(parts[1])
    return names


def _lengths(hmm_text: str) -> int:
    total = 0
    seen_name = False
    for line in hmm_text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "NAME":
            seen_name = True
        elif parts[0] == "LENG" and seen_name and len(parts) > 1:
            total += int(parts[1])
            seen_name = False
    return total


def extract_profiles(src: Path, n_models: int) -> tuple[str, list[str]]:
    """Copy the first ``n_models`` profiles. The gzip is not modified."""
    blocks: list[str] = []
    opener = gzip.open if str(src).endswith(".gz") else open
    with opener(src, "rt") as handle:
        buf: list[str] = []
        for line in handle:
            buf.append(line)
            if line.startswith("//"):
                blocks.append("".join(buf))
                buf = []
                if len(blocks) >= n_models:
                    break
    if len(blocks) < n_models:
        raise SystemExit(f"{src} yielded {len(blocks)} profiles, wanted {n_models}")
    text = "".join(blocks)
    names = _order(text)
    if len(names) != n_models:
        raise SystemExit(f"parsed {len(names)} names from {n_models} profiles")
    return text, names


def build(dest: Path, n_records: int = N_RECORDS, emit_seed: int = EMIT_SEED) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    text, names = extract_profiles(PFAM, N_MODELS)
    hmm = dest / "mini.hmm"
    hmm.write_text(text)
    anchor = names[ANCHOR_INDEX]
    anchor_block = text.split("//\n")[ANCHOR_INDEX] + "//\n"
    anchor_path = dest / "anchor.hmm"
    anchor_path.write_text(anchor_block)
    emitted = dest / "emitted.fa"
    proc = subprocess.run(
        [HMMEMIT, "--seed", str(emit_seed), "-N", str(n_records), "-o", str(emitted), str(anchor_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stderr[-400:] or proc.stdout[-400:])
    records = shim.parse_fasta(emitted.read_text())
    if len(records) != n_records:
        raise SystemExit(f"hmmemit wrote {len(records)} records, wanted {n_records}")
    lines = []
    for index, record in enumerate(records):
        lines.append(f">{shim.record_name(index)}")
        lines.append(record["sequence"])
    (dest / "queries.fa").write_text("\n".join(lines) + "\n")
    manifest = {
        "source": str(PFAM),
        "n_models": N_MODELS,
        "n_records": n_records,
        "anchor": anchor,
        "anchor_index": ANCHOR_INDEX,
        "presence_index": PRESENCE_INDEX,
        "presence_model": names[PRESENCE_INDEX],
        "names": names,
        "emit_seed": emit_seed,
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {hmm} anchor={anchor} and {n_records} queries")


def _positional(argv: list[str]) -> list[str]:
    skip = {"--tblout", "--domtblout", "-o", "--cpu", "-Z"}
    out: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token in skip:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        out.append(token)
        index += 1
    return out


def _paths(argv: list[str]) -> tuple[Path, Path]:
    tbl = dom = None
    for index, token in enumerate(argv):
        if token == "--tblout" and index + 1 < len(argv):
            tbl = Path(argv[index + 1])
        elif token == "--domtblout" and index + 1 < len(argv):
            dom = Path(argv[index + 1])
    if tbl is None or dom is None:
        raise SystemExit("confirm_hmmscan.py needs --tblout and --domtblout")
    return tbl, dom


def post_edit(tbl: str, dom: str, subset_text: str, full_order: list[str]) -> tuple[str, str]:
    """Apply one coupling to hmmscan tables.

    A trailing token keeps HMMER's fixed-width columns intact. The check
    compares whole lines, so the token is enough for a pad to see the change.
    """
    spec = shim.load_env()
    affected = (
        shim.affected_names(
            [{"name": shim.record_name(i), "sequence": ""} for i in range(spec["n_records"])],
            spec,
        )
        if spec["n_records"]
        else set()
    )
    present = set(_order(subset_text))
    total = _lengths(subset_text)
    digest = hashlib.sha256(subset_text.encode()).hexdigest()[:8]
    anchor_name = os.environ.get("TARE_ANCHOR") or (full_order[ANCHOR_INDEX] if len(full_order) > ANCHOR_INDEX else "A")
    if anchor_name not in full_order:
        raise SystemExit(f"anchor {anchor_name} is not in the reference")
    anchor = full_order.index(anchor_name)
    if spec["coupling"] == "order":
        real_responsible = full_order[anchor - spec["distance"]]
    elif spec["coupling"] == "presence":
        real_responsible = full_order[PRESENCE_INDEX]
    else:
        real_responsible = None

    def action(target: str, query: str) -> str:
        if query not in affected or spec["coupling"] == "none":
            return "keep"
        if spec["coupling"] == "residues":
            return f"L{total}"
        if spec["coupling"] == "global":
            return f"G{digest}"
        if spec["coupling"] == "presence":
            if target != anchor_name:
                return "keep"
            if real_responsible not in present:
                return "drop"
            return "keep"
        if spec["coupling"] == "order":
            if target != anchor_name:
                return "keep"
            if real_responsible not in present:
                return "FAR"
            return "keep"
        return "keep"

    def edit(text: str, target_col: int, query_col: int) -> str:
        kept: list[str] = []
        for line in text.splitlines(keepends=True):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                kept.append(line if line.endswith("\n") else line + "\n")
                continue
            cells = stripped.split()
            if max(target_col, query_col) >= len(cells):
                kept.append(line if line.endswith("\n") else line + "\n")
                continue
            decision = action(cells[target_col], cells[query_col])
            if decision == "drop":
                continue
            if decision == "keep":
                kept.append(line if line.endswith("\n") else line + "\n")
                continue
            body = line[:-1] if line.endswith("\n") else line
            kept.append(body + f" {decision}\n")
        return "".join(kept)

    return edit(tbl, 0, 2), edit(dom, 0, 3)


def _body(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip() and not line.startswith("#")]


def _hmmer_version() -> str:
    proc = subprocess.run([HMMER, "-h"], check=False, capture_output=True, text=True)
    for line in proc.stdout.splitlines():
        if line.startswith("# HMMER"):
            return line
    return proc.stdout.splitlines()[0] if proc.stdout else ""


def run_confirmations(
    dest: Path,
    *,
    forms: tuple | None = None,
    out_path: Path | None = None,
    emit_seed: int = EMIT_SEED,
    cpu: str = "1",
) -> None:
    """One TARE trial per form. Not part of the 50-trial rates."""
    from acts.reference_run import ReferenceIncremental
    import acts.reference_run as reference_run

    try:
        os.nice(10)
    except OSError:
        pass
    if not (dest / "mini.hmm").is_file() or not (dest / "manifest.json").is_file():
        build(dest, emit_seed=emit_seed)
    elif emit_seed != EMIT_SEED:
        manifest_seed = json.loads((dest / "manifest.json").read_text()).get("emit_seed")
        if manifest_seed != emit_seed:
            build(dest, emit_seed=emit_seed)
    manifest = json.loads((dest / "manifest.json").read_text())
    hmm = dest / "mini.hmm"
    fasta = dest / "queries.fa"
    n_records = int(manifest["n_records"])
    n_models = int(manifest["n_models"])
    script = Path(__file__).resolve()
    # One trial per form. C3 uses distance 2, the nearest distance on the
    # measured grid. Seeds are inside 20261113–20261117; each draw meets the
    # locked size-50 sample, so a single trial can see the random pad.
    if forms is None:
        forms = (
            ("C0", "none", 1, 0, 20261113),
            ("C1", "residues", 1, 20, 20261114),
            ("C2", "presence", 1, 20, 20261115),
            ("C3", "order", 2, 20, 20261116),
            ("C4", "global", 1, 20, 20261117),
        )
    rows = []
    for form, coupling, distance, k, seed in forms:
        os.environ.update(
            {
                "TARE_COUPLING": coupling,
                "TARE_K": str(k),
                "TARE_SEED": str(seed),
                "TARE_N": str(n_records),
                "TARE_M": str(n_models),
                "TARE_D": str(distance),
                "TARE_AFFECT": "",
                "TARE_ANCHOR": manifest["anchor"],
                "TARE_FULL_HMM": str(hmm),
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
            }
        )
        work = dest / f"trial_{form}_d{distance}"
        if work.exists():
            shutil.rmtree(work)
        work.mkdir()
        captured: list[dict] = []
        original = reference_run._batched_replay

        def wrapped(*args, **kwargs):
            texts, n_batches = original(*args, **kwargs)
            captured.append(texts)
            return texts, n_batches

        reference_run._batched_replay = wrapped
        try:
            result = ReferenceIncremental(
                argv=[
                    str(script),
                    "--cut_ga",
                    "--noali",
                    "--cpu",
                    cpu,
                    "--tblout",
                    "{output:tblout}",
                    "--domtblout",
                    "{output:domtblout}",
                    "-o",
                    "/dev/null",
                    str(hmm),
                    str(fasta),
                ],
                input_path=fasta,
                out_dir=work,
                reference=hmm,
                cache_path=work / "cache.sqlite",
                verify="audit",
                pin="-Z {entry_count}",
            ).run()
        finally:
            reference_run._batched_replay = original
        stock_tbl = work / "stock.tbl"
        stock_dom = work / "stock.dom"
        stock_proc = subprocess.run(
            [
                sys.executable,
                str(script),
                "--cut_ga",
                "--noali",
                "--cpu",
                cpu,
                "--tblout",
                str(stock_tbl),
                "--domtblout",
                str(stock_dom),
                "-o",
                "/dev/null",
                "-Z",
                str(n_models),
                str(hmm),
                str(fasta),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
        if stock_proc.returncode != 0:
            raise SystemExit(stock_proc.stderr[-500:] or "stock hmmscan failed")
        replay = captured[0] if captured else {}
        classes = {}
        differs = None
        if replay:
            for name, stock_path in (("tblout", stock_tbl), ("domtblout", stock_dom)):
                classes[name] = shim.diff_class(_body(stock_path.read_text()), _body(replay.get(name, "")))
            differs = any(kind != "identical" for kind in classes.values())
        labeled = shim.classify(result.decision, result.reason, bool(differs))
        plan = shim.trial_plan(
            n_records=n_records,
            n_models=n_models,
            k=k,
            seed=seed,
            coupling=coupling,
            distance=distance,
        )
        rows.append(
            {
                "form": form,
                "coupling": coupling,
                "distance": distance,
                "seed": seed,
                "k": k,
                "n_records": n_records,
                "n_models": n_models,
                "anchor": manifest["anchor"],
                "decision": result.decision,
                "reason": result.reason,
                "outcome": labeled["outcome"],
                "layer": labeled["layer"],
                "replay_differs": differs,
                "diff_class_by_table": classes,
                "stock_rows": len(_body(stock_tbl.read_text())),
                "affected_n": len(plan.affected),
                "replay_captured": bool(captured),
                "reused_rows": (result.extra or {}).get("reused_rows"),
                "audit": (result.extra or {}).get("audit"),
                "audit_checked": (result.extra or {}).get("audit_checked"),
            }
        )
        print(
            f"confirm {form} d={distance} {result.decision} {labeled['outcome']} "
            f"layer={labeled['layer']} class={classes.get('tblout')}",
            flush=True,
        )
        shutil.rmtree(work, ignore_errors=True)
    payload = {
        "system": "TARE",
        "kind": "hmmscan_confirmation",
        "not_part_of_detection_rates": True,
        "hmmer": _hmmer_version(),
        "python": platform.python_version(),
        "pfam": manifest,
        "pin": "-Z {entry_count}",
        "cpu": cpu,
        "trials": rows,
    }
    out = out_path or (_PIPELINE / "results" / "adversarial" / "confirm.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {out}")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "run":
        if len(args) != 2:
            raise SystemExit("usage: confirm_hmmscan.py run DIR")
        run_confirmations(Path(args[1]))
        return 0
    if args and args[0] == "build":
        if len(args) != 2:
            raise SystemExit("usage: confirm_hmmscan.py build DIR")
        build(Path(args[1]))
        return 0
    positional = _positional(args)
    if len(positional) != 2:
        raise SystemExit("usage: confirm_hmmscan.py [hmmscan flags] database queries")
    tbl, dom = _paths(args)
    press = subprocess.run(
        [HMMPRESS, "-f", positional[0]],
        check=False,
        capture_output=True,
        text=True,
    )
    if press.returncode != 0:
        sys.stderr.write((press.stderr or press.stdout or "hmmpress failed")[-500:])
        return press.returncode or 1
    proc = subprocess.run([HMMER, *args], check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write((proc.stderr or proc.stdout or "hmmscan failed")[-500:])
        return proc.returncode
    full_path = os.environ.get("TARE_FULL_HMM")
    full_order = _order(Path(full_path).read_text()) if full_path else _order(Path(positional[0]).read_text())
    subset_text = Path(positional[0]).read_text()
    edited_tbl, edited_dom = post_edit(tbl.read_text(), dom.read_text(), subset_text, full_order)
    tbl.write_text(edited_tbl)
    dom.write_text(edited_dom)
    return 0


if __name__ == "__main__":
    sys.exit(main())
