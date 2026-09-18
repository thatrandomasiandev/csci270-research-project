#!/usr/bin/env python3
"""Parse STAR Log.out phase timestamps into wall-clock buckets.

Phases (from Log.out / Log.progress markers STAR prints):
  pre_map   = process start → "started mapping"
  map       = "started mapping" → "finished mapping"
  post_map  = "finished mapping" → "finished successfully" (sort + finish)
  total     = process start → "finished successfully"

Also accepts an optional external wall_sec (harness wall-clock) for comparison.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean, stdev

# STAR prints e.g. "Sep 09 15:50:01 ..... loading genome"
TS_RE = re.compile(
    r"^(?P<mon>\w{3})\s+(?P<day>\d{1,2})\s+(?P<hms>\d{2}:\d{2}:\d{2})\s+\.+?\s+(?P<label>.+)$"
)

MARKERS = {
    "loading genome": "load_genome",
    "started mapping": "start_map",
    "finished mapping": "finish_map",
    "started sorting BAM": "start_sort",
    "finished successfully": "finish",
}


def parse_log(path: Path, year: int | None = None) -> dict[str, datetime]:
    """Parse phase markers from STAR stdout capture or Log.out.

    STAR prints '..... loading genome' etc. to logStdOut (terminal), not always
    to Log.out (logMain). Prefer a tee'd stdout file when available.
    """
    year = year or datetime.now().year
    found: dict[str, datetime] = {}
    text = path.read_text(errors="replace")
    for line in text.splitlines():
        # Tolerate leading whitespace / progress prefixes
        s = line.strip()
        m = TS_RE.match(s)
        if not m:
            # Fallback: find '..... <label>' anywhere on the line
            if "....." not in s:
                continue
            # e.g. "Sep 09 15:51:19 ..... loading genome"
            m = TS_RE.match(s)
            if not m:
                parts = s.split(".....", 1)
                if len(parts) != 2:
                    continue
                left, right = parts[0].strip(), parts[1].strip()
                # left should end with timestamp
                tm = re.search(r"(\w{3})\s+(\d{1,2})\s+(\d{2}:\d{2}:\d{2})$", left)
                if not tm:
                    continue
                label = right
                key = MARKERS.get(label)
                if key is None:
                    continue
                dt = datetime.strptime(
                    f"{year} {tm.group(1)} {tm.group(2)} {tm.group(3)}",
                    "%Y %b %d %H:%M:%S",
                )
                found.setdefault(key, dt)
                continue
        label = m.group("label").strip()
        key = MARKERS.get(label)
        if key is None:
            continue
        dt = datetime.strptime(
            f"{year} {m.group('mon')} {m.group('day')} {m.group('hms')}",
            "%Y %b %d %H:%M:%S",
        )
        found.setdefault(key, dt)
    return found


def phase_seconds(marks: dict[str, datetime], t0: datetime | None = None) -> dict[str, float | None]:
    """Compute phase durations. t0 defaults to load_genome (first logged event)."""
    t_load = marks.get("load_genome")
    t_start = marks.get("start_map")
    t_fmap = marks.get("finish_map")
    t_sort = marks.get("start_sort")
    t_fin = marks.get("finish")
    origin = t0 or t_load

    def delta(a: datetime | None, b: datetime | None) -> float | None:
        if a is None or b is None:
            return None
        return (b - a).total_seconds()

    pre = delta(origin, t_start)
    mapping = delta(t_start, t_fmap)
    # post includes sort if present, else finish_map → finish
    post = delta(t_fmap, t_fin)
    total = delta(origin, t_fin)
    load_only = delta(t_load, t_start) if t_load and t_start else None
    sort_only = delta(t_sort, t_fin) if t_sort and t_fin else None
    return {
        "pre_map_s": pre,
        "map_s": mapping,
        "post_map_s": post,
        "total_log_s": total,
        "load_to_map_s": load_only,
        "sort_to_finish_s": sort_only,
    }


def fmt(x: float | None) -> str:
    return f"{x:.3f}" if x is not None else "NA"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("logs", nargs="+", type=Path, help="STAR Log.out path(s)")
    ap.add_argument("--csv", type=Path, help="Append/write summary CSV")
    ap.add_argument("--label", default="", help="Run label column")
    ap.add_argument("--wall", type=float, default=None, help="External harness wall_sec")
    ap.add_argument("--year", type=int, default=None)
    args = ap.parse_args()

    rows = []
    for log in args.logs:
        marks = parse_log(log, args.year)
        ph = phase_seconds(marks)
        row = {
            "label": args.label or log.parent.name,
            "log": str(log),
            "wall_sec": args.wall,
            **ph,
            "markers": ",".join(sorted(marks.keys())),
        }
        rows.append(row)
        pre, mp, post, tot = ph["pre_map_s"], ph["map_s"], ph["post_map_s"], ph["total_log_s"]
        pre_pct = (100.0 * pre / tot) if pre is not None and tot else None
        print(
            f"{row['label']}: total_log={fmt(tot)}s  pre_map={fmt(pre)}s"
            f" ({fmt(pre_pct)}%)  map={fmt(mp)}s  post_map={fmt(post)}s"
            f"  wall={fmt(args.wall)}  markers=[{row['markers']}]"
        )

    if len(rows) > 1:
        for key in ("pre_map_s", "map_s", "post_map_s", "total_log_s"):
            vals = [r[key] for r in rows if r[key] is not None]
            if vals:
                sd = stdev(vals) if len(vals) > 1 else 0.0
                print(f"  mean {key}: {mean(vals):.3f} ± {sd:.3f} (n={len(vals)})")

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        write_header = not args.csv.exists()
        with args.csv.open("a", newline="") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "label",
                    "log",
                    "wall_sec",
                    "pre_map_s",
                    "map_s",
                    "post_map_s",
                    "total_log_s",
                    "load_to_map_s",
                    "sort_to_finish_s",
                    "markers",
                ],
            )
            if write_header:
                w.writeheader()
            for r in rows:
                w.writerow(r)


if __name__ == "__main__":
    main()
