"""Predict whether record memoization can pay on a tool + input.

Engineering wrapper around the locked screen rule in
``docs/TOOL_SCREEN.md`` (erratum) / ``docs/HEADLINE_SCREEN.md``.
Not a new method. Probe cost *P* is a stub until Agent A's batched
subset-invariance formula is merged; this module does not invent it.
"""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from acts.cache import fingerprint_inputs, namespace
from acts.fasta import FastaRec, read_fasta, write_fasta
from acts.records import iter_lines
from acts.sample import sample_records
from acts.vcf import body_lines, is_header, read_maybe_gz
from acts.vcf_fields import KEY_FIELDS, cache_key as vcf_cache_key

SEED = 20260927
RUNS = 3
CEILING_MIN = 3.0
SAVED_MIN_S = 60.0
M_GATE = 1.0 / 3.0
SCREEN_LADDER = (1, 50, 200, 800, 1000, 5000, 20000)
PROBE_COST_NOTE = (
    "stub: probe cost P is not computed here. Agent A's batched "
    "subset-invariance formula is not in this tree. Do not treat "
    "ceiling(m) as P-adjusted speedup. Wire the real P after merge."
)

_NOOP_CODE = (
    "import sys, pathlib\n"
    "p = pathlib.Path(sys.argv[-1]) if len(sys.argv) > 1 else None\n"
    "if p is not None and p.is_file():\n"
    "    p.read_bytes()\n"
    "else:\n"
    "    sys.stdin.buffer.read()\n"
)


class PredictError(Exception):
    """User-facing failure (bad argv, tool crash, empty input)."""


def subset_sizes(n: int) -> list[int]:
    """Screen ladder, omitting sizes above *n*; always include *n*.

    Tiny *N* (fixtures) get a midpoint so OLS has at least two points
    besides the endpoints when *n* >= 3.
    """
    if n <= 0:
        return []
    if n == 1:
        return [1]
    sizes = [s for s in SCREEN_LADDER if s < n]
    if n not in sizes:
        sizes.append(n)
    sizes = sorted({s for s in sizes if 1 <= s <= n})
    if 1 not in sizes:
        sizes = [1, *sizes]
    if len(sizes) < 3 and n >= 3:
        mid = max(2, n // 2)
        sizes = sorted(set(sizes) | {mid})
    return sizes


def fit_ab(ns: list[int], ts: list[float]) -> tuple[float, float]:
    """OLS of t = a + b·n on per-size mean walls. Same estimator as the screen."""
    if not ns or not ts or len(ns) != len(ts):
        return 0.0, 0.0
    n_bar = statistics.fmean(ns)
    t_bar = statistics.fmean(ts)
    var_n = sum((n - n_bar) ** 2 for n in ns)
    if var_n == 0:
        return t_bar, 0.0
    cov = sum((n - n_bar) * (t - t_bar) for n, t in zip(ns, ts))
    b = cov / var_n
    return t_bar - b * n_bar, b


def ceiling(a: float, b: float, n: int, m: float, w: float) -> float | None:
    den = a + b * m * n + w
    if den <= 0:
        return None
    return (a + b * n) / den


def saved_s(a: float, b: float, n: int, m: float, w: float) -> float:
    return (a + b * n) - (a + b * m * n + w)


def recommend(
    a: float,
    b: float,
    n: int,
    m: float,
    w: float,
) -> tuple[str, str]:
    """SHIP/REFUSE from the corrected screen rule.

    Advance only if ceiling(m) ≥ 3 and absolute time saved ≥ 60 s.
    If a → 0 the ratio cannot beat 1/m, so m must be < 1/3.
    """
    if n <= 0:
        return "REFUSE", "N=0; nothing to time"
    if m >= M_GATE:
        return (
            "REFUSE",
            f"m={m:.4f} ≥ 1/3; ceiling cannot reach {CEILING_MIN:g} even as a,w → 0",
        )
    if a <= 0 or b <= 0:
        return "REFUSE", "linear model failed (need a>0 and b>0)"
    ratio = ceiling(a, b, n, m, w)
    saved = saved_s(a, b, n, m, w)
    if ratio is None:
        return "REFUSE", "denominator ≤ 0"
    if ratio < CEILING_MIN:
        return "REFUSE", f"ceiling(m)={ratio:.3f} < {CEILING_MIN:g}"
    if saved < SAVED_MIN_S:
        return "REFUSE", f"saved={saved:.3f}s < {SAVED_MIN_S:g}s"
    return (
        "SHIP",
        f"ceiling(m)={ratio:.3f} ≥ {CEILING_MIN:g} and saved={saved:.1f}s ≥ {SAVED_MIN_S:g}s",
    )


def record_keys(kind: str, path: Path) -> list[str]:
    if kind == "lines":
        return list(iter_lines(path))
    if kind == "vcf":
        text = read_maybe_gz(path)
        return [vcf_cache_key(ln, KEY_FIELDS) for ln in body_lines(text)]
    if kind == "fasta":
        return [rec.key for rec in read_fasta(path)]
    raise PredictError(f"unknown kind {kind!r}")


def load_cache_keys(path: Path, argv: list[str], kind: str) -> set[str]:
    """Keys in *path* for this argv/kind namespace. Does not write cache sidecars."""
    if not path.is_file():
        return set()
    ns = namespace(argv, kind, fingerprint_inputs(argv))
    out: set[str] = set()
    for line in path.read_text().splitlines():
        if not line:
            continue
        row = json.loads(line)
        if row.get("ns") == ns and "record" in row:
            out.add(row["record"])
    return out


def miss_fraction(
    keys: list[str],
    cached: set[str] | None,
) -> tuple[float, dict]:
    """Fraction of distinct keys that would still be sent to the tool.

    No cache / empty cache: first-run within-file unique_frac.
    Non-empty cache: unique keys absent from the cache, over N.
    """
    n = len(keys)
    n_unique = len(set(keys))
    if n == 0:
        return 1.0, {
            "mode": "empty_input",
            "n": 0,
            "n_unique": 0,
            "n_miss_unique": 0,
            "unique_frac": 1.0,
        }
    if not cached:
        m = n_unique / n
        return m, {
            "mode": "first_run",
            "n": n,
            "n_unique": n_unique,
            "n_miss_unique": n_unique,
            "unique_frac": m,
        }
    unseen = {k for k in keys if k not in cached}
    m = len(unseen) / n
    return m, {
        "mode": "incremental",
        "n": n,
        "n_unique": n_unique,
        "n_miss_unique": len(unseen),
        "unique_frac": n_unique / n,
        "cache_keys": len(cached),
    }


def substitute_argv(argv: list[str], input_path: Path) -> list[str]:
    replaced = [a.replace("{input}", str(input_path)) for a in argv]
    if any("{input}" in a for a in argv):
        return replaced
    return replaced + [str(input_path)]


def invoke_argv(kind: str, argv: list[str], input_path: Path) -> tuple[list[str], bool]:
    """Return (cmd, use_stdin). lines tools read stdin; vcf/fasta take a path."""
    if any("{input}" in a for a in argv):
        return substitute_argv(argv, input_path), False
    if kind in {"vcf", "fasta"}:
        return substitute_argv(argv, input_path), False
    return list(argv), True


def time_tool(kind: str, argv: list[str], input_path: Path) -> float:
    cmd, use_stdin = invoke_argv(kind, argv, input_path)
    t0 = time.perf_counter()
    if use_stdin:
        with input_path.open("rb") as inf:
            proc = subprocess.run(
                cmd,
                stdin=inf,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=False,
            )
    else:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
    wall = time.perf_counter() - t0
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", "replace")[-800:]
        raise PredictError(f"tool failed (rc={proc.returncode}): {err}")
    return wall


@dataclass
class InputBundle:
    kind: str
    path: Path
    n: int
    keys: list[str]
    header: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    fasta: list[FastaRec] = field(default_factory=list)


def load_input(kind: str, path: Path) -> InputBundle:
    if not path.is_file():
        raise PredictError(f"input missing: {path}")
    keys = record_keys(kind, path)
    if kind == "lines":
        lines = list(iter_lines(path))
        return InputBundle(kind, path, len(lines), keys, lines=lines)
    if kind == "vcf":
        text = read_maybe_gz(path)
        header = [ln for ln in text.splitlines() if is_header(ln)]
        body = body_lines(text)
        return InputBundle(kind, path, len(body), keys, header=header, lines=body)
    recs = read_fasta(path)
    return InputBundle(kind, path, len(recs), keys, fasta=recs)


def write_subset(bundle: InputBundle, n: int, dest: Path, *, seed: int) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if bundle.kind == "fasta":
        picked = sample_records(bundle.fasta, n, seed=seed)
        write_fasta(dest, picked)
        return dest
    if bundle.kind == "vcf":
        picked = sample_records(bundle.lines, n, seed=seed)
        dest.write_text("\n".join(bundle.header + picked) + "\n")
        return dest
    picked = sample_records(bundle.lines, n, seed=seed)
    dest.write_text("\n".join(picked) + ("\n" if picked else ""))
    return dest


def measure_sizes(
    bundle: InputBundle,
    argv: list[str],
    work: Path,
    *,
    seed: int,
    runs: int,
) -> tuple[list[int], list[float], list[dict]]:
    sizes = subset_sizes(bundle.n)
    means: list[float] = []
    rows: list[dict] = []
    for n in sizes:
        subset = write_subset(bundle, n, work / f"n{n}{bundle.path.suffix or '.txt'}", seed=seed + n)
        walls: list[float] = []
        for i in range(runs):
            wall = time_tool(bundle.kind, argv, subset)
            walls.append(wall)
            rows.append({"n": n, "run": i + 1, "wall_s": wall})
        means.append(statistics.fmean(walls))
    return sizes, means, rows


def measure_w(kind: str, input_path: Path, *, runs: int) -> float:
    """Wrapper + input I/O with the tool replaced by a no-op.  Mean of *runs*."""
    noop = [sys.executable, "-c", _NOOP_CODE]
    walls = [time_tool(kind, noop, input_path) for _ in range(runs)]
    return statistics.fmean(walls)


@dataclass
class PredictReport:
    kind: str
    input: str
    n: int
    sizes: list[int]
    seed: int
    runs: int
    a_s: float
    b_s_per_record: float
    w_s: float
    m: float
    m_detail: dict
    stock_s: float
    cached_s: float
    ceiling_m: float | None
    saved_s: float
    decision: str
    reason: str
    predicted_speedup: float | None
    predicted_speedup_includes_P: bool
    probe_cost_P: None
    probe_cost_note: str
    timed_runs: list[dict]

    def as_dict(self) -> dict:
        return asdict(self)


def run_predict(
    *,
    kind: str,
    input_path: Path,
    argv: list[str],
    cache_path: Path | None = None,
    seed: int = SEED,
    runs: int = RUNS,
    work: Path | None = None,
) -> PredictReport:
    if kind not in {"vcf", "fasta", "lines"}:
        raise PredictError(f"unknown kind {kind!r}")
    if not argv:
        raise PredictError("predict needs a tool after --")
    if runs < 1:
        raise PredictError("--runs must be ≥ 1")

    bundle = load_input(kind, input_path)
    cached: set[str] | None = None
    if cache_path is not None:
        cached = load_cache_keys(cache_path, argv, kind)
    m, m_detail = miss_fraction(bundle.keys, cached)

    own_tmp = None
    if work is None:
        own_tmp = tempfile.TemporaryDirectory(prefix="acts_predict_")
        work = Path(own_tmp.name)
    try:
        sizes, means, timed = measure_sizes(bundle, argv, work, seed=seed, runs=runs)
        a, b = fit_ab(sizes, means)
        w = measure_w(kind, bundle.path, runs=runs)
    finally:
        if own_tmp is not None:
            own_tmp.cleanup()

    n = bundle.n
    stock = a + b * n
    cached_wall = a + b * m * n + w
    ratio = ceiling(a, b, n, m, w)
    saved = saved_s(a, b, n, m, w)
    decision, reason = recommend(a, b, n, m, w)
    return PredictReport(
        kind=kind,
        input=str(input_path),
        n=n,
        sizes=sizes,
        seed=seed,
        runs=runs,
        a_s=a,
        b_s_per_record=b,
        w_s=w,
        m=m,
        m_detail=m_detail,
        stock_s=stock,
        cached_s=cached_wall,
        ceiling_m=ratio,
        saved_s=saved,
        decision=decision,
        reason=reason,
        predicted_speedup=ratio,
        predicted_speedup_includes_P=False,
        probe_cost_P=None,
        probe_cost_note=PROBE_COST_NOTE,
        timed_runs=timed,
    )
