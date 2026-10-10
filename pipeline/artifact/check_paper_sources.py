#!/usr/bin/env python3
"""Check every ``% source:`` comment in pipeline/paper/main.tex.

Read-only. Each displayed number must be the cited file's value at the
printed precision, or the closed form the comment names. Exit 1 on any
mismatch. This script does not write the paper or the result files.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAPER = REPO / "pipeline" / "paper" / "main.tex"

NUMBER = r"[-+]?(?:\d+\.\d+|\d+)(?:[eE][-+]?\d+)?"
ASSIGN = re.compile(rf"([A-Za-z_][\w.]*)\s*=\s*({NUMBER})(?![A-Za-z])")
SCOPE_ASSIGN = re.compile(rf"\b(hmmscan|hmmsearch|A|B)\s*=\s*({NUMBER})(?![A-Za-z])")
STRING_ASSIGN = re.compile(
    r'([A-Za-z_][\w.]*)\s*=\s*(true|false|SHIP|REFUSE|STOP_MATCH|B1|"[^"]*")'
)
BARE_BOOL = re.compile(r"\b([A-Za-z_][\w.]*)\s+(true|false)\b")
FILE_REF = re.compile(r"(pipeline/(?:results|docs)/[A-Za-z0-9_./-]+\.(?:json|md))")
SCOPES = {"hmmscan", "hmmsearch", "A", "B"}


def close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-9)


def load_json(path: Path):
    return json.loads(path.read_text())


def walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def num_eq(got, value: float) -> bool:
    if isinstance(got, bool) or got is None:
        return False
    if isinstance(got, (int, float)):
        return close(float(got), value)
    if isinstance(got, str):
        try:
            return close(float(got), value)
        except ValueError:
            return False
    return False


def lookup(node, path: str):
    """Follow a dotted path, skipping one intermediate object when a comment omits it."""
    current = node
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        if isinstance(current, dict):
            found = None
            for value in current.values():
                if isinstance(value, dict) and part in value:
                    found = value[part]
                    break
            if found is None:
                return None
            current = found
            continue
        if isinstance(current, list):
            found = None
            for item in current:
                if isinstance(item, dict) and (
                    item.get("mode") == part or item.get("collection") == part or item.get("name") == part
                ):
                    found = item
                    break
            if found is None:
                return None
            current = found
            continue
        return None
    return current


def find_path(node, path: str):
    """Return every value reached by path, starting at any object."""
    found = []

    def search(current):
        if isinstance(current, dict):
            got = lookup(current, path)
            if got is not None:
                found.append(got)
            for value in current.values():
                search(value)
        elif isinstance(current, list):
            for value in current:
                search(value)

    search(node)
    return found


def ancestors_of(node, target, trail=()):
    if node is target:
        return trail
    if isinstance(node, dict):
        for value in node.values():
            found = ancestors_of(value, target, trail + (node,))
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = ancestors_of(value, target, trail + (node,))
            if found is not None:
                return found
    return None


def scope_ok(blob, obj, scopes: set[str]) -> bool:
    if not scopes:
        return True
    chain = []
    anc = ancestors_of(blob, obj)
    if anc is None:
        chain = [obj]
    else:
        chain = [obj, *anc]
    for scope in scopes:
        if scope in {"hmmscan", "hmmsearch"}:
            if not any(isinstance(item, dict) and item.get("mode") == scope for item in chain):
                return False
        elif not any(
            isinstance(item, dict) and (item.get("collection") == scope or item.get("name") == scope)
            for item in chain
        ):
            return False
    return True


def scopes_in(text: str) -> set[str]:
    found = set(re.findall(r"\b(hmmscan|hmmsearch)\b", text))
    found.update(re.findall(r"(?<![A-Za-z0-9_.])([AB])(?![A-Za-z0-9_])", text))
    return found


def position_in(text: str) -> int | None:
    found = re.findall(r"position\s*=?\s*(\d+)", text)
    if len(set(found)) == 1:
        return int(found[0])
    return None


def value_in(blobs, path: str, value: float, scopes: set[str], position: int | None, key_is_position: bool) -> bool:
    for blob in blobs:
        for got in find_path(blob, path):
            if num_eq(got, value) and not scopes and position is None:
                return True
        for obj in walk(blob):
            if not isinstance(obj, dict):
                continue
            if position is not None and not key_is_position and obj.get("position") != position:
                continue
            if scopes and not scope_ok(blob, obj, scopes):
                continue
            got = lookup(obj, path) if "." in path else obj.get(path)
            if num_eq(got, value):
                return True
    return False


def headline(repo: Path) -> tuple[int, dict]:
    data = load_json(repo / "pipeline/results/headline_screen.json")
    modes = {row["mode"]: row for row in data["modes"]}
    return int(data["N"]), modes


def protocol_n_p(repo: Path) -> int:
    text = (repo / "pipeline/docs/REFERENCE_INCREMENTAL_PROTOCOL.md").read_text()
    found = re.findall(r"n_p\s*=\s*(\d+)\b", text)
    if "300" not in found:
        raise ValueError(f"protocol n_p values are {found}")
    return 300


def amdahl(repo: Path) -> dict:
    capital_n, modes = headline(repo)
    out = {}
    for name, row in modes.items():
        a = float(row["a_s"])
        b = float(row["b_s_per_record"])
        w = float(row["w"]["w_s"])
        bn = b * capital_n
        out[name] = {
            "a": a,
            "b": b,
            "w": w,
            "bN": bn,
            "a_share": a / (a + bn),
            "b_share": bn / (a + bn),
            "ceiling": (a + bn) / (a + w),
        }
    return out


def kill_changed(repo: Path) -> dict:
    kill = load_json(repo / "pipeline/results/reference_kill_r1.json")
    changed = kill["z_new"] - kill["unchanged_strict"]
    return {
        "z_new": kill["z_new"],
        "z_old": kill["z_old"],
        "unchanged_strict": kill["unchanged_strict"],
        "changed": changed,
        "c": changed / kill["z_new"],
        "phi_cached": kill["z_new"] / kill["z_old"],
        "phi_changed": kill["z_new"] / changed,
    }


def formulas(source: str, repo: Path) -> list[float]:
    out: list[float] = []
    compact = source.replace(" ", "")
    screen = amdahl(repo)
    scan = screen["hmmscan"]
    search = screen["hmmsearch"]
    probe_n = protocol_n_p(repo)

    closed = re.search(rf"\(1-0?\.01\)\^(\d+)\s*=\s*({NUMBER})", source)
    if closed:
        got = (1 - 0.01) ** int(closed.group(1))
        stated = float(closed.group(2))
        if not close(got, stated):
            raise ValueError(f"(1-0.01)^{closed.group(1)} = {got} but the comment says {stated}")
        out.extend([0.01, float(closed.group(1)), got])

    if "b_s_per_record*N" in compact or "b*N" in compact or "b_s_per_record * N" in source:
        out.extend([scan["bN"], search["bN"]])
    if "a/(a+bN)" in compact or "computeda share" in compact or "computed a share" in source:
        out.extend([scan["a_share"], search["a_share"]])
    if "bN/(a+bN)" in compact:
        out.extend([scan["b_share"], search["b_share"]])
    if "(a+bN)/(a+w)" in compact or (
        "PROJECTED" in source and "headline_screen" in source and "P=" not in compact and "P_both" not in source
    ):
        out.extend([scan["ceiling"], search["ceiling"]])

    primary = 3 * scan["a"] + 2 * scan["b"] * probe_n
    both = 5 * scan["a"] + 3 * scan["b"] * probe_n
    if "3a+2" in compact or "w/P" in source:
        out.append(primary)
        if "ratio=" in source or "w/P" in source:
            out.append(scan["w"] / primary)
    if "5a+3" in compact or "P_both" in source:
        out.append(both)

    if "c*=" in source or "c*" in source or "c\\*" in source:
        changed = kill_changed(repo)
        capital_n, _modes = headline(repo)
        which = both if ("P_both" in source or "5a+3" in compact) else primary
        if "P_both" in source or "5a+3" in compact or "3a+2" in compact or "S=" in source:
            out.append(1 - which / (scan["b"] * capital_n))
            out.append((1 - changed["c"]) * scan["b"] * capital_n)
            out.append(((1 - changed["c"]) * scan["b"] * capital_n) / which)

    if "z_new/z_old" in source or "z_new/(z_new-unchanged_strict)" in source or "changed=4052" in source:
        changed = kill_changed(repo)
        out.extend([changed["z_new"], changed["z_old"], changed["unchanged_strict"], changed["changed"], changed["c"]])
        if "z_new/z_old" in source:
            out.append(changed["phi_cached"])
        if "z_new/(z_new-unchanged_strict)" in source or "changed=4052" in source:
            out.append(changed["phi_changed"])

    if "1156-724" in source:
        kill = load_json(repo / "pipeline/results/reference_kill_r2p.json")
        out.append(float(kill["evalue_tokens"] - kill["evalue_byte_reproducible"]))

    if "0/56" in source:
        rows = load_json(repo / "pipeline/results/probe_eval_audit.json")["rows"]
        classes = {"F1", "F2", "F3", "F4", "F5", "F7", "F8"}
        for size in (500, 2000):
            subset = [row for row in rows if row["probe_n"] == size and row["class"] in classes]
            unsafe = sum(1 for row in subset if row["unsafe_ship"])
            if unsafe != 0 or len(subset) != 56:
                raise ValueError(f"probe_n={size} in-scope unsafe-ship is {unsafe}/{len(subset)}")
        out.extend([0, 56])

    if "k+1" in source:
        text = (repo / "pipeline/docs/REFERENCE_INCREMENTAL_PROTOCOL.md").read_text()
        if not re.search(r"k\s*=\s*2\b", text):
            raise ValueError("protocol does not pin k=2")
        out.append(3)
    if "REFERENCE_INCREMENTAL_PROTOCOL.md" in source:
        text = (repo / "pipeline/docs/REFERENCE_INCREMENTAL_PROTOCOL.md").read_text()
        if "parameter k" in source:
            if not re.search(r"k\s*=\s*2\b", text):
                raise ValueError("protocol does not pin k=2")
            out.append(2)
        if "parameter n_p" in source:
            out.append(float(protocol_n_p(repo)))
        if "seed" in source and re.search(r"\b20261006\b", text):
            out.append(20261006)
        if re.search(r"\baudit q\b", source):
            if not re.search(r"q\s*=\s*0\.02\b", text):
                raise ValueError("protocol does not pin q=0.02")
            out.append(0.02)

    return out


def curve_anchors(source: str, blobs: list) -> list[float]:
    if "curve" not in source:
        return []
    values: list[float] = []
    for blob in blobs:
        if not isinstance(blob, dict):
            continue
        if "genbank" in source and "genbank_hmmscan" in blob:
            curve = blob["genbank_hmmscan"]["curve"]
            if "ratio" in source:
                ratios = [row["ratio"] for row in curve]
                if any(item != 0 for item in ratios):
                    raise ValueError(f"genbank ratios are {ratios}")
                values.extend(float(item) for item in ratios)
            if "dep_recall=0" in source:
                recalls = [row["dep_recall"] for row in curve]
                if any(item != 0 for item in recalls):
                    raise ValueError(f"genbank dep_recall is {recalls}")
                values.extend(float(item) for item in recalls)
            if "k=6" in source:
                row = next(item for item in curve if item["k"] == 6)
                values.append(float(row["copy_aware_recall"]))
        if "refseq" in source and "refseq_hmmscan_control" in blob:
            curve = blob["refseq_hmmscan_control"]["curve"]
            if "ratio" in source:
                ratios = [row["ratio"] for row in curve]
                if any(item != 1 for item in ratios):
                    raise ValueError(f"refseq ratios are {ratios}")
                values.extend(float(item) for item in ratios)
    return values


def fit_error_anchors(text: str) -> list[float]:
    chunks = re.split(r"\n## ", text)
    counts = []
    for chunk in chunks:
        if "hmmsearch (PRIMARY)" not in chunk or "**Fit error" not in chunk:
            continue
        counts.append(len(re.findall(r"^- genome \d+:", chunk, flags=re.M)))
    if counts != [6, 6]:
        raise ValueError(f"primary hmmsearch fit-error lists have {counts} genomes")
    return [6, 6, 12]


def normalize_text(text: str) -> str:
    text = text.replace("\\%", "%")
    text = text.replace("{,}", "")
    text = text.replace("\\,", "")
    text = text.replace("\\_", "_")
    text = re.sub(r"\\texttt\{([^{}]*)\}", r" \1 ", text)
    text = re.sub(r"\\mathrm\{([^{}]*)\}", r" \1 ", text)
    text = re.sub(
        r"(\d+\.\d+)\s*\\times\s*10\^\{(-?\d+)\}",
        lambda match: f"{match.group(1)}e{match.group(2)}",
        text,
    )
    text = re.sub(r"\\[a-zA-Z]+", " ", text)
    text = text.replace("{", " ").replace("}", " ").replace("$", " ").replace("~", " ")
    text = text.replace("`", "").replace("*", "")
    text = re.sub(r"20\d{2}_\d{2}", " ", text)
    return text


def line_numbers_cited(line: str, source_line: str) -> bool:
    """True when every number on line is written in the source comment."""
    source = source_line.split("% source:", 1)[-1]
    for match in re.finditer(r"\d+\.\d+|\d+", normalize_text(line)):
        token = match.group(0)
        if re.search(rf"(?<!\d){re.escape(token)}(?!\d)", source) is None:
            return False
    return True


def ends_sentence(line: str) -> bool:
    stripped = re.sub(r"\\\\$", "", line.strip()).strip()
    return stripped.endswith((".", "?", "!"))


def is_display_line(line: str) -> bool:
    plain = re.sub(r"\$.*?\$", "", line)
    plain = re.sub(r"\\[a-zA-Z]+", "", plain)
    plain = re.sub(r"[^A-Za-z]", "", plain)
    return "$" in line and len(plain) <= 3


def claim_text(lines: list[str], index: int) -> str:
    raw = lines[index]
    prefix = raw.split("% source:", 1)[0].strip()
    if prefix and re.search(r"\d", prefix):
        return prefix
    chunks: list[str] = []
    if prefix:
        chunks.append(prefix)
    saw_digit = bool(re.search(r"\d", prefix))
    j = index - 1
    while j >= 0:
        piece = lines[j].strip()
        if not piece or "% source:" in piece or piece.startswith("%"):
            break
        if piece in {"\\[", "\\]", "\\midrule", "\\toprule", "\\bottomrule"} or piece.startswith("\\label"):
            j -= 1
            continue
        if piece.startswith(("\\section", "\\subsection", "\\paragraph", "\\caption", "\\begin", "\\end")):
            break
        if chunks and "&" in piece and "&" in chunks[0]:
            break
        has_digit = bool(re.search(r"\d", piece))
        if saw_digit and has_digit and not line_numbers_cited(piece, lines[index]):
            break
        if saw_digit and ends_sentence(piece):
            break
        chunks.append(piece)
        saw_digit = saw_digit or has_digit
        j -= 1
    forward: list[str] = []
    k = index + 1
    while k < len(lines):
        piece = lines[k].strip()
        if not piece or "% source:" in piece or piece.startswith("%"):
            break
        if piece.startswith(("\\section", "\\subsection", "\\paragraph", "\\caption", "\\begin", "\\end", "\\item", "\\pending")):
            break
        if "\\pending" in piece or "\\cite" in piece:
            break
        if is_display_line(piece) or "&" in piece:
            break
        if re.search(r"\d", piece) and not line_numbers_cited(piece, lines[index]):
            break
        forward.append(piece)
        if ends_sentence(piece):
            break
        k += 1
    return " ".join([*reversed(chunks), *forward])


def claim_quantities(claim: str) -> list[dict]:
    text = normalize_text(claim)
    text = re.sub(r"WP_\d+\.\d+", " ", text)
    occupied = [False] * (len(text) + 1)
    found: list[tuple[int, str, re.Match]] = []

    def take(pattern: str, kind: str):
        for match in re.finditer(pattern, text):
            if any(occupied[match.start() : match.end()]):
                continue
            for offset in range(match.start(), match.end()):
                occupied[offset] = True
            found.append((match.start(), kind, match))

    take(r"\d+\.\d+\.\d+", "version")
    take(r"(\d+(?:\.\d+)?)e(-?\d+)", "scientific")
    take(r"(\d+)/(\d+)", "fraction")
    take(r"(\d+\.\d+)\s*%", "percent")
    take(r"\d+\.\d+", "decimal")
    take(r"(?<![A-Za-z0-9])\d+(?![A-Za-z])", "integer")
    quantities = []
    for _start, kind, match in sorted(found):
        if kind == "version":
            quantities.append({"kind": kind, "value": match.group(0)})
        elif kind == "scientific":
            quantities.append(
                {
                    "kind": kind,
                    "mantissa": float(match.group(1)),
                    "exp": int(match.group(2)),
                    "decimals": len(match.group(1).split(".")[1]) if "." in match.group(1) else 0,
                }
            )
        elif kind == "fraction":
            quantities.append({"kind": kind, "num": int(match.group(1)), "den": int(match.group(2))})
        elif kind == "percent":
            quantities.append(
                {
                    "kind": kind,
                    "value": float(match.group(1)),
                    "decimals": len(match.group(1).split(".")[1]),
                }
            )
        elif kind == "decimal":
            raw = match.group(0)
            quantities.append({"kind": kind, "value": float(raw), "decimals": len(raw.split(".")[1])})
        else:
            quantities.append({"kind": kind, "value": int(match.group(0))})
    for token in re.findall(r"\\texttt\{([^{}]+)\}", claim):
        token = token.replace("\\_", "_")
        if re.fullmatch(r"[\d.eE+-]+", token) or token.startswith("WP_"):
            quantities.append({"kind": "token", "value": token})
    bracket = re.search(r"\[(\d+(?:\s*,\s*\d+)+)\]", normalize_text(claim))
    if bracket:
        quantities.append(
            {"kind": "list", "value": [int(part) for part in bracket.group(1).split(",")]}
        )
    return quantities


def matches_quantity(quantity: dict, value: float) -> bool:
    kind = quantity["kind"]
    if kind == "percent":
        return round(value * 100, quantity["decimals"]) == quantity["value"]
    if kind == "scientific":
        mantissa = value / (10 ** quantity["exp"])
        return round(mantissa, quantity["decimals"]) == quantity["mantissa"]
    if kind == "decimal":
        return round(value, quantity["decimals"]) == quantity["value"]
    if kind == "integer":
        return float(value).is_integer() and int(round(value)) == quantity["value"] and close(float(value), float(quantity["value"]))
    return False


def fraction_in_text(text: str, num: int, den: int) -> bool:
    flat = normalize_text(text)
    flat = re.sub(r"\s*/\s*", "/", flat)
    return f"{num}/{den}" in flat


def cited_files(source: str, repo: Path, previous: list[Path]) -> list[Path]:
    found: list[Path] = []
    for match in FILE_REF.finditer(source):
        path = repo / match.group(1)
        if path not in found:
            found.append(path)
    for match in re.finditer(r"\b([A-Za-z0-9_.-]+\.json)\b", source):
        name = match.group(1)
        if any(path.name == name for path in found):
            continue
        candidate = repo / "pipeline" / "results" / name
        if candidate.is_file() and candidate not in found:
            found.append(candidate)
    if not found and (
        "those fields" in source
        or "same fields" in source
        or "computed" in source
        or (source.strip().startswith("PROJECTED") and "closed form" not in source)
    ):
        found = [path for path in previous if path.suffix == ".json"] or list(previous)
    return found


def check_numbers(source: str, blobs: list, texts: list[str], anchors: list[float]) -> list[str]:
    errors = []
    position = position_in(source)
    consumed_spans = []

    def covered(match: re.Match) -> bool:
        return any(start <= match.start() and match.end() <= end for start, end in consumed_spans)

    for match in SCOPE_ASSIGN.finditer(source):
        consumed_spans.append((match.start(), match.end()))
        scope, raw, value = match.group(1), match.group(2), float(match.group(2))
        prefix = source[: match.start()]
        prefix = re.sub(rf"(?:\s+(?:hmmscan|hmmsearch|A|B)\s*=\s*{NUMBER})+\s*$", "", prefix)
        field_match = re.search(r"([A-Za-z_][\w.]*)\s*$", prefix)
        field = field_match.group(1) if field_match else ""
        if field in {"fields", "json", "and", "from", "share"} or not field:
            if any(close(value, anchor) for anchor in anchors):
                anchors.append(value)
                continue
            errors.append(f"{scope}={raw} has no field and is not a recomputed value")
            continue
        if value_in(blobs, field, value, {scope}, position, False) or any(close(value, anchor) for anchor in anchors):
            anchors.append(value)
        else:
            errors.append(f"{field} for {scope}={raw} is not in the cited file")

    for match in ASSIGN.finditer(source):
        if covered(match):
            continue
        key, raw, value = match.group(1), match.group(2), float(match.group(2))
        if any(close(value, anchor) for anchor in anchors):
            anchors.append(value)
            continue
        prefix = source[: match.start()]
        scopes = scopes_in(prefix)
        # A path written before the key narrows the object.
        phrases = re.findall(r"[A-Za-z_][\w]*\.[\w:.]+", prefix)
        candidates = [key]
        for phrase in phrases:
            if not key.startswith(phrase):
                candidates.append(f"{phrase}.{key}")
        ok = False
        for candidate in candidates:
            if value_in(blobs, candidate, value, scopes, position, key == "position"):
                ok = True
                break
        if not ok:
            for text in texts:
                window = normalize_text(text)
                shown = str(int(value)) if float(value).is_integer() else raw
                if re.search(rf"{re.escape(key.split('.')[-1])}\s*=\s*{re.escape(shown)}\b", window):
                    ok = True
                    break
                if key.split(".")[-1] in window and re.search(rf"(?<!\d){re.escape(shown)}(?!\d)", window):
                    ok = True
                    break
        if ok:
            anchors.append(value)
        else:
            errors.append(f"{key}={raw} is not in the cited file")

    for match in re.finditer(r"\[(\d+(?:\s*,\s*\d+)+)\]", source):
        want = [int(part) for part in match.group(1).split(",")]
        ok = False
        for blob in blobs:
            for obj in walk(blob):
                if isinstance(obj, dict) and any(value == want for value in obj.values()):
                    ok = True
        if not ok and any(match.group(0).replace(" ", "") in text.replace(" ", "") for text in texts):
            ok = True
        if ok:
            anchors.extend(float(item) for item in want)
        else:
            errors.append(f"list {want} is not in the cited file")

    for match in STRING_ASSIGN.finditer(source):
        key, literal = match.group(1), match.group(2)
        if not literal_in(blobs, texts, key, literal, scopes_in(source[: match.start()])):
            errors.append(f"{key}={literal} is not in the cited file")
    for match in BARE_BOOL.finditer(source):
        key, literal = match.group(1), match.group(2)
        if key in {"and", "is", "are"}:
            continue
        if not literal_in(blobs, texts, key, literal, scopes_in(source[: match.start()])):
            errors.append(f"{key} {literal} is not in the cited file")

    for match in re.finditer(r"\b(\d+\.\d+\.\d+)\b", source):
        version = match.group(1)
        if not any(version in json.dumps(blob) for blob in blobs) and not any(version in text for text in texts):
            errors.append(f"version {version} is not in the cited file")

    if "n_consistent=" in source:
        wanted = [float(item) for item in re.findall(r"n_consistent=(\d+)", source)]
        for blob in blobs:
            for obj in walk(blob):
                if not isinstance(obj, dict) or "n" not in obj or "n_consistent" not in obj:
                    continue
                if any(num_eq(obj["n_consistent"], item) for item in wanted):
                    anchors.append(float(obj["n"]))

    return errors


def literal_in(blobs, texts, key: str, literal: str, scopes: set[str]) -> bool:
    want = literal.strip('"')
    last = key.split(".")[-1]
    if want in {"true", "false"}:
        flag = want == "true"
        for blob in blobs:
            for obj in walk(blob):
                if isinstance(obj, dict) and obj.get(last) is flag and scope_ok(blob, obj, scopes):
                    return True
                got = lookup(obj, key) if isinstance(obj, dict) else None
                if got is flag:
                    return True
        return any(re.search(rf"{re.escape(last)}\s*[:=]?\s*{want}", normalize_text(text)) for text in texts)
    for blob in blobs:
        for got in find_path(blob, key):
            if got == want or (isinstance(got, str) and want in got):
                return True
        for obj in walk(blob):
            if isinstance(obj, dict) and (obj.get(last) == want or (isinstance(obj.get(last), str) and want in obj.get(last))):
                return True
    return any(want in text for text in texts)


def printed_anchors(source: str, blobs: list) -> list[float]:
    values = []
    for match in re.finditer(r"((?:[A-Za-z_][\w]*\.)*(?:part_printed|whole_printed))\b", source):
        for blob in blobs:
            for got in find_path(blob, match.group(1)):
                if isinstance(got, str):
                    try:
                        values.append(float(got))
                    except ValueError:
                        continue
    return values


def string_field_anchors(source: str, blobs: list) -> list[float]:
    """Numbers that live inside a cited string, such as a refusal reason."""
    values = []
    for match in re.finditer(r"([A-Za-z_][\w.]*)", source):
        key = match.group(1)
        if not key.endswith("reason") and key not in {"r2n.reason"}:
            continue
        for blob in blobs:
            for got in find_path(blob, key):
                if isinstance(got, str):
                    values.extend(float(item) for item in re.findall(r"\d+", got))
    return values


def file_list_anchors(source: str, blobs: list) -> list[float]:
    values = []
    if "n_mismatch" not in source:
        return values
    path_match = re.search(r"([A-Za-z_][\w.]*)\.files", source)
    if not path_match:
        return values
    for blob in blobs:
        files = lookup(blob, path_match.group(1) + ".files")
        if not isinstance(files, list):
            continue
        counts = [row.get("n_mismatch") for row in files if isinstance(row, dict)]
        if "all 0" in source and any(item != 0 for item in counts):
            raise ValueError(f"{path_match.group(1)} n_mismatch is {counts}")
        values.extend(float(item) for item in counts if isinstance(item, (int, float)))
    return values


def same_object_probe(source: str, blobs: list) -> list[str]:
    if "probe.P_s" not in source or "[" not in source:
        return []
    want_p = float(re.search(rf"P_s\s*=\s*({NUMBER})", source).group(1))
    want_sizes = [int(part) for part in re.search(r"\[(\d+(?:\s*,\s*\d+)+)\]", source).group(1).split(",")]
    for blob in blobs:
        for obj in walk(blob):
            if isinstance(obj, dict) and num_eq(obj.get("P_s"), want_p) and obj.get("sizes") == want_sizes:
                return []
    return [f"no probe object has P_s={want_p} and sizes {want_sizes}"]


def prose_tokens(claim: str, blobs: list, texts: list[str], files: list[Path]) -> list[str]:
    errors = []
    if re.search(r"\d", claim):
        return errors
    tokens = [token.replace("\\_", "_") for token in re.findall(r"\\texttt\{([^{}]+)\}", claim)]
    words = re.findall(r"\b(entry_count|total_entry_length|per_key_row_count|REFUSE|SHIP|STOP_MATCH)\b", claim)
    blob_text = "\n".join(json.dumps(blob) for blob in blobs)
    cited = "\n".join(str(path) for path in files)
    for token in tokens + words:
        if token in blob_text or any(token in text for text in texts) or token.strip("/") in cited:
            continue
        errors.append(f"{token} is not in the cited file")
    return errors


def quantity_ok(quantity: dict, anchors: list[float], blobs: list, texts: list[str], source: str) -> bool:
    kind = quantity["kind"]
    if kind == "token":
        blob_text = "\n".join(json.dumps(blob) for blob in blobs)
        return quantity["value"] in blob_text or any(quantity["value"] in text for text in texts)
    if kind == "version":
        blob_text = "\n".join(json.dumps(blob) for blob in blobs)
        return quantity["value"] in blob_text or any(quantity["value"] in text for text in texts)
    if kind == "list":
        rendered = "[" + ",".join(str(item) for item in quantity["value"]) + "]"
        if any(rendered in text.replace(" ", "") for text in texts):
            return True
        return any(
            isinstance(obj, dict) and any(value == quantity["value"] for value in obj.values())
            for blob in blobs
            for obj in walk(blob)
        )
    if kind == "fraction":
        if any(fraction_in_text(text, quantity["num"], quantity["den"]) for text in texts):
            return True
        def side(number: int) -> bool:
            if any(matches_quantity({"kind": "integer", "value": number}, value) for value in anchors):
                return True
            return any(has_exact_number(blob, float(number)) for blob in blobs)

        return side(quantity["num"]) and side(quantity["den"])
    if any(matches_quantity(quantity, value) for value in anchors):
        return True
    if kind == "integer":
        shown = str(quantity["value"])
        if re.search(rf"(?<!\d){shown}(?!\d)", source):
            return True
        if quantity["value"] >= 10 and any(
            re.search(rf"(?<!\d){shown}(?!\d)", normalize_text(text)) for text in texts
        ):
            return True
        if any(has_exact_number(blob, float(quantity["value"])) for blob in blobs) and not anchors:
            return True
        return False
    if kind in {"decimal", "percent", "scientific"}:
        return any(quantity_in_text(text, quantity) for text in texts)
    return False


def quantity_in_text(text: str, quantity: dict) -> bool:
    flat = normalize_text(text)
    if quantity["kind"] == "decimal":
        return re.search(rf"(?<!\d){re.escape(str(quantity['value']))}(?!\d)", flat) is not None
    if quantity["kind"] == "percent":
        return f"{quantity['value']}%" in flat.replace(" ", "")
    return False


def has_exact_number(node, value: float) -> bool:
    if isinstance(node, bool):
        return False
    if isinstance(node, (int, float)):
        return close(float(node), value)
    if isinstance(node, str):
        try:
            return close(float(node), value)
        except ValueError:
            return False
    if isinstance(node, dict):
        return any(has_exact_number(item, value) for item in node.values())
    if isinstance(node, list):
        return any(has_exact_number(item, value) for item in node)
    return False


def unresolved_source_floats(source: str, anchors: list[float], blobs: list) -> list[str]:
    errors = []
    masked = ASSIGN.sub(" ", source)
    masked = SCOPE_ASSIGN.sub(" ", masked)
    for match in re.finditer(rf"(?<![\w.])({NUMBER})", masked):
        raw = match.group(1)
        if "." not in raw and "e" not in raw.lower():
            continue
        if len(raw.split(".")[-1]) < 5 and "e" not in raw.lower():
            continue
        value = float(raw)
        if any(close(value, anchor) for anchor in anchors):
            continue
        if any(has_exact_number(blob, value) for blob in blobs):
            anchors.append(value)
            continue
        errors.append(f"source number {raw} is not in the cited file and does not match a recomputed value")
    return errors


def audit(lines: list[str], index: int, repo: Path, previous: list[Path]) -> tuple[list[str], list[Path]]:
    source = lines[index].split("% source:", 1)[1].strip()
    claim = claim_text(lines, index)
    files = cited_files(source, repo, previous)
    formula_only = "closed form" in source or bool(re.search(r"\(1-0?\.01\)\^", source))
    if not files and not formula_only:
        return ["no committed file is cited"], previous
    missing = [str(path.relative_to(repo)) for path in files if not path.is_file()]
    if missing:
        return [f"missing {', '.join(missing)}"], files or previous

    blobs = []
    texts = []
    for path in files:
        if path.suffix == ".json":
            blobs.append(load_json(path))
        else:
            texts.append(path.read_text())

    errors: list[str] = []
    anchors: list[float] = []
    try:
        anchors.extend(formulas(source, repo))
    except ValueError as exc:
        errors.append(str(exc))
    try:
        anchors.extend(curve_anchors(source, blobs))
    except ValueError as exc:
        errors.append(str(exc))
    if "six genomes in each" in source and texts:
        try:
            anchors.extend(fit_error_anchors(texts[0]))
        except ValueError as exc:
            errors.append(str(exc))
    try:
        anchors.extend(file_list_anchors(source, blobs))
    except ValueError as exc:
        errors.append(str(exc))
    anchors.extend(string_field_anchors(source, blobs))
    anchors.extend(printed_anchors(source, blobs))
    if re.search(r"k\s*=\s*2\b", normalize_text(claim)) and any(re.search(r"k\s*=\s*2\b", text) for text in texts):
        anchors.append(2.0)
    record = re.search(r"record_key=(\S+)", source)
    if record:
        token = record.group(1).rstrip(".,;")
        blob_text = "\n".join(json.dumps(blob) for blob in blobs)
        if token not in blob_text:
            errors.append(f"record_key {token} is not in the cited file")
    errors.extend(check_numbers(source, blobs, texts, anchors))
    errors.extend(same_object_probe(source, blobs))
    errors.extend(unresolved_source_floats(source, anchors, blobs))

    if "Fisher" in source:
        if not any("[0, 3, 2, 1]" in text for text in texts):
            errors.append("Fisher-Yates guard [0, 3, 2, 1] is not in the cited file")
        else:
            anchors.extend([0, 3, 2, 1])
    if "group-testing" in source:
        if not any("1+2+4+8" in text for text in texts):
            errors.append("group-testing schedule 1+2+4+8 is not in the cited file")
        else:
            anchors.extend([1, 2, 4, 8])
    if texts:
        joined = "\n".join(texts)
        for job in re.findall(r"\b\d{7,}\b", source):
            if job not in joined:
                errors.append(f"job {job} is not in the cited file")
        if "STOP_MATCH" in source and "STOP_MATCH" not in joined:
            errors.append("STOP_MATCH is not in the cited file")
    for fraction in re.finditer(r"(\d+)\s*/\s*(\d+)", source):
        num, den = int(fraction.group(1)), int(fraction.group(2))
        anchors.extend([float(num), float(den)])
        if texts and not any(fraction_in_text(text, num, den) for text in texts) and "0/56" not in source:
            errors.append(f"fraction {num}/{den} is not in the cited file")

    # Path-only citations such as host.slurm_job_id and :z_new.
    for path_text in re.findall(r"(?:pipeline/\S+|:[A-Za-z_][\w.]*)", source):
        rest = source.split(path_text, 1)[1].lstrip(" :")
        dotted = re.match(r"([A-Za-z_][\w.]*)", rest)
        target = dotted.group(1) if dotted else path_text.lstrip(":")
        if "=" in source[source.find(target) : source.find(target) + len(target) + 8] if target in source else "":
            continue
        for blob in blobs:
            for got in find_path(blob, target):
                if num_eq(got, float(got) if isinstance(got, (int, float)) and not isinstance(got, bool) else -1):
                    anchors.append(float(got))
                elif isinstance(got, str) and got.isdigit():
                    anchors.append(float(got))

    for quantity in claim_quantities(claim):
        if quantity_ok(quantity, anchors, blobs, texts, source):
            continue
        errors.append(f"claim {quantity} does not match the cited file")
    errors.extend(prose_tokens(claim, blobs, texts, files))
    return errors, files or previous


def main() -> int:
    lines = PAPER.read_text().splitlines()
    comments = [index for index, line in enumerate(lines) if "% source:" in line]
    failures = 0
    previous: list[Path] = []
    for index in comments:
        problems, previous = audit(lines, index, REPO, previous)
        if problems:
            failures += 1
            print(f"FAIL L{index + 1}: " + "; ".join(problems))
    print(f"source_comments={len(comments)} mismatches={failures}")
    if len(comments) < 180:
        print("FAIL fewer source comments than main.tex is expected to carry")
        return 1
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL checker crashed: {exc}", file=sys.stderr)
        raise
