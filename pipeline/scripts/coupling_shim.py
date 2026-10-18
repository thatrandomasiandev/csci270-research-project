#!/usr/bin/env python3
"""Synthetic hmmscan that injects one reference-coupling at a time.

TARE invokes this program with the same argv shape it uses for hmmscan.
``-Z`` is inserted by the pin. The coupling mode and the affected-record
draw travel in the environment, so the argv does not change.

Hits are entry-local except for the injected coupling. One model, chosen
by the trial seed, is a hit for every record. Its bit score is a hash of
the record and model names and does not depend on which other models are
in the file. The printed E-value is ``p * Z`` with ``p = 1e-3``. ``Z`` is
the ``-Z`` value when TARE passes one, otherwise the number of models in
the file. ``--cut_ga`` keeps a hit only when its score is at least the
model's GA.

Couplings (``TARE_COUPLING``):

- ``none``: no extra dependence.
- ``residues``: on affected records, the bias column is the sum of model
  lengths in the file actually searched.
- ``presence``: an affected record's hit is omitted unless a designated
  other model is in that file.
- ``order``: an affected record's note names the model ``TARE_D`` positions
  earlier in the full reference, or ``via-missing`` when that model was
  left out.
- ``global``: on affected records, the note is a hash of the raw text of
  every model in the file actually searched.

Affected records are drawn from the records that are not in TARE's probe
sample. The constants below match ``acts.reference_fit``. Contract
inference and the in-situ check therefore see an entry-local scorer.
"""

from __future__ import annotations

import hashlib
import os
import random
import sys
from collections import Counter
from pathlib import Path

VERSION = "coupling-shim-1"

# Duplicated from acts.reference_fit so a subprocess need not import acts.
# tests/test_coupling_shim.py asserts the two copies match.
PROBE_N = 300
PROBE_SEED = 20261006

P_HIT = 1e-3
DEFAULT_GA = 20.0
E_REPORT = 10.0

COUPLINGS = ("none", "residues", "presence", "order", "global")


def sample_record_indices(n: int, k: int, seed: int) -> list[int]:
    """Second Random(seed) draw, file order kept. Matches acts.reference_fit."""
    if k >= n:
        return list(range(n))
    rng = random.Random(seed)
    picked = set(rng.sample(range(n), k))
    return [i for i in range(n) if i in picked]


def probe_indices(n_records: int) -> set[int]:
    width = min(PROBE_N, n_records)
    return set(sample_record_indices(n_records, width, PROBE_SEED))


def model_length(index: int) -> int:
    """Unequal lengths so an entry-count factor is not a length factor.

    Every 50th model is long. An equal-count split then does not reproduce
    the E-value column under the total-length hypothesis.
    """
    if index % 50 == 0:
        return 100_000
    return 1 + (index % 7)


def model_name(index: int) -> str:
    return f"m{index:04d}"


def record_name(index: int) -> str:
    return f"q{index:04d}"


class TrialPlan:
    def __init__(
        self,
        *,
        affected: list[int],
        hit_index: int,
        responsible: int | None,
        n_records: int,
        n_models: int,
    ) -> None:
        self.affected = list(affected)
        self.hit_index = hit_index
        self.responsible = responsible
        self.n_records = n_records
        self.n_models = n_models

    @property
    def hit_name(self) -> str:
        return model_name(self.hit_index)

    @property
    def responsible_name(self) -> str | None:
        if self.responsible is None:
            return None
        return model_name(self.responsible)


def trial_plan(
    *,
    n_records: int,
    n_models: int,
    k: int,
    seed: int,
    coupling: str,
    distance: int,
) -> TrialPlan:
    """Draw affected records and the hit model from ``seed``.

    Affected indices lie outside the probe sample. ``k`` above that
    complement raises; it is not silently truncated.
    """
    if coupling not in COUPLINGS:
        raise ValueError(f"unknown coupling {coupling!r}")
    if n_models < 24:
        raise ValueError("need at least 24 models so a distance-20 predecessor exists")
    if k < 0:
        raise ValueError("k must be non-negative")
    probe = probe_indices(n_records)
    eligible = [i for i in range(n_records) if i not in probe]
    if k > len(eligible):
        raise ValueError(f"k={k} exceeds the non-probe complement ({len(eligible)})")
    rng = random.Random(seed)
    affected = rng.sample(eligible, k) if k else []
    hit_index = rng.randrange(21, n_models - 1)
    responsible: int | None
    if coupling == "presence":
        banned = {hit_index - 1, hit_index, hit_index + 1}
        choices = [i for i in range(n_models) if i not in banned]
        responsible = rng.choice(choices)
    elif coupling == "order":
        if distance < 1:
            raise ValueError("order coupling needs distance >= 1")
        responsible = hit_index - distance
        if responsible < 0:
            raise ValueError("distance runs off the start of the reference")
    else:
        responsible = None
    return TrialPlan(
        affected=affected,
        hit_index=hit_index,
        responsible=responsible,
        n_records=n_records,
        n_models=n_models,
    )


def write_reference(path: Path, n_models: int) -> None:
    parts: list[str] = []
    for index in range(n_models):
        parts.append(
            "HMMER3/f\n"
            f"NAME  {model_name(index)}\n"
            f"LENG  {model_length(index)}\n"
            "GA    20.00 20.00;\n"
            "//\n"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(parts))


def write_queries(path: Path, n_records: int, *, length: int = 40) -> None:
    residue = "ACDEFGHIKLMNPQRSTVWY"
    body = (residue * ((length // len(residue)) + 1))[:length]
    lines = []
    for index in range(n_records):
        lines.append(f">{record_name(index)}")
        lines.append(body)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def parse_hmm(text: str) -> list[dict]:
    models: list[dict] = []
    raw: list[str] = []
    name: str | None = None
    length: int | None = None
    ga = DEFAULT_GA
    for line in text.splitlines(keepends=True):
        raw.append(line)
        parts = line.split()
        if parts and parts[0] == "NAME" and len(parts) > 1:
            name = parts[1]
        elif parts and parts[0] == "LENG" and length is None and len(parts) > 1:
            length = int(parts[1])
        elif parts and parts[0] == "GA" and len(parts) > 1:
            ga = float(parts[1])
        elif line.startswith("//"):
            if name is None or length is None:
                raise SystemExit("HMM entry is missing NAME or LENG")
            models.append({"name": name, "length": length, "ga": ga, "raw": "".join(raw)})
            raw = []
            name = None
            length = None
            ga = DEFAULT_GA
    if raw and "".join(raw).strip():
        raise SystemExit("truncated HMM entry")
    if not models:
        raise SystemExit("HMM file contained no entries")
    return models


def parse_fasta(text: str) -> list[dict]:
    records: list[dict] = []
    name: str | None = None
    chunks: list[str] = []
    for line in text.splitlines():
        if line.startswith(">"):
            if name is not None:
                records.append({"name": name, "sequence": "".join(chunks)})
            header = line[1:].strip().split(None, 1)
            name = header[0] if header else ""
            chunks = []
            continue
        chunks.append(line.strip())
    if name is not None:
        records.append({"name": name, "sequence": "".join(chunks)})
    if not records:
        raise SystemExit("FASTA contained no records")
    return records


def bit_score(record: str, model: str) -> float:
    """Hash score in ``[21, 40]``. It does not read the rest of the reference."""
    digest = hashlib.sha256(f"{record}\t{model}".encode()).digest()
    unit = int.from_bytes(digest[:2], "big") / 65535
    return 21.0 + 19.0 * unit


def content_hash(models: list[dict]) -> str:
    blob = "".join(model["raw"] for model in models).encode()
    return hashlib.sha256(blob).hexdigest()[:8]


def passes_report(*, score: float, ga: float, evalue: float, cut_ga: bool) -> bool:
    """``--cut_ga`` thresholds the bit score. Otherwise the default is E <= 10."""
    if cut_ga:
        return score >= ga
    return evalue <= E_REPORT


def format_e(value: float) -> str:
    return f"{value:.6e}"


def load_env(environ: dict[str, str] | None = None) -> dict:
    env = os.environ if environ is None else environ
    coupling = env.get("TARE_COUPLING", "none")
    if coupling not in COUPLINGS:
        raise SystemExit(f"TARE_COUPLING must be one of {COUPLINGS}")
    return {
        "coupling": coupling,
        "k": int(env.get("TARE_K", "0")),
        "seed": int(env.get("TARE_SEED", "0")),
        "n_records": int(env.get("TARE_N", "0")),
        "n_models": int(env.get("TARE_M", "0")),
        "distance": int(env.get("TARE_D", "1")),
        "affect": env.get("TARE_AFFECT", ""),
    }


def affected_names(queries: list[dict], spec: dict) -> set[str]:
    if spec["affect"] == "all":
        return {query["name"] for query in queries}
    if spec["n_records"] <= 0 or spec["n_models"] <= 0:
        return set()
    plan = trial_plan(
        n_records=spec["n_records"],
        n_models=spec["n_models"],
        k=spec["k"],
        seed=spec["seed"],
        coupling=spec["coupling"],
        distance=spec["distance"],
    )
    return {record_name(index) for index in plan.affected}


def score_models(
    models: list[dict],
    queries: list[dict],
    *,
    z_override: int | None,
    cut_ga: bool,
    spec: dict | None = None,
) -> dict[str, str]:
    """Return tblout and domtblout text for this searched subset."""
    spec = load_env() if spec is None else spec
    coupling = spec["coupling"]
    plan = None
    if spec["n_records"] > 0 and spec["n_models"] > 0:
        plan = trial_plan(
            n_records=spec["n_records"],
            n_models=spec["n_models"],
            k=spec["k"],
            seed=spec["seed"],
            coupling=coupling,
            distance=spec["distance"],
        )
    by_name = {model["name"]: model for model in models}
    present = set(by_name)
    total_length = sum(model["length"] for model in models)
    z = len(models) if z_override is None else z_override
    evalue = P_HIT * z
    digest = content_hash(models)
    if spec.get("affect") == "all":
        affected = {query["name"] for query in queries}
    elif plan is not None:
        affected = {record_name(index) for index in plan.affected}
    else:
        affected = set()
    hit_name = plan.hit_name if plan is not None else None
    responsible = plan.responsible_name if plan is not None else None

    tbl_rows: list[str] = []
    dom_rows: list[str] = []
    for query in queries:
        if hit_name is None or hit_name not in by_name:
            continue
        model = by_name[hit_name]
        score = bit_score(query["name"], hit_name)
        if not passes_report(score=score, ga=float(model["ga"]), evalue=evalue, cut_ga=cut_ga):
            continue
        is_affected = query["name"] in affected
        if coupling == "presence" and is_affected and responsible not in present:
            continue
        bias = "0.50"
        note = "synthetic"
        if is_affected and coupling == "residues":
            bias = str(total_length)
        elif is_affected and coupling == "order":
            note = f"via-{responsible}" if responsible in present else "via-missing"
        elif is_affected and coupling == "global":
            note = f"g{digest}"
        e_text = format_e(evalue)
        score_text = f"{score:.2f}"
        tbl_rows.append(f"{hit_name} {query['name']} {e_text} {score_text} {bias} {note}")
        c_e = format_e(P_HIT)
        dom_rows.append(f"{hit_name} {query['name']} {e_text} {score_text} {bias} {c_e} {note}")

    tbl = (
        f"# coupling-shim {VERSION} tblout Z={z} cut_ga={int(cut_ga)}\n"
        "# target_name query_name evalue score bias note\n"
        + "".join(f"{row}\n" for row in tbl_rows)
    )
    dom = (
        f"# coupling-shim {VERSION} domtblout Z={z} cut_ga={int(cut_ga)}\n"
        "# target_name query_name i_evalue score bias c_evalue note\n"
        + "".join(f"{row}\n" for row in dom_rows)
    )
    return {"tblout": tbl, "domtblout": dom}


def diff_class(stock_lines: list[str], replay_lines: list[str]) -> str:
    """identical / order / value-only / missing / extra / missing_and_extra."""
    if stock_lines == replay_lines:
        return "identical"
    if sorted(stock_lines) == sorted(replay_lines):
        return "order"

    def pairs(lines: list[str]) -> list[tuple[str, str]]:
        out = []
        for line in lines:
            cells = line.split()
            if len(cells) < 2:
                out.append(("", line))
            else:
                out.append((cells[1], cells[0]))
        return out

    stock_pairs = Counter(pairs(stock_lines))
    replay_pairs = Counter(pairs(replay_lines))
    if stock_pairs == replay_pairs:
        return "value-only"
    missing = stock_pairs - replay_pairs
    extra = replay_pairs - stock_pairs
    if missing and extra:
        return "missing_and_extra"
    if missing:
        return "missing"
    if extra:
        return "extra"
    return "different_row"


def layer_of(decision: str, reason: str) -> str | None:
    """Which shipped layer produced this decision. ``None`` when nothing fired."""
    text = reason.lower()
    if decision == "SHIP":
        return None
    if "non-candidate" in text:
        return "r4"
    if "ic2 neighbor" in text:
        return "neighbor_pad"
    if "ic2 random" in text:
        return "random_pad"
    if decision == "REFUSE_AUDIT" or "audited records differ" in text:
        return "audit"
    if decision == "REFUSE_PIN" and (
        "pin check failed" in text or "identity check failed" in text or "differs from the whole" in text
    ):
        return "in_situ_r3"
    if decision == "REFUSE_PIN":
        return "r2_pin"
    if decision == "REFUSE":
        return "contract"
    return "other"


def classify(decision: str, reason: str, replay_differs: bool) -> dict:
    """true refusal, needless refusal, correct ship, or UNSAFE.

    UNSAFE means the replay body differed from stock and every check passed.
    A contract or pin refusal is recorded separately: the safety check did not run.
    """
    layer = layer_of(decision, reason)
    if decision == "SHIP" and not replay_differs:
        outcome = "correct_ship"
    elif decision == "SHIP" and replay_differs:
        outcome = "UNSAFE"
    elif str(decision).startswith("REFUSE") and replay_differs and layer in {"contract", "r2_pin"}:
        outcome = "contract_refuse"
    elif str(decision).startswith("REFUSE") and replay_differs:
        outcome = "true_refusal"
    elif str(decision).startswith("REFUSE") and not replay_differs:
        outcome = "needless_refusal"
    else:
        outcome = "other"
    return {"outcome": outcome, "layer": layer, "decision": decision}


def parse_argv(argv: list[str]) -> tuple[dict, list[str]]:
    """hmmscan-shaped argv. Returns options and the two positionals."""
    opts = {"cut_ga": False, "z": None, "tblout": None, "domtblout": None, "cpu": "1"}
    positionals: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--cut_ga":
            opts["cut_ga"] = True
        elif token in {"--noali", "--notextw"}:
            pass
        elif token == "--cpu" and index + 1 < len(argv):
            index += 1
            opts["cpu"] = argv[index]
        elif token == "-Z" and index + 1 < len(argv):
            index += 1
            opts["z"] = int(argv[index])
        elif token == "--tblout" and index + 1 < len(argv):
            index += 1
            opts["tblout"] = argv[index]
        elif token == "--domtblout" and index + 1 < len(argv):
            index += 1
            opts["domtblout"] = argv[index]
        elif token == "-o" and index + 1 < len(argv):
            index += 1
        elif token.startswith("-"):
            raise SystemExit(f"unrecognized argument {token}")
        else:
            positionals.append(token)
        index += 1
    if len(positionals) != 2:
        raise SystemExit("usage: coupling_shim.py [options] hmmfile seqfile")
    return opts, positionals


def main(argv: list[str] | None = None) -> int:
    opts, positionals = parse_argv(sys.argv[1:] if argv is None else argv)
    models = parse_hmm(Path(positionals[0]).read_text())
    queries = parse_fasta(Path(positionals[1]).read_text())
    tables = score_models(models, queries, z_override=opts["z"], cut_ga=opts["cut_ga"])
    if not opts["tblout"] or not opts["domtblout"]:
        raise SystemExit("both --tblout and --domtblout are required")
    Path(opts["tblout"]).write_text(tables["tblout"])
    Path(opts["domtblout"]).write_text(tables["domtblout"])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
