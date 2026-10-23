#!/usr/bin/env python3
"""Fail if submission surfaces contain deanonymizing strings."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAPER = REPO / "pipeline/paper/tare"

# Host/lab/identity tokens. "discovery" and "CARC" are the cluster SSH alias /
# center name — body prose must not use them; LaTeX % comments (provenance
# keys like discovery_s) are stripped before scanning .tex sources.
FORBIDDEN = [
    r"Terranova",
    r"Joshua(?!\s+Project)",
    r"\bJosh\b",
    r"jjt_373",
    r"\bbiyik\b",
    r"\bBiyik\b",
    r"\bUSC\b",
    r"University of Southern California",
    r"\bCARC\b",
    r"\bdiscovery\b",
    r"/project2/",
    r"/Users/",
    r"\bLIRA\b",
    r"@usc\.edu",
    r"thatrandomasiandev",
]


def strip_tex_comments(text: str) -> str:
    """Remove TeX % comments (not escaped \\%). Keep newlines for line mapping."""
    out = []
    for line in text.splitlines(keepends=True):
        i = 0
        buf = []
        while i < len(line):
            ch = line[i]
            if ch == "%" and (i == 0 or line[i - 1] != "\\"):
                buf.append("\n" if line.endswith("\n") else "")
                break
            buf.append(ch)
            i += 1
        else:
            buf.append("") if False else None
        out.append("".join(buf) if buf else ("\n" if line.endswith("\n") else ""))
    return "".join(out)


def pdf_text(pdf: Path) -> str:
    if not pdf.is_file():
        return ""
    for cmd in (
        ["pdftotext", str(pdf), "-"],
        ["strings", str(pdf)],
    ):
        try:
            proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
            if proc.returncode == 0 and proc.stdout:
                return proc.stdout
        except FileNotFoundError:
            continue
    return ""


def scan_blob(label: str, text: str, bad: list[str]) -> None:
    for pat in FORBIDDEN:
        if re.search(pat, text):
            bad.append(f"{label}: matches /{pat}/")


def main() -> int:
    bad: list[str] = []
    for path in [PAPER / "main.tex", PAPER / "refs.bib", PAPER / "macros_pending.tex"]:
        if not path.is_file():
            continue
        raw = path.read_text(errors="replace")
        text = strip_tex_comments(raw) if path.suffix == ".tex" else raw
        scan_blob(str(path.relative_to(REPO)), text, bad)

    pdf = PAPER / "main.pdf"
    blob = pdf_text(pdf)
    if blob:
        scan_blob("main.pdf text/strings", blob, bad)

    try:
        proc = subprocess.run(
            ["pdfinfo", str(pdf)], check=False, capture_output=True, text=True
        )
        meta = proc.stdout or ""
        scan_blob("main.pdf pdfinfo", meta, bad)
    except FileNotFoundError:
        pass

    if bad:
        print("ANONYMITY FAIL:")
        for line in bad:
            print(" ", line)
        return 1
    print("ANONYMITY OK (paper surfaces)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
