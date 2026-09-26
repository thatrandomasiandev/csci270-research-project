"""VCF column / INFO helpers. Format-level; no tool names."""

from __future__ import annotations

from typing import Iterable

COL_CHROM, COL_POS, COL_ID, COL_REF, COL_ALT = range(5)
COL_QUAL, COL_FILTER, COL_INFO, COL_FORMAT = 5, 6, 7, 8

NAMED = {
    "CHROM": COL_CHROM,
    "POS": COL_POS,
    "ID": COL_ID,
    "REF": COL_REF,
    "ALT": COL_ALT,
    "QUAL": COL_QUAL,
    "FILTER": COL_FILTER,
    "INFO": COL_INFO,
    "FORMAT": COL_FORMAT,
}

KEY_FIELDS = ("CHROM", "POS", "REF", "ALT")
NONKEY_GROUPS = ("ID", "QUAL", "FILTER", "INFO", "SAMPLES")


def split_record(line: str) -> list[str]:
    return line.rstrip("\n").split("\t")


def join_record(parts: list[str]) -> str:
    return "\t".join(parts)


def parse_info(info: str) -> list[tuple[str, str | None]]:
    if not info or info == ".":
        return []
    out: list[tuple[str, str | None]] = []
    for part in info.split(";"):
        if not part:
            continue
        if "=" in part:
            key, val = part.split("=", 1)
            out.append((key, val))
        else:
            out.append((part, None))
    return out


def info_map(info: str) -> dict[str, str | None]:
    return dict(parse_info(info))


def format_info_item(key: str, val: str | None) -> str:
    return key if val is None else f"{key}={val}"


def format_info(items: Iterable[tuple[str, str | None]]) -> str:
    parts = [format_info_item(k, v) for k, v in items]
    return ";".join(parts) if parts else "."


def col(parts: list[str], name: str) -> str | None:
    i = NAMED.get(name)
    if i is None or i >= len(parts):
        return None
    return parts[i]


def set_col(parts: list[str], name: str, value: str) -> None:
    i = NAMED[name]
    while len(parts) <= i:
        parts.append(".")
    parts[i] = value


def flip_gt(gt: str) -> str:
    sep = "|" if "|" in gt else "/"
    alleles = gt.split(sep)
    flipped = [{"0": "1", "1": "0"}.get(a, a) for a in alleles]
    if flipped == alleles:
        flipped[0] = "1" if flipped[0] != "1" else "0"
    return sep.join(flipped)


def perturb_sample(token: str) -> str:
    if "|" in token or "/" in token:
        return flip_gt(token)
    if token in {".", "./.", ".|."}:
        return "0/1"
    return token[::-1] if token else "PERT"


def info_types(header: list[str]) -> dict[str, str]:
    """Parse ##INFO=<ID=X,...,Type=Float,...> → {X: Float}."""
    out: dict[str, str] = {}
    for ln in header:
        if not ln.startswith("##INFO=<"):
            continue
        body = ln[len("##INFO=<") :].rstrip(">")
        ident = None
        typ = None
        for bit in body.split(","):
            if bit.startswith("ID="):
                ident = bit[3:]
            elif bit.startswith("Type="):
                typ = bit[5:]
        if ident and typ:
            out[ident] = typ
    return out


def perturb_info_value(val: str | None, typ: str | None) -> str | None:
    if val is None:
        return "1"
    t = (typ or "").lower()
    if t == "float":
        return "0.123456"
    if t == "integer":
        return "999991"
    if val == ".":
        return "PERT"
    return f"PERT_{val}" if len(val) < 40 else "PERT"


def perturb_info(info: str, types: dict[str, str] | None = None) -> str:
    items = parse_info(info)
    if not items:
        return info
    types = types or {}
    out: list[tuple[str, str | None]] = []
    for key, val in items:
        out.append((key, perturb_info_value(val, types.get(key))))
    return format_info(out)


def perturb_record(
    line: str,
    n: int,
    groups: Iterable[str] | None = None,
    *,
    info_types_map: dict[str, str] | None = None,
) -> str:
    """Replace non-key fields. CHROM/POS/REF/ALT stay put."""
    parts = split_record(line)
    wanted = set(groups) if groups is not None else set(NONKEY_GROUPS)
    if "ID" in wanted and len(parts) > COL_ID:
        parts[COL_ID] = f"PERTURB_{n}"
    if "QUAL" in wanted and len(parts) > COL_QUAL:
        parts[COL_QUAL] = "99" if parts[COL_QUAL] == "." else "."
    if "FILTER" in wanted and len(parts) > COL_FILTER:
        parts[COL_FILTER] = "PERT" if parts[COL_FILTER] == "PASS" else "PASS"
    if "INFO" in wanted and len(parts) > COL_INFO:
        parts[COL_INFO] = perturb_info(parts[COL_INFO], info_types_map)
    if "SAMPLES" in wanted and len(parts) > COL_FORMAT + 1:
        for i in range(COL_FORMAT + 1, len(parts)):
            parts[i] = perturb_sample(parts[i])
    return join_record(parts)


def cache_key(line: str, fields: Iterable[str]) -> str:
    parts = split_record(line)
    bits: list[str] = []
    for name in fields:
        if name == "SAMPLES":
            bits.extend(parts[COL_FORMAT:] if len(parts) > COL_FORMAT else [])
        else:
            val = col(parts, name)
            if val is None:
                raise ValueError(f"missing {name} on {line[:80]!r}")
            bits.append(val)
    return "\t".join(bits)
