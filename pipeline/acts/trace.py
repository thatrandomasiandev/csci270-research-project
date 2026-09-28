"""Probe-time file tracing. Linux strace only. Rattle transfer, not a novelty claim."""

from __future__ import annotations

import re
import shutil
import stat
import sys
from pathlib import Path

_OPEN_RE = re.compile(
    r"""(?:openat|open)\s*\(\s*(?:AT_FDCWD,\s*)?"((?:\\.|[^"\\])*)"\s*,\s*([^)]+)\)\s*=\s*(-?\d+)"""
)
_SKIP_PREFIXES = ("/proc/", "/sys/", "/dev/")
_WRITE_FLAGS = ("O_WRONLY", "O_RDWR", "O_CREAT", "O_TRUNC", "O_APPEND")


def tracing_available() -> bool:
    return shutil.which("strace") is not None


_WARNED = False


def warn_untraced() -> None:
    global _WARNED
    if _WARNED:
        return
    _WARNED = True
    print(
        "warning: file tracing unavailable (no strace); "
        "files not named in argv are uncovered",
        file=sys.stderr,
    )


def _unescape(raw: str) -> str:
    return raw.encode("utf-8").decode("unicode_escape")


def _is_temp(path: Path, work: Path | None) -> bool:
    """Drop the infer work tree and obvious scratch names, not the whole /tmp."""
    if work is not None:
        try:
            path.resolve().relative_to(work.resolve())
            return True
        except ValueError:
            pass
    name = path.name
    return name.endswith((".tmp", ".swp", ".pyc")) or name == "tmp"


def parse_strace(
    text: str,
    *,
    input_path: Path | None = None,
    work: Path | None = None,
) -> list[str]:
    """Return resolved read-only regular files, excluding protocol skips."""
    skip: set[str] = set()
    if input_path is not None:
        try:
            skip.add(str(input_path.resolve()))
        except OSError:
            skip.add(str(input_path))
    found: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        m = _OPEN_RE.search(line)
        if not m:
            continue
        raw, flags, ret = m.group(1), m.group(2), m.group(3)
        if ret.startswith("-"):
            continue
        if any(tok in flags for tok in _WRITE_FLAGS):
            continue
        if "O_RDONLY" not in flags and "O_RDWR" not in flags:
            # open() without flags is read; require no write flags (already).
            pass
        try:
            path = Path(_unescape(raw))
        except ValueError:
            continue
        if not path.is_absolute():
            continue
        try:
            resolved = str(path.resolve())
        except OSError:
            continue
        if resolved in skip or resolved in seen:
            continue
        if resolved.startswith(_SKIP_PREFIXES) or resolved in ("/proc", "/sys", "/dev"):
            continue
        p = Path(resolved)
        try:
            mode = p.stat().st_mode
        except OSError:
            continue
        if not stat.S_ISREG(mode):
            continue
        if _is_temp(p, work):
            continue
        seen.add(resolved)
        found.append(resolved)
    found.sort()
    return found


def traced_argv(argv: list[str], log_path: Path) -> list[str]:
    return ["strace", "-f", "-e", "trace=openat,open", "-o", str(log_path), "--", *argv]


def run_traced(
    argv: list[str],
    *,
    input_path: Path,
    work: Path,
    runner,
) -> tuple[str, list[str], str]:
    """Run *runner(argv, input_path)* under strace. Returns stdout, files, status."""
    if not tracing_available():
        warn_untraced()
        return runner(argv, input_path), [], "unavailable"
    log_path = work / "strace.log"
    work.mkdir(parents=True, exist_ok=True)
    wrapped = traced_argv(argv, log_path)
    try:
        out = runner(wrapped, input_path)
    except Exception:
        # runner raises InferError on tool failure; still parse the log if any
        files = parse_strace(
            log_path.read_text() if log_path.is_file() else "",
            input_path=input_path,
            work=work,
        )
        raise
    files = parse_strace(
        log_path.read_text() if log_path.is_file() else "",
        input_path=input_path,
        work=work,
    )
    return out, files, "ok"
