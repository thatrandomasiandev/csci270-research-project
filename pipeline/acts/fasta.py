"""FASTA records. Cache key is the sequence, never the header."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FastaRec:
    name: str
    description: str
    seq: str

    @property
    def key(self) -> str:
        return seq_key(self.seq)


def seq_key(seq: str) -> str:
    aa = "".join(ch for ch in seq.upper() if not ch.isspace() and ch != "*")
    return hashlib.md5(aa.encode("ascii")).hexdigest()


def parse_fasta(text: str) -> list[FastaRec]:
    recs: list[FastaRec] = []
    name: str | None = None
    desc = ""
    chunks: list[str] = []
    for line in text.splitlines():
        if line.startswith(">"):
            if name is not None:
                recs.append(FastaRec(name, desc, "".join(chunks)))
            header = line[1:].strip()
            parts = header.split(None, 1)
            name = parts[0] if parts else ""
            desc = parts[1] if len(parts) > 1 else ""
            chunks = []
            continue
        chunks.append(line.strip())
    if name is not None:
        recs.append(FastaRec(name, desc, "".join(chunks)))
    return recs


def read_fasta(path: Path) -> list[FastaRec]:
    return parse_fasta(path.read_text())


def write_fasta(path: Path, recs: list[FastaRec]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for rec in recs:
        hdr = f">{rec.name}"
        if rec.description:
            hdr += f" {rec.description}"
        lines.append(hdr)
        seq = rec.seq
        if not seq:
            continue
        for i in range(0, len(seq), 60):
            lines.append(seq[i : i + 60])
    path.write_text("\n".join(lines) + ("\n" if lines else ""))
    return path


def shuffle_fasta(recs: list[FastaRec], *, seed: int = 7) -> list[FastaRec]:
    return random.Random(seed).sample(recs, len(recs))


def perturb_fasta(recs: list[FastaRec]) -> list[FastaRec]:
    """Rename every record and give it a fresh description.

    Descriptions are multi-word with varying word counts, so a tool that echoes the
    description as several whitespace tokens is exercised (2026-09-28 savings
    STOP_MATCH: single-token probe descriptions hid that case).
    """
    out: list[FastaRec] = []
    for i, rec in enumerate(recs):
        desc = "" if i % 4 == 3 else " ".join([f"PDESC_{i}"] + ["w"] * (1 + i % 3))
        out.append(FastaRec(f"PERT_{i}", desc, rec.seq))
    return out
