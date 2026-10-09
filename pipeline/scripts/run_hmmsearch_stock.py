#!/usr/bin/env python3
"""Time one pre-registered stock hmmsearch genome from the task manifest."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from hmmsearch_stock import load_manifest, measure_stock  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--index", type=int, default=None)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--hmm", required=True, type=Path)
    parser.add_argument("--hmmsearch", required=True)
    parser.add_argument("--hmmpress", required=True)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--cpu", type=int, default=32)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    tasks = load_manifest(args.manifest)
    index = args.index
    if index is None:
        raw = os.environ.get("SLURM_ARRAY_TASK_ID", "").strip()
        if not raw:
            raise SystemExit("pass --index or set SLURM_ARRAY_TASK_ID")
        index = int(raw)
    if index < 0 or index >= len(tasks):
        raise SystemExit(f"array index {index} is outside 0..{len(tasks) - 1}")
    destination = measure_stock(
        tasks[index],
        data_root=args.data_root,
        hmm=args.hmm,
        hmmsearch=args.hmmsearch,
        hmmpress=args.hmmpress,
        out_dir=args.out_dir,
        work=args.work,
        cpu=args.cpu,
    )
    print(f"wrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
