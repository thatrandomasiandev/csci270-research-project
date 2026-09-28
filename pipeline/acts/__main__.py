"""acts — strategy runner. First strategy: record memoization.

  python3 -m acts probe --kind fastq_pe --r1 A.fq.gz --r2 B.fq.gz
  python3 -m acts run --strategy record_memo --kind lines --input in.txt -- cat
  python3 -m acts run -- STAR …     # refuses identity (not byte-identical)
  python3 -m acts predict --kind lines --input in.txt -- cat
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from acts.overlap import overlap, unique_keys_fastq_pe, unique_keys_lines
from acts.records import probe_fastq_pe, probe_lines
from acts.strategies.record_memo import RecordMemo
from acts.suiteb import SUITEB, probe_all, probe_overlap, write_csv, write_overlap_csv


def cmd_probe(args: argparse.Namespace) -> int:
    if args.kind == "fastq_pe":
        if not args.r1 or not args.r2:
            print("fastq_pe needs --r1 and --r2", file=sys.stderr)
            return 2
        rep = probe_fastq_pe(Path(args.r1), Path(args.r2))
    elif args.kind == "lines":
        if not args.input:
            print("lines needs --input", file=sys.stderr)
            return 2
        rep = probe_lines(Path(args.input))
    else:
        print(f"unknown kind {args.kind}", file=sys.stderr)
        return 2
    payload = {
        "kind": rep.kind,
        "n": rep.n,
        "n_unique": rep.n_unique,
        "unique_frac": round(rep.unique_frac, 6),
        "max_speedup_if_pure": round(rep.max_speedup_if_pure, 4),
        "duplicates_rare": rep.duplicates_rare,
        **rep.extra,
    }
    print(json.dumps(payload, indent=2))
    return 0


def cmd_probe_suiteb(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else SUITEB
    if not root.is_dir():
        print(f"Suite B root missing: {root}", file=sys.stderr)
        return 2
    rows = probe_all(root)
    dest = Path(args.out) if args.out else Path("results") / "suiteB_dups.csv"
    write_csv(rows, dest)
    print(json.dumps(
        {
            "wrote": str(dest),
            "rows": [
                {
                    "id": inst,
                    "n": rep.n,
                    "n_unique": rep.n_unique,
                    "unique_frac": round(rep.unique_frac, 6),
                    "max_speedup_if_pure": round(rep.max_speedup_if_pure, 4),
                    "duplicates_rare": rep.duplicates_rare,
                }
                for inst, _r1, _r2, rep in rows
            ],
        },
        indent=2,
    ))
    return 0


def cmd_overlap(args: argparse.Namespace) -> int:
    if args.suiteb:
        root = Path(args.root) if args.root else SUITEB
        if not root.is_dir():
            print(f"Suite B root missing: {root}", file=sys.stderr)
            return 2
        rows = probe_overlap(root)
        dest = Path(args.out) if args.out else Path("results") / "suiteB_overlap.csv"
        write_overlap_csv(rows, dest)
        print(json.dumps(
            {
                "wrote": str(dest),
                "rows": [
                    {
                        "group": g,
                        "prev": a,
                        "new": b,
                        "n_shared": rep.n_shared,
                        "recall_in_new": round(rep.recall_in_new, 6),
                        "jaccard": round(rep.jaccard, 6),
                        "overlap_rare": rep.overlap_rare,
                    }
                    for g, a, b, rep in rows
                ],
            },
            indent=2,
        ))
        return 0
    if args.kind == "fastq_pe":
        prev = unique_keys_fastq_pe(Path(args.prev_r1), Path(args.prev_r2))
        new = unique_keys_fastq_pe(Path(args.new_r1), Path(args.new_r2))
    else:
        prev = unique_keys_lines(Path(args.prev))
        new = unique_keys_lines(Path(args.new))
    rep = overlap(prev, new)
    print(json.dumps(
        {
            "n_prev": rep.n_prev,
            "n_new": rep.n_new,
            "n_shared": rep.n_shared,
            "recall_in_new": round(rep.recall_in_new, 6),
            "jaccard": round(rep.jaccard, 6),
            "overlap_rare": rep.overlap_rare,
        },
        indent=2,
    ))
    return 0


def cmd_predict(args: argparse.Namespace) -> int:
    from acts.predict import PredictError, run_predict

    if not args.input:
        print("predict needs --input", file=sys.stderr)
        return 2
    tool = list(args.tool)
    if tool and tool[0] == "--":
        tool = tool[1:]
    if not tool:
        print("predict needs a tool after --", file=sys.stderr)
        return 2
    try:
        report = run_predict(
            kind=args.kind,
            input_path=Path(args.input),
            argv=tool,
            cache_path=Path(args.cache) if args.cache else None,
            seed=args.seed,
            runs=args.runs,
        )
    except PredictError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(report.as_dict(), indent=2))
    print(f"decision: {report.decision}")
    print(f"why:      {report.reason}")
    if report.predicted_speedup is not None:
        extra = (
            f"  predicted={report.predicted_speedup:.3f}× with P="
            f"{report.probe_cost_P:.3f}s"
        )
        ceil = (
            f"{report.ceiling_m:.3f}×" if report.ceiling_m is not None else "n/a"
        )
        print(f"ceiling:  {ceil} (P-free screen){extra}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    out = Path(args.out) if args.out else Path("acts_out") / args.strategy
    if args.strategy != "record_memo":
        print(f"unknown strategy {args.strategy}; more later", file=sys.stderr)
        return 2
    tool = list(args.tool)
    if tool and tool[0] == "--":
        tool = tool[1:]
    memo = RecordMemo(
        kind=args.kind,
        argv=tool,
        input_path=Path(args.input) if args.input else None,
        r1=Path(args.r1) if args.r1 else None,
        r2=Path(args.r2) if args.r2 else None,
        out_dir=out,
        cache_path=Path(args.cache) if args.cache else None,
        audit_p=args.audit_p,
        audit_seed=args.audit_seed,
        probe_n=args.probe_n,
        probe_seed=args.probe_seed,
        verify=args.verify,
    )
    rec = memo.run()
    print(f"strategy: {rec.strategy}")
    print(f"decision: {rec.decision}")
    print(f"why:      {rec.reason}")
    print(f"wrote {out / 'decision.txt'}")
    return 0 if rec.decision == "SHIP" else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="acts")
    sub = p.add_subparsers(dest="verb", required=True)

    pr = sub.add_parser("probe", help="count distinct records; no tool run")
    pr.add_argument("--kind", required=True, choices=("fastq_pe", "lines"))
    pr.add_argument("--input")
    pr.add_argument("--r1")
    pr.add_argument("--r2")
    pr.set_defaults(func=cmd_probe)

    rn = sub.add_parser("run", help="run a strategy; refuse when MATCH cannot hold")
    rn.add_argument("--strategy", default="record_memo")
    rn.add_argument("--kind", default="lines", choices=("fastq_pe", "lines", "vcf", "fasta"))
    rn.add_argument("--input")
    rn.add_argument("--r1")
    rn.add_argument("--r2")
    rn.add_argument("-o", "--out")
    rn.add_argument("--cache", help="persistent record cache (jsonl); default out_dir/cache.jsonl")
    rn.add_argument("--verify", choices=("audit", "full"), default="audit")
    rn.add_argument("--audit-p", type=float, default=None, dest="audit_p")
    rn.add_argument("--audit-seed", type=int, default=20260927, dest="audit_seed")
    rn.add_argument("--probe-n", type=int, default=500, dest="probe_n")
    rn.add_argument("--probe-seed", type=int, default=20260927, dest="probe_seed")
    rn.add_argument("tool", nargs=argparse.REMAINDER)
    rn.set_defaults(func=cmd_run)

    pd = sub.add_parser(
        "predict",
        help="time subsets, fit t=a+b·n, estimate m, screen-rule SHIP/REFUSE",
    )
    pd.add_argument("--kind", required=True, choices=("vcf", "fasta", "lines"))
    pd.add_argument("--input", required=True)
    pd.add_argument("--cache", help="existing record cache (jsonl); omit for first-run m")
    pd.add_argument("--seed", type=int, default=20260927)
    pd.add_argument("--runs", type=int, default=3, help="timed repeats per subset size")
    pd.add_argument("tool", nargs=argparse.REMAINDER)
    pd.set_defaults(func=cmd_predict)

    ov = sub.add_parser("overlap", help="cross-run record overlap (incremental kill test)")
    ov.add_argument("--suiteb", action="store_true")
    ov.add_argument("--root")
    ov.add_argument("-o", "--out")
    ov.add_argument("--kind", default="lines", choices=("fastq_pe", "lines"))
    ov.add_argument("--prev")
    ov.add_argument("--new")
    ov.add_argument("--prev-r1")
    ov.add_argument("--prev-r2")
    ov.add_argument("--new-r1")
    ov.add_argument("--new-r2")
    ov.set_defaults(func=cmd_overlap)

    ps = sub.add_parser("probe-suiteB", help="PE uniqueness on official Suite B FASTQs")
    ps.add_argument("--root", help="suiteB directory (default: star/bench/datasets/suiteB)")
    ps.add_argument("-o", "--out")
    ps.set_defaults(func=cmd_probe_suiteb)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
