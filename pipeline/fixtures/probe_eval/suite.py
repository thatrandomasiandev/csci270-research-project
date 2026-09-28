"""Synthetic probe-eval tools and inputs. Locked by docs/PROBE_EVAL_PROTOCOL.md."""

from __future__ import annotations

import hashlib
import os
import secrets
import time
from pathlib import Path

SEED = 20260927
CLASSES = ("F1", "F2", "F3", "F4", "F5", "F6-env", "F6-file", "F7", "F8")
FREQS = (1.0, 0.1, 0.01, 0.001)
FORMATS = ("vcf", "fasta")
CONTROLS = ("C1", "C2", "C3", "C4", "C5")
N_REC = 2500

VCF_HEADER = [
    "##fileformat=VCFv4.2",
    '##INFO=<ID=ANN,Number=1,Type=String,Description="produced">',
    '##INFO=<ID=RARE,Number=1,Type=String,Description="rare">',
    '##FILTER=<ID=PASS,Description="pass">',
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
]


def is_live(cls: str, fmt: str, index: int, p: float, *, seed: int = SEED) -> bool:
    if cls.startswith("C"):
        return False
    if cls in {"F6", "F6-env", "F6-file"}:
        return True
    raw = hashlib.sha256(f"{seed}|{cls}|{fmt}|{index}".encode()).hexdigest()
    return int(raw[:8], 16) % 10000 < int(round(p * 10000))


def vcf_key(index: int) -> str:
    return f"chr1:{index + 1}:A>T"


def fasta_seq(index: int) -> str:
    aa = "ACDEFGHIKLMNPQRSTVWY"
    return "M" + "".join(aa[(index + j) % len(aa)] for j in range(11))


def write_vcf(path: Path, indices: list[int], *, id_suffix: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = list(VCF_HEADER)
    for i in indices:
        ident = f"id{i}{id_suffix}"
        lines.append(f"chr1\t{i + 1}\t{ident}\tA\tT\t.\tPASS\t.")
    path.write_text("\n".join(lines) + "\n")
    return path


def write_fasta(path: Path, indices: list[int], *, desc_suffix: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    chunks: list[str] = []
    for i in indices:
        chunks.append(f">q{i} desc{i}{desc_suffix}")
        chunks.append(fasta_seq(i))
    path.write_text("\n".join(chunks) + "\n")
    return path


def parse_vcf_body(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln and not ln.startswith("#")]


def parse_fasta(text: str) -> list[tuple[int, str, str, str]]:
    recs: list[tuple[int, str, str, str]] = []
    name = desc = None
    seq: list[str] = []
    for line in text.splitlines():
        if line.startswith(">"):
            if name is not None:
                recs.append(_pack_fa(name, desc or "", "".join(seq)))
            parts = line[1:].strip().split(None, 1)
            name = parts[0] if parts else ""
            desc = parts[1] if len(parts) > 1 else ""
            seq = []
        else:
            seq.append(line.strip())
    if name is not None:
        recs.append(_pack_fa(name, desc or "", "".join(seq)))
    return recs


def _pack_fa(name: str, desc: str, seq: str) -> tuple[int, str, str, str]:
    idx = int(name[1:]) if name.startswith("q") and name[1:].isdigit() else 0
    return idx, name, desc, seq


def _safe_ann(index: int) -> str:
    return vcf_key(index)


def _safe_score(seq: str) -> int:
    return sum(ord(c) for c in seq) % 97


def hidden_cfg_path(src: Path) -> Path:
    return src.parent / "hidden.cfg"


def hidden_token(src: Path) -> str:
    path = hidden_cfg_path(src)
    if path.is_file():
        return path.read_text().strip() or "base"
    return "base"


def emit_vcf(text: str, cls: str, p: float, *, seed: int = SEED, src: Path | None = None) -> str:
    body = parse_vcf_body(text)
    header = [ln for ln in text.splitlines() if ln.startswith("#")]
    n = len(body)
    env = os.environ.get("ACTS_PROBE_EVAL_ENV", "base")
    out = list(header)
    prev_key = ""
    prev_idx = -1
    for pos, line in enumerate(body):
        parts = line.split("\t")
        while len(parts) < 8:
            parts.append(".")
        chrom, pos_s, ident, ref, alt = parts[:5]
        idx = int(pos_s) - 1
        live = is_live(cls, "vcf", idx, p, seed=seed)
        key = f"{chrom}:{pos_s}:{ref}>{alt.split(',')[0]}"
        rare = ""
        if cls == "C2":
            parts[6] = "PASS"
            ann = _safe_ann(idx)
        elif cls in {"C1", "C3"}:
            ann = _safe_ann(idx)
        elif cls == "F1" and live:
            ann = f"rnd{secrets.randbelow(1_000_000_000)}"
        elif cls == "F2" and live and prev_key:
            ann = f"prev:{prev_key}"
        elif cls == "F3" and live:
            ann = f"N{n}"
        elif cls == "F4" and live:
            ann = f"id:{ident}"
        elif cls == "F5":
            ann = _safe_ann(idx)
            if live:
                rare = ident
        elif cls in {"F6", "F6-env"}:
            ann = f"env:{env}:{key}"
        elif cls == "F6-file":
            ann = f"file:{hidden_token(src or Path('.'))}:{key}"
        elif cls == "F7" and live:
            ann = f"t{time.time_ns()}"
        elif cls == "F8" and live and prev_key:
            tokens = [prev_key, key] if prev_idx % 2 == 0 else [key, prev_key]
            ann = "|".join(tokens)
        else:
            ann = _safe_ann(idx)
        info = f"ANN={ann}"
        if rare:
            info += f";RARE={rare}"
        parts[7] = info
        out.append("\t".join(parts))
        prev_key = key
        prev_idx = idx
    return "\n".join(out) + "\n"


def emit_fasta(text: str, cls: str, p: float, *, seed: int = SEED, src: Path | None = None) -> str:
    recs = parse_fasta(text)
    n = len(recs)
    env = os.environ.get("ACTS_PROBE_EVAL_ENV", "base")
    lines = ["# probe_eval table"]
    prev_name = ""
    prev_idx = -1
    for idx, name, desc, seq in recs:
        live = is_live(cls, "fasta", idx, p, seed=seed)
        score = _safe_score(seq)
        extra = "."
        if cls == "C5" and score == 0:
            prev_name = name
            prev_idx = idx
            continue
        if cls == "F1" and live:
            score = secrets.randbelow(1_000_000_000)
        elif cls == "F2" and live and prev_name:
            score = sum(ord(c) for c in prev_name) % 97
        elif cls == "F3" and live:
            score = n
        elif cls == "F4" and live:
            score = sum(ord(c) for c in desc) % 97
        elif cls == "F5" and live:
            extra = desc
        elif cls in {"F6", "F6-env"}:
            score = sum(ord(c) for c in env) % 97
        elif cls == "F6-file":
            score = sum(ord(c) for c in hidden_token(src or Path("."))) % 97
        elif cls == "F7" and live:
            score = time.time_ns() % 97
        row_a = f"{name}\t{score}\t{extra}"
        row_b = f"{name}\t{score + 1}\t{extra}"
        if cls == "F8" and live and prev_name:
            if prev_idx % 2 == 0:
                lines.extend([row_b, row_a])
            else:
                lines.extend([row_a, row_b])
        elif cls == "F8":
            lines.extend([row_a, row_b])
        else:
            lines.append(row_a)
        prev_name = name
        prev_idx = idx
    return "\n".join(lines) + "\n"


def run_tool(kind: str, cls: str, p: float, src: Path, *, seed: int = SEED) -> str:
    text = src.read_text()
    if kind == "vcf":
        return emit_vcf(text, cls, p, seed=seed, src=src)
    if kind == "fasta":
        return emit_fasta(text, cls, p, seed=seed, src=src)
    raise ValueError(kind)
