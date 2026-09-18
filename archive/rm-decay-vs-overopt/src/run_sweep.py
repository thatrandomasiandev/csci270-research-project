"""Sweep runner for multi-seed protocols and mitigations."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


PROTOCOLS = ["oracle", "decay", "overopt", "shared_blindspot"]
MITIGATIONS = {
    "none": {},
    "uncertainty_penalty": {"--uncertainty-penalty": "1.0"},
    "kl": {"--kl-coef": "0.1"},
    "more_prefs": {"--more-prefs": None},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3, 4])
    ap.add_argument("--protocols", nargs="+", default=PROTOCOLS)
    ap.add_argument("--envs", nargs="+", default=["point_mass"])
    ap.add_argument("--mitigations", nargs="+", default=["none"])
    ap.add_argument("--num-steps", type=int, default=30_000)
    ap.add_argument("--out-root", type=str, default="results/raw")
    ap.add_argument("--device", type=str, default="cpu")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--jobs", type=int, default=1, help="parallel workers")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    train = root / "src" / "train.py"
    jobs = []

    for env in args.envs:
        for protocol in args.protocols:
            for mit in args.mitigations:
                for seed in args.seeds:
                    out = Path(args.out_root) / f"{env}_{protocol}_{mit}_seed{seed}"
                    cmd = [
                        sys.executable,
                        str(train),
                        "--protocol",
                        protocol,
                        "--env",
                        env,
                        "--seed",
                        str(seed),
                        "--num-steps",
                        str(args.num_steps),
                        "--out-dir",
                        str(out),
                        "--device",
                        args.device,
                        "--mitigation",
                        mit,
                        "--diag-every",
                        "8",
                    ]
                    extra = MITIGATIONS.get(mit, {})
                    for k, v in extra.items():
                        cmd.append(k)
                        if v is not None:
                            cmd.append(v)
                    jobs.append(cmd)

    print(f"Launching {len(jobs)} runs (parallelism={args.jobs})")
    if args.dry_run:
        for cmd in jobs:
            print(" ".join(cmd))
        return

    if args.jobs <= 1:
        for cmd in jobs:
            print(" ".join(cmd))
            subprocess.run(cmd, check=True)
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _run(cmd):
            print(" ".join(cmd))
            return subprocess.run(cmd, check=True)

        with ThreadPoolExecutor(max_workers=args.jobs) as ex:
            futs = [ex.submit(_run, cmd) for cmd in jobs]
            for f in as_completed(futs):
                f.result()


if __name__ == "__main__":
    main()
