#!/usr/bin/env python3
"""CARC / Slurm GPU queue dashboard (stdlib only) — live by default.

Same behavior as the lab dashboard: SSH to Discovery, poll sinfo/squeue/sacct/sprio.
Requires USC VPN + working `ssh discovery` (or CARC_SSH_HOST).

  python3 server.py          # live
  python3 server.py --demo   # optional offline UI smoke test only

Open http://127.0.0.1:8767
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
FIXTURES = ROOT / "fixtures"

HOST = os.environ.get("CARC_DASH_HOST", "127.0.0.1")
PORT = int(os.environ.get("CARC_DASH_PORT", "8767"))
SSH_HOST = os.environ.get("CARC_SSH_HOST", "discovery")
# Display / history label only. Live Slurm queries use the remote $USER from SSH.
SSH_USER = os.environ.get("CARC_NETID", "").strip()
CACHE_TTL_SEC = float(os.environ.get("CARC_DASH_TTL", "25"))
HISTORY_HOURS = int(os.environ.get("CARC_DASH_HISTORY_HOURS", "48"))
PARTITIONS = os.environ.get("CARC_DASH_PARTITIONS", "gpu,debug")
DEMO = os.environ.get("CARC_DASH_DEMO", "").strip().lower() in {"1", "true", "yes", "on"}

_lock = threading.Lock()
_collect_lock = threading.Lock()
_cache: dict[str, Any] = {"ts": 0.0, "data": None, "error": None}


def _ssh(remote_cmd: str, timeout: int = 60) -> str:
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        "-o",
        "StrictHostKeyChecking=accept-new",
        SSH_HOST,
        remote_cmd,
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(err or f"ssh failed ({proc.returncode})")
    return proc.stdout


def _remote_user() -> str:
    if SSH_USER:
        return SSH_USER
    try:
        return _ssh("printf %s \"$USER\"", timeout=20).strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def _split_sections(out: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current = None
    buf: list[str] = []
    for line in out.splitlines():
        if line.startswith("___") and line.endswith("___"):
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = line.strip("_")
            buf = []
        else:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


def _parse_sinfo_gpu(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.strip().splitlines():
        if not line.strip() or line.startswith("PARTITION"):
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        partition, gres, nodes, cpus, memory = parts[:5]
        gpu_type, gpu_count = "none", 0
        m = re.search(r"gpu:([a-z0-9]+):(\d+)", gres, re.I)
        if m:
            gpu_type, gpu_count = m.group(1), int(m.group(2))
        rows.append(
            {
                "partition": partition,
                "gres": gres,
                "gpu_type": gpu_type,
                "gpus_per_node": gpu_count,
                "nodes": int(nodes) if str(nodes).isdigit() else nodes,
                "cpus": int(cpus) if str(cpus).isdigit() else cpus,
                "memory": memory,
            }
        )
    return rows


def _parse_pipe_table(text: str, fields: list[str]) -> list[dict[str, str]]:
    """Parse `|`-delimited squeue/sacct rows. Skips header if present."""
    rows: list[dict[str, str]] = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if not parts:
            continue
        head0 = parts[0].upper()
        if head0 in {"JOBID", "JOB_ID"}:
            continue
        if len(parts) < len(fields):
            parts.extend([""] * (len(fields) - len(parts)))
        row = {fields[i]: parts[i] for i in range(len(fields))}
        rows.append(row)
    return rows


def _parse_top_pending(text: str) -> list[dict[str, str]]:
    return _parse_pipe_table(text, ["job_id", "user", "priority", "time", "reason"])


def _normalize_state(state: str) -> str:
    s = (state or "").strip().upper()
    aliases = {
        "PENDING": "PD",
        "RUNNING": "R",
        "COMPLETED": "CD",
        "FAILED": "F",
        "CANCELLED": "CA",
        "TIMEOUT": "TO",
        "NODE_FAIL": "NF",
        "PREEMPTED": "PR",
        "COMPLETING": "CG",
    }
    if s in aliases:
        return aliases[s]
    for full, short in aliases.items():
        if s.startswith(full):
            return short
    return s[:2] if len(s) > 2 else s


def _collect_live() -> dict[str, Any]:
    user = _remote_user()
    parts = PARTITIONS
    remote = f"""
set -e
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
echo '___SINFO___'
sinfo -p {parts} -o '%P %G %D %c %m' 2>/dev/null || true
echo '___QUEUE_SUMMARY___'
echo -n 'gpu_running '; squeue -p gpu -t R -h 2>/dev/null | wc -l | tr -d ' '
echo -n 'gpu_pending '; squeue -p gpu -t PD -h 2>/dev/null | wc -l | tr -d ' '
echo -n 'debug_running '; squeue -p debug -t R -h 2>/dev/null | wc -l | tr -d ' '
echo -n 'debug_pending '; squeue -p debug -t PD -h 2>/dev/null | wc -l | tr -d ' '
echo '___MY_JOBS___'
squeue -u "$USER" -h -o '%i|%P|%j|%u|%t|%M|%D|%R' 2>/dev/null || true
echo '___RECENT___'
sacct -u "$USER" --starttime=now-{HISTORY_HOURS}hours -X -n -P \\
  -o JobID,Partition,JobName,State,Elapsed,ExitCode,End 2>/dev/null | tail -40 || true
echo '___TOP_PENDING___'
squeue -p gpu -t PD -h -o '%i|%u|%Q|%M|%R' 2>/dev/null | head -20 || true
echo '___SPRIO___'
squeue -u "$USER" -h -o '%i' 2>/dev/null | head -8 | while read -r j; do
  [ -n "$j" ] && sprio -j "$j" 2>/dev/null || true
done
echo '___START___'
squeue -u "$USER" --start -h -o '%i|%t|%S|%R' 2>/dev/null || true
echo '___DONE___'
"""
    out = _ssh(remote)
    sections = _split_sections(out)

    required = {"QUEUE_SUMMARY", "MY_JOBS", "DONE"}
    missing = required - set(sections)
    if missing:
        raise RuntimeError(f"incomplete SSH payload, missing: {sorted(missing)}")

    summary: dict[str, int] = {}
    for line in sections.get("QUEUE_SUMMARY", "").splitlines():
        parts_line = line.split()
        if len(parts_line) == 2 and parts_line[1].isdigit():
            summary[parts_line[0]] = int(parts_line[1])

    my_jobs_raw = _parse_pipe_table(
        sections.get("MY_JOBS", ""),
        ["job_id", "partition", "name", "user", "state", "time", "nodes", "reason"],
    )
    for row in my_jobs_raw:
        row["state"] = _normalize_state(row.get("state", ""))
        row["source"] = "queue"

    recent_raw = _parse_pipe_table(
        sections.get("RECENT", ""),
        ["job_id", "partition", "name", "state", "time", "exit_code", "end"],
    )
    queue_ids = {r["job_id"] for r in my_jobs_raw}
    history: list[dict[str, str]] = []
    for row in reversed(recent_raw):
        jid = row.get("job_id", "")
        if not jid or jid in queue_ids:
            continue
        st = _normalize_state(row.get("state", ""))
        if st in {"PD", "R", "CG"}:
            continue
        history.append(
            {
                "job_id": jid,
                "partition": row.get("partition", ""),
                "name": row.get("name", ""),
                "user": user,
                "state": st,
                "time": row.get("time", ""),
                "nodes": "",
                "reason": f"exit {row.get('exit_code', '')} · end {row.get('end', '')}",
                "source": "history",
            }
        )

    start_rows = _parse_pipe_table(
        sections.get("START", ""),
        ["job_id", "state", "start", "reason"],
    )
    start_map = {r["job_id"]: r for r in start_rows}
    for row in my_jobs_raw:
        est = start_map.get(row["job_id"])
        if est and est.get("start") and est["start"] not in {"N/A", "Unknown"}:
            row["reason"] = f"{row.get('reason', '')} · eta {est['start']}".strip(" ·")

    return {
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "ssh_host": SSH_HOST,
        "user": user,
        "mode": "live",
        "summary": {
            "gpu_running": summary.get("gpu_running", 0),
            "gpu_pending": summary.get("gpu_pending", 0),
            "debug_running": summary.get("debug_running", 0),
            "debug_pending": summary.get("debug_pending", 0),
        },
        "nodes": _parse_sinfo_gpu(sections.get("SINFO", "")),
        "my_jobs": my_jobs_raw,
        "recent_jobs": history[:25],
        "top_pending": _parse_top_pending(sections.get("TOP_PENDING", "")),
        "start_estimates": sections.get("START", ""),
        "sprio": sections.get("SPRIO", ""),
        "raw_ok": True,
    }


def _collect_demo() -> dict[str, Any]:
    path = FIXTURES / "demo_status.json"
    if not path.exists():
        raise RuntimeError(f"missing demo fixture: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["fetched_at"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    data["mode"] = "demo"
    data["ssh_host"] = data.get("ssh_host", "demo")
    data["user"] = SSH_USER or data.get("user", "demo_user")
    data["raw_ok"] = True
    return data


def _collect() -> dict[str, Any]:
    if DEMO:
        return _collect_demo()
    return _collect_live()


def get_status(force: bool = False) -> dict[str, Any]:
    now = time.time()
    with _lock:
        if (
            not force
            and _cache["data"] is not None
            and now - float(_cache["ts"]) < CACHE_TTL_SEC
        ):
            return {
                "ok": True,
                "cached": True,
                "cache_age_sec": round(now - float(_cache["ts"]), 1),
                **_cache["data"],
            }

    with _collect_lock:
        now = time.time()
        with _lock:
            if (
                not force
                and _cache["data"] is not None
                and now - float(_cache["ts"]) < CACHE_TTL_SEC
            ):
                return {
                    "ok": True,
                    "cached": True,
                    "cache_age_sec": round(now - float(_cache["ts"]), 1),
                    **_cache["data"],
                }
        try:
            data = _collect()
            with _lock:
                _cache["ts"] = time.time()
                _cache["data"] = data
                _cache["error"] = None
            return {"ok": True, "cached": False, "cache_age_sec": 0, **data}
        except Exception as exc:  # noqa: BLE001
            with _lock:
                _cache["error"] = str(exc)
                stale = _cache["data"]
            payload: dict[str, Any] = {
                "ok": False,
                "error": str(exc),
                "hint": (
                    "Connect USC VPN and ensure `ssh discovery` (or your CARC_SSH_HOST) "
                    "works with BatchMode. See ssh_config.example and README.md."
                ),
            }
            if stale:
                payload["stale"] = True
                payload["cached"] = True
                payload.update(stale)
            return payload


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[dash] {self.address_string()} {fmt % args}", flush=True)

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            html = (STATIC / "index.html").read_bytes()
            self._send(200, html, "text/html; charset=utf-8")
            return
        if path == "/static/style.css":
            css = (STATIC / "style.css").read_bytes()
            self._send(200, css, "text/css; charset=utf-8")
            return
        if path == "/api/status":
            force = "force=1" in (urlparse(self.path).query or "")
            payload = get_status(force=force)
            self._send(
                200,
                json.dumps(payload).encode("utf-8"),
                "application/json; charset=utf-8",
            )
            return
        if path == "/api/health":
            body = json.dumps(
                {
                    "ok": True,
                    "demo": DEMO,
                    "host": HOST,
                    "port": PORT,
                    "ssh_host": SSH_HOST,
                }
            ).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        self._send(404, b"not found", "text/plain; charset=utf-8")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="CARC GPU queue dashboard")
    p.add_argument("--host", default=HOST, help="bind address (default CARC_DASH_HOST)")
    p.add_argument("--port", type=int, default=PORT, help="port (default CARC_DASH_PORT)")
    p.add_argument(
        "--demo",
        action="store_true",
        help="serve fixture data (no SSH / VPN required)",
    )
    p.add_argument(
        "--ssh-host",
        default=SSH_HOST,
        help="SSH Host alias or hostname (default CARC_SSH_HOST)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    global HOST, PORT, SSH_HOST, DEMO  # noqa: PLW0603
    args = _parse_args(argv)
    HOST = args.host
    PORT = args.port
    SSH_HOST = args.ssh_host
    if args.demo:
        DEMO = True

    if not DEMO and not SSH_HOST:
        print("error: set CARC_SSH_HOST or pass --ssh-host", file=sys.stderr)
        raise SystemExit(2)

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    mode = "demo" if DEMO else "live"
    print(f"CARC GPU dashboard ({mode}) → http://{HOST}:{PORT}", flush=True)
    if DEMO:
        print("Serving fixtures/demo_status.json (no cluster access needed)", flush=True)
    else:
        print(f"SSH target: {SSH_HOST}", flush=True)
        if SSH_USER:
            print(f"Display user: {SSH_USER} (queries use remote $USER)", flush=True)
        else:
            print("Display user: auto from remote $USER", flush=True)
    print("Ctrl+C to stop", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye", flush=True)


if __name__ == "__main__":
    main()
