"""VCF / VEP record body. MATCH is this body, never the dated header."""

from __future__ import annotations

import random
from collections import Counter
from pathlib import Path


def is_header(line: str) -> bool:
    return line.startswith("#")


def body_lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln and not is_header(ln)]


def variant_key(line: str) -> str:
    parts = line.split("\t")
    if len(parts) < 5:
        raise ValueError(f"not a VCF record: {line[:80]!r}")
    chrom, pos, _id, ref, alt = parts[:5]
    return f"{chrom}\t{pos}\t{ref}\t{alt}"


def body_map(text: str) -> dict[str, list[str]]:
    """Group records by key. Lists keep duplicates; nothing is dropped."""
    out: dict[str, list[str]] = {}
    for ln in body_lines(text):
        out.setdefault(variant_key(ln), []).append(ln)
    return out


def bodies_equal(a: str, b: str) -> bool:
    """Order-insensitive multiset of non-header record lines."""
    return Counter(body_lines(a)) == Counter(body_lines(b))


def shuffle_body(text: str, *, seed: int = 0) -> str:
    header = [ln for ln in text.splitlines() if is_header(ln)]
    body = body_lines(text)
    rng = random.Random(seed)
    rng.shuffle(body)
    return "\n".join(header + body) + ("\n" if text.endswith("\n") or body else "")


def read_maybe_gz(path: Path) -> str:
    if str(path).endswith(".gz"):
        import gzip

        return gzip.open(path, "rt").read()
    return path.read_text()
