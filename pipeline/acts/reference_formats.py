"""Per-format reference entry parsers.

Length and the volatile-tag list are data sitting next to the parser.
The fitter reads those fields; it does not compute a length itself.
"""

from __future__ import annotations

import gzip
from dataclasses import dataclass
from pathlib import Path

from acts.entry_hash import entry_content_hash
from acts.fasta import parse_fasta

# File-format header token. It names the on-disk grammar, not a program.
PROFILE_MAGIC = "HMMER3/f"

# Lines whose first token is here cannot change a score-thresholded scan.
PROFILE_VOLATILE_TAGS = ("DATE", "BM", "SM", "COM")

ENTRYLINE = "entryline"
FASTA = "fasta"
PROFILE = "profile_text"


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


def _tag_value(text: str, tag: str) -> str | None:
    for line in text.splitlines():
        parts = line.split()
        if parts and parts[0] == tag and len(parts) > 1:
            return parts[1]
    return None


def _profile_entry(raw: str) -> Entry:
    length_token = _tag_value(raw, "LENG")
    if length_token is None:
        raise FormatError("profile entry has no LENG line")
    try:
        length = int(length_token)
    except ValueError as exc:
        raise FormatError(f"profile LENG is not an integer: {length_token}") from exc
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


def iter_profile_raw(path: Path):
    """Yield each profile entry's raw text, one entry at a time.

    The yielded text includes the ``//`` line and ends with a newline, matching
    the raw stored by ``parse_profile_text``. The file is not held in memory.
    """
    opener = gzip.open if _is_gzip(path) else open
    with opener(path, "rt") as handle:
        buf: list[str] = []
        started = False
        for line in handle:
            if not started:
                if not line.strip():
                    continue
                if line.split(None, 1)[0] != PROFILE_MAGIC:
                    raise FormatError("not profile text")
                started = True
            buf.append(line if line.endswith("\n") else line + "\n")
            if line.startswith("//"):
                yield "".join(buf)
                buf = []
                started = False
        if "".join(buf).strip():
            raise FormatError("truncated profile entry")


def parse_profile_text(text: str) -> list[Entry]:
    entries: list[Entry] = []
    buf: list[str] = []
    started = False
    for line in text.splitlines(keepends=True):
        if not started:
            if not line.strip():
                continue
            if line.split(None, 1)[0] != PROFILE_MAGIC:
                raise FormatError("not profile text")
            started = True
        buf.append(line)
        if line.startswith("//"):
            entries.append(_profile_entry("".join(buf)))
            buf = []
            started = False
    leftover = "".join(buf).strip()
    if leftover:
        raise FormatError("truncated profile entry")
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


def parse_reference_text(text: str) -> list[Entry]:
    """Detect one reference format and return its entries in file order."""
    stripped = text.lstrip()
    if not stripped:
        raise FormatError("empty reference")
    first = stripped.splitlines()[0]
    first_token = first.split(None, 1)[0]
    if first_token == PROFILE_MAGIC:
        return parse_profile_text(text)
    if stripped.startswith(">"):
        return parse_fasta_entries(text)
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
