"""Per-format reference entry parsers.

Length and the volatile-tag list are data sitting next to the parser.
The fitter reads those fields; it does not compute a length itself.
"""

from __future__ import annotations

import gzip
import re
from dataclasses import dataclass
from pathlib import Path

from acts.entry_hash import entry_content_hash
from acts.fasta import parse_fasta

# One profile grammar's header. Callers and tests still name this token.
# Detection accepts any magic of the same shape, so a second block format
# is not a second parser.
PROFILE_MAGIC = "HMMER3/f"
_PROFILE_MAGIC_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*\/[A-Za-z0-9.]+$")

# Integer length tag, first match wins. LENG stays ahead of any other tag
# so an existing profile's length does not move.
_LENGTH_TAGS = ("LENG", "CLEN")

# Lines whose first token is here cannot change a score-thresholded scan.
PROFILE_VOLATILE_TAGS = ("DATE", "BM", "SM", "COM")

ENTRYLINE = "entryline"
FASTA = "fasta"
PROFILE = "profile_text"
# Bucher & Bairoch, ISMB 1994. ID/AC header, MA or PA body, // terminator.
GENERALIZED_PROFILE = "generalized_profile"

# Line codes that do not change a score. The matrix (MA) and the pattern
# (PA) stay. Dates, prose, cross-references, documentation pointers, and
# per-release match counts (NR) do not.
GENERALIZED_VOLATILE_TAGS = ("DT", "DE", "CC", "DR", "NR", "3D", "PR", "DO")

_ID_LINE = re.compile(r"^ID\s+(\S+?);\s*(MATRIX|PATTERN)\.")
_AC_LINE = re.compile(r"^AC\s+([^;\s]+)")
_MATCH_MARK = re.compile(r"/M:")


class FormatError(ValueError):
    """The bytes are not a reference this parser will accept."""


@dataclass(frozen=True)
class Entry:
    """One reference entry, in file order."""

    raw: str
    length: int
    content_hash: str
    keys: tuple[str, ...]
    format_name: str

    @property
    def primary(self) -> str:
        return self.keys[0]


@dataclass(frozen=True)
class RecordItem:
    """One record from the record input. `key` is the identifier tools echo."""

    key: str
    name: str
    description: str
    sequence: str


def read_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    if data.startswith(b"\x1f\x8b"):
        return gzip.decompress(data)
    return data


def read_text(path: Path) -> str:
    return read_bytes(path).decode()


def _is_profile_magic(token: str) -> bool:
    return _PROFILE_MAGIC_RE.fullmatch(token) is not None


def _tag_value(text: str, tag: str) -> str | None:
    for line in text.splitlines():
        parts = line.split()
        if parts and parts[0] == tag and len(parts) > 1:
            return parts[1]
    return None


def _first_block(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines(keepends=True):
        lines.append(line)
        if line.startswith("//"):
            break
    return "".join(lines)


def _profile_entry(raw: str) -> Entry:
    # Length belongs to the model block. A following filter block can carry
    # its own length tag and must not replace the model's.
    length_token = None
    head = _first_block(raw)
    for tag in _LENGTH_TAGS:
        length_token = _tag_value(head, tag)
        if length_token is not None:
            break
    if length_token is None:
        raise FormatError("profile entry has no length tag")
    try:
        length = int(length_token)
    except ValueError as exc:
        raise FormatError(f"profile length is not an integer: {length_token}") from exc
    name = _tag_value(raw, "NAME")
    acc = _tag_value(raw, "ACC")
    keys: list[str] = []
    for token in (name, acc):
        if token and token not in keys:
            keys.append(token)
    if acc and "." in acc:
        bare = acc.split(".", 1)[0]
        if bare and bare not in keys:
            keys.append(bare)
    if not keys:
        raise FormatError("profile entry has no NAME or ACC")
    return Entry(
        raw=raw if raw.endswith("\n") else raw + "\n",
        length=length,
        content_hash=entry_content_hash(raw if raw.endswith("\n") else raw + "\n", PROFILE_VOLATILE_TAGS),
        keys=tuple(keys),
        format_name=PROFILE,
    )


def _is_gzip(path: Path) -> bool:
    if path.name.endswith(".gz"):
        return True
    with path.open("rb") as handle:
        return handle.read(2) == b"\x1f\x8b"


def _block_magic(raw: str) -> str:
    return raw.lstrip().split(None, 1)[0]


def _same_record(left: str, right: str) -> bool:
    """Adjacent blocks with the same keys and different magics are one entry.

    A model file may store a second block (a filter) under the same name.
    Two blocks with the same magic stay separate, and a repeated key then
    fails in ``alias_map``.
    """
    keys = tuple(token for token in (_tag_value(left, "NAME"), _tag_value(left, "ACC")) if token)
    other = tuple(token for token in (_tag_value(right, "NAME"), _tag_value(right, "ACC")) if token)
    return bool(keys) and keys == other and _block_magic(left) != _block_magic(right)


def _iter_profile_blocks(lines):
    buf: list[str] = []
    started = False
    for line in lines:
        if not started:
            if not line.strip():
                continue
            if not _is_profile_magic(line.split(None, 1)[0]):
                raise FormatError("not profile text")
            started = True
        buf.append(line if line.endswith("\n") else line + "\n")
        if line.startswith("//"):
            yield "".join(buf)
            buf = []
            started = False
    if "".join(buf).strip():
        raise FormatError("truncated profile entry")


def _iter_profile_entries(lines):
    pending: str | None = None
    for block in _iter_profile_blocks(lines):
        if pending is None:
            pending = block
            continue
        if _same_record(pending, block):
            yield pending + block
            pending = None
            continue
        yield pending
        pending = block
    if pending is not None:
        yield pending


def iter_profile_raw(path: Path):
    """Yield each profile entry's raw text, one entry at a time.

    The yielded text includes the ``//`` line and ends with a newline, matching
    the raw stored by ``parse_profile_text``. The file is not held in memory.
    Adjacent blocks that are the same record are one yield.
    """
    opener = gzip.open if _is_gzip(path) else open
    with opener(path, "rt") as handle:
        yield from _iter_profile_entries(handle)


def parse_profile_text(text: str) -> list[Entry]:
    entries = [_profile_entry(raw) for raw in _iter_profile_entries(text.splitlines(keepends=True))]
    if not entries:
        raise FormatError("profile text contained no entries")
    return entries


def _fasta_raw_records(text: str) -> list[str]:
    chunks: list[list[str]] = []
    for line in text.splitlines(keepends=True):
        if line.startswith(">"):
            chunks.append([line])
        elif chunks:
            chunks[-1].append(line)
    if not chunks:
        raise FormatError("not fasta")
    return ["".join(chunk) for chunk in chunks]


def parse_fasta_entries(text: str) -> list[Entry]:
    raws = _fasta_raw_records(text)
    recs = parse_fasta(text)
    if len(recs) != len(raws):
        raise FormatError("fasta record count mismatch")
    entries: list[Entry] = []
    for raw, rec in zip(raws, recs):
        body = raw.split("\n", 1)[1] if "\n" in raw else ""
        length = sum(1 for ch in body if not ch.isspace())
        stored = raw if raw.endswith("\n") else raw + "\n"
        entries.append(
            Entry(
                raw=stored,
                length=length,
                content_hash=entry_content_hash(stored, ()),
                keys=(rec.name,),
                format_name=FASTA,
            )
        )
    return entries


def parse_entryline(text: str) -> list[Entry]:
    entries: list[Entry] = []
    saw = False
    for line in text.splitlines():
        if not line.strip():
            continue
        saw = True
        parts = line.split()
        if len(parts) != 2 or not parts[1].isdigit():
            raise FormatError("not entryline")
        ident, length_s = parts
        raw = f"{ident} {length_s}\n"
        entries.append(
            Entry(
                raw=raw,
                length=int(length_s),
                content_hash=entry_content_hash(raw, ()),
                keys=(ident,),
                format_name=ENTRYLINE,
            )
        )
    if not saw:
        raise FormatError("empty entryline")
    return entries


def _looks_like_generalized_profile(text: str) -> bool:
    """True when an ID entry and a // terminator both occur.

    A release file may open with comment lines (CC) or a starred banner
    before the first ID. Those lines are not a different format.
    """
    saw_id = False
    saw_end = False
    for line in text.splitlines():
        if _ID_LINE.match(line):
            saw_id = True
        if line.strip() == "//":
            saw_end = True
        if saw_id and saw_end:
            return True
    return False


def _slash_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    buf: list[str] = []
    for line in text.splitlines(keepends=True):
        buf.append(line if line.endswith("\n") else line + "\n")
        if line.strip() == "//":
            blocks.append("".join(buf))
            buf = []
    if "".join(buf).strip():
        raise FormatError("truncated generalized-profile entry")
    return blocks


def _pattern_length(raw: str) -> int:
    body: list[str] = []
    for line in raw.splitlines():
        if line.startswith("PA") and line[2:3].isspace():
            parts = line.split(None, 1)
            if len(parts) == 2:
                body.append(parts[1])
    return sum(1 for ch in "".join(body) if not ch.isspace()) or 1


def _generalized_entry(raw: str) -> Entry | None:
    name = None
    accession = None
    for line in raw.splitlines():
        if name is None:
            matched = _ID_LINE.match(line)
            if matched:
                name = matched.group(1)
        if accession is None:
            matched = _AC_LINE.match(line)
            if matched:
                accession = matched.group(1)
    if name is None:
        return None
    if not accession:
        raise FormatError("generalized-profile entry has no AC")
    n_match = len(_MATCH_MARK.findall(raw))
    length = n_match if n_match else _pattern_length(raw)
    joined = f"{accession}|{name}"
    keys: list[str] = []
    for token in (joined, accession, name):
        if token not in keys:
            keys.append(token)
    stored = raw if raw.endswith("\n") else raw + "\n"
    return Entry(
        raw=stored,
        length=length,
        content_hash=entry_content_hash(stored, GENERALIZED_VOLATILE_TAGS),
        keys=tuple(keys),
        format_name=GENERALIZED_PROFILE,
    )


def parse_generalized_profile(text: str) -> list[Entry]:
    """Entries of a generalized-profile library, in file order.

    A leading block with no ID line is a banner and is not an entry.
    The primary key is ``accession|name``. That is the one field the
    format's tabular export uses to name the entry, and replay selects
    entries by the primary key.
    Length is the number of ``/M:`` match positions. A pattern entry,
    which has none, uses the number of non-space characters on its PA
    lines.
    """
    if not _looks_like_generalized_profile(text):
        raise FormatError("not generalized-profile text")
    entries: list[Entry] = []
    for raw in _slash_blocks(text):
        entry = _generalized_entry(raw)
        if entry is not None:
            entries.append(entry)
    if not entries:
        raise FormatError("generalized-profile text contained no entries")
    return entries


def parse_reference_text(text: str) -> list[Entry]:
    """Detect one reference format and return its entries in file order."""
    stripped = text.lstrip()
    if not stripped:
        raise FormatError("empty reference")
    first = stripped.splitlines()[0]
    first_token = first.split(None, 1)[0]
    if _is_profile_magic(first_token):
        return parse_profile_text(text)
    if stripped.startswith(">"):
        return parse_fasta_entries(text)
    if _looks_like_generalized_profile(text):
        return parse_generalized_profile(text)
    try:
        return parse_entryline(text)
    except FormatError:
        raise FormatError("reference format has no parser") from None


def parse_reference(path: Path) -> list[Entry]:
    try:
        return parse_reference_text(read_text(path))
    except FormatError:
        raise
    except OSError as exc:
        raise FormatError(str(exc)) from exc


def parses_as_entries(path: Path) -> bool:
    try:
        parse_reference(path)
    except (FormatError, UnicodeError, OSError):
        return False
    return True


def write_entries(entries: list[Entry], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(entry.raw for entry in entries))
    return path


def read_records(path: Path) -> list[RecordItem]:
    """Record input. FASTA yields one item per record; anything else is one id per line."""
    text = read_text(path)
    if text.lstrip().startswith(">"):
        return [
            RecordItem(key=rec.name, name=rec.name, description=rec.description, sequence=rec.seq)
            for rec in parse_fasta(text)
        ]
    items: list[RecordItem] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split(None, 1)
        items.append(
            RecordItem(key=parts[0], name=parts[0], description=parts[1] if len(parts) > 1 else "", sequence="")
        )
    return items


def length_weighted_churn(old: list[Entry], new: list[Entry]) -> dict:
    """Share of the new release's length that is not an unchanged entry.

    An entry is unchanged when its content hash occurs in the old release.
    ``c_length = (L_new - L_unchanged) / L_new``. Hash identity is the same
    one the reuse path uses, so this fraction is the length weight of the
    entries that path must scan.
    """
    if not new:
        raise FormatError("new reference has no entries")
    return length_weighted_churn_hashes(
        {entry.content_hash for entry in old},
        new,
        n_old=len(old),
    )


def length_weighted_churn_hashes(old_hashes: set[str], new: list[Entry], *, n_old: int) -> dict:
    length_new = 0
    length_unchanged = 0
    n_unchanged = 0
    for entry in new:
        length_new += entry.length
        if entry.content_hash in old_hashes:
            length_unchanged += entry.length
            n_unchanged += 1
    if length_new <= 0:
        raise FormatError("new reference has no length")
    changed = length_new - length_unchanged
    return {
        "n_old": n_old,
        "n_new": len(new),
        "n_unchanged_hash": n_unchanged,
        "n_changed_and_new": len(new) - n_unchanged,
        "length_new": length_new,
        "length_unchanged": length_unchanged,
        "length_changed_and_new": changed,
        "c_length": changed / length_new,
    }


def alias_map(entries: list[Entry]) -> dict[str, int]:
    """Map an output token to an entry index. Ambiguous aliases are an error."""
    out: dict[str, int] = {}
    for index, entry in enumerate(entries):
        for token in entry.keys:
            if token in out and out[token] != index:
                raise FormatError(f"entry alias {token!r} is not unique")
            out[token] = index
    return out
