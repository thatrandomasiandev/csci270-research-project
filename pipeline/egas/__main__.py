"""CLI: python3 -m egas <check|gate|propose|run|verify> -c contract.toml"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from egas.contract import load_contract
from egas.driver import Driver
from egas.report import format_human
from egas.decide import DecisionRecord, Decision


def _driver(args: argparse.Namespace) -> Driver:
    contract = load_contract(Path(args.contract))
    out = Path(args.out) if args.out else None
    return Driver(contract, out_dir=out)


def cmd_check(args: argparse.Namespace) -> int:
    c = load_contract(Path(args.contract))
    stock = Path(c.resolve(c.stock_bin))
    opt = Path(c.resolve(c.opt_bin))
    print(f"ok  {c.name}  method={c.method}  target={c.target_speedup}×  "
          f"threads={c.threads}  runs={c.runs}  workloads={len(c.workloads)}")
    print(f"    root={c.root}")
    print(f"    stock={stock}")
    print(f"    opt={opt}")
    if not stock.is_file() or not opt.is_file():
        print("not ready  binaries missing — cannot bake off")
    if c.profile_path is None or not Path(c.profile_path).is_file():
        print("not ready  no profile — gate will refuse")
    return 0


def cmd_gate(args: argparse.Namespace) -> int:
    d = _driver(args)
    profile = d.load_profile(Path(args.profile) if args.profile else None)
    if profile is None:
        print("no profile — pass --profile or set contract.profile", file=sys.stderr)
        return 2
    res = d.gate(profile)
    assert res is not None
    print(res.status)
    print(res.reason)
    return 0 if res.status != "REFUSE" else 3


def cmd_propose(args: argparse.Namespace) -> int:
    args.skip_bakeoff = True
    args.apply = False
    args.workloads = None
    return cmd_run(args)


def cmd_verify(args: argparse.Namespace) -> int:
    args.apply = False
    args.skip_bakeoff = False
    return cmd_run(args)


def cmd_run(args: argparse.Namespace) -> int:
    d = _driver(args)
    report = d.run(
        profile_path=Path(args.profile) if getattr(args, "profile", None) else None,
        apply_automated=bool(getattr(args, "apply", False)),
        workloads=getattr(args, "workloads", None),
        skip_bakeoff=bool(getattr(args, "skip_bakeoff", False)),
    )
    rec = DecisionRecord(Decision(report.decision), report.reason)
    sys.stdout.write(format_human(report, rec))
    print(f"wrote {d.out_dir / 'report.json'}")
    return 0 if report.decision == Decision.SHIP.value else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="egas",
        description="Equivalence-gated 2× search. Refuses when Amdahl or MATCH fail.",
    )
    p.add_argument("-c", "--contract", required=True, help="TOML contract")
    p.add_argument("-o", "--out", help="report directory")
    p.add_argument("--profile", help="override contract.profile")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="validate the fairness contract")
    sub.add_parser("gate", help="Amdahl refuse / proceed from a profile")
    sub.add_parser("propose", help="write T1–T3 plan; do not time")
    run_p = sub.add_parser("run", help="gate + optional T4 apply + bake-off + decide")
    run_p.add_argument("--apply", action="store_true", help="apply automated T4 / STAR patch build")
    run_p.add_argument("--skip-bakeoff", action="store_true")
    run_p.add_argument("--workloads", nargs="*")
    ver = sub.add_parser("verify", help="MATCH + min_pair on existing binaries")
    ver.add_argument("--workloads", nargs="*")

    args = p.parse_args(argv)
    if args.cmd == "check":
        return cmd_check(args)
    if args.cmd == "gate":
        return cmd_gate(args)
    if args.cmd == "propose":
        return cmd_propose(args)
    if args.cmd == "verify":
        return cmd_verify(args)
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
