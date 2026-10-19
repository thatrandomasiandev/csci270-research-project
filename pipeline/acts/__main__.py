"""acts — strategy runner.

  python3 -m acts probe --kind fastq_pe --r1 A.fq.gz --r2 B.fq.gz
  python3 -m acts run --strategy record_memo --kind lines --input in.txt -- cat
  python3 -m acts run --kind files --input in_dir -- python3 tool.py
  python3 -m acts run --kind linetable --input in.smi -- python3 tool.py
  python3 -m acts run --strategy reference --input records.faa --reference db --prep 'prep {reference}' -- tool {reference} {input} {output}
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
    tool = list(args.tool)
    if tool and tool[0] == "--":
        tool = tool[1:]
    if args.strategy == "reference":
        from acts.reference_run import ReferenceIncremental, RunError

        if not args.input:
            print("reference needs --input", file=sys.stderr)
            return 2
        if not tool:
            print("reference needs a tool after --", file=sys.stderr)
            return 2
        try:
            memo = ReferenceIncremental(
                argv=tool,
                input_path=Path(args.input),
                out_dir=out,
                reference=Path(args.reference) if args.reference else None,
                prep=args.prep,
                baseline=args.baseline,
                cache_path=Path(args.cache) if args.cache else None,
                verify=args.verify,
                audit_p=args.audit_p,
                audit_seed=args.audit_seed,
                audit_bound=args.audit_bound,
                audit_epsilon=args.audit_epsilon,
                audit_k_fraction=args.audit_k_fraction,
                audit_size=args.audit_size,
                first_use_k=args.first_use,
                pin=args.pin,
                slack=args.slack,
                subset_aux=args.subset_aux,
                invalidate_group=args.invalidate_group,
            )
        except RunError as exc:
            print(exc.reason, file=sys.stderr)
            return 2
        rec = memo.run()
        print(f"strategy: {rec.strategy}")
        print(f"decision: {rec.decision}")
        print(f"why:      {rec.reason}")
        print(f"wrote {out / 'decision.txt'}")
        return 0 if rec.decision == "SHIP" else 1
    if args.strategy != "record_memo":
        print(f"unknown strategy {args.strategy}; more later", file=sys.stderr)
        return 2
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

    rn = sub.add_parser(
        "run",
        help=(
            "run a strategy. record_memo memoizes records. "
            "reference fits F(records, reference): unchanged reference entries are reused, "
            "and fitted numeric columns are rescaled. Probe is fixed at k=2, n_p=300, "
            "seed 20261006. --prep builds index sidecars; it is not inferred."
        ),
    )
    rn.add_argument("--strategy", default="record_memo", choices=("record_memo", "reference"))
    rn.add_argument(
        "--kind",
        default="lines",
        choices=("fastq_pe", "lines", "vcf", "fasta", "files", "linetable"),
    )
    rn.add_argument("--input")
    rn.add_argument(
        "--pin",
        nargs="?",
        const="",
        default=None,
        help="exact mode (reference strategy): options that set the tool's normalizer, inserted after the tool name, "
        "e.g. '-Z {entry_count}'. Placeholders: {entry_count}, {total_entry_length}. "
        "Pass --pin with no template to infer one when a value column depends on reference size. "
        "If every value column is the identity normalizer, exact mode runs with no pin: "
        "the probe-sample replay is compared with no added option, and the safety check still runs. "
        "A fitted size member with no pin still refuses. "
        "The template and its evidence are stored on the contract for that argv and reused. "
        "An explicit template overrides inference. If inference finds no pin, exact mode refuses. "
        "Output body is byte-identical to a full run or refused.",
    )
    rn.add_argument(
        "--slack",
        help=(
            "exact mode, with --pin: reporting flags used only to fill the cache and to scan "
            "new or changed entries. Replay uses the original argv plus the pin. "
            "'-E {E*2} --domE {domE*2}' multiplies those argv values by 2. "
            "A literal is allowed when argv already sets that flag; the factor is the ratio. "
            "The factor is stored on the contract. A later reference whose old/new entry-count "
            "ratio exceeds it is a full run. Without both --pin and --slack, a row-key superset still refuses. "
            "An inferred pin is not combined with --slack; pass an explicit pin template with --slack."
        ),
    )
    rn.add_argument("--reference", help="reference file. Default: the argv file that parses as entries and is not --input")
    rn.add_argument(
        "--prep",
        help="command run on each reference file before the tool. Use {reference} for that path. Builds index sidecars.",
    )
    rn.add_argument(
        "--subset-aux",
        action="append",
        default=None,
        help=(
            "exact and fit subset runs only: rewrite an argv file that lists entries. "
            "'{arg-after:--flag}:tokens' takes the file after --flag, drops tokens that name "
            "an entry outside the current subset, keeps every other token, and drops a line "
            "left with fewer than two tokens. A full run keeps the original file. "
            "The rule is caller data. It is not inferred."
        ),
    )
    rn.add_argument(
        "--invalidate-group",
        default=None,
        help=(
            "exact mode: a file whose lines are a group id and then entry names. "
            "'{arg-after:--flag}' names the argv flag that points at the file. "
            "A new, changed, or removed member makes every still-present member "
            "of that group get scanned again. The file path is not part of the "
            "cache namespace. The rule is caller data."
        ),
    )
    rn.add_argument(
        "--baseline",
        choices=("gestore",),
        default=None,
        help="gestore reruns changed entries and does not infer a normalizer, so size-dependent columns cannot be reused",
    )
    rn.add_argument("--r1")
    rn.add_argument("--r2")
    rn.add_argument("-o", "--out")
    rn.add_argument("--cache", help="persistent record cache (jsonl); default out_dir/cache.jsonl")
    rn.add_argument("--verify", choices=("audit", "full"), default="audit")
    rn.add_argument("--audit-p", type=float, default=None, dest="audit_p")
    rn.add_argument("--audit-seed", type=int, default=20260927, dest="audit_seed")
    rn.add_argument(
        "--audit-bound",
        action="store_true",
        help=(
            "size the audit sample so that a fraction audit-k-fraction of records "
            "is missed with probability at most audit-epsilon: "
            "s = ceil(ln(epsilon) / ln(1 - fraction))"
        ),
    )
    rn.add_argument("--audit-epsilon", type=float, default=0.05, dest="audit_epsilon")
    rn.add_argument(
        "--audit-k-fraction",
        type=float,
        default=0.01,
        dest="audit_k_fraction",
        help="k_min/n for --audit-bound (default 0.01)",
    )
    rn.add_argument(
        "--audit-size",
        type=int,
        default=None,
        dest="audit_size",
        help="override the bounded audit sample size",
    )
    rn.add_argument(
        "--first-use",
        nargs="?",
        const=2,
        type=int,
        default=0,
        dest="first_use",
        help=(
            "full stock comparison for the first K updates of a new program "
            "binary and argv namespace, then sampled checks. "
            "Passing the flag alone uses K=2. Omitting it leaves the mode off."
        ),
    )
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
