"""YAML-list reference format (opt-in).

A document whose top level is a mapping with exactly one list-valued key.
Each list item is one Entry; raw bytes are sliced from the original file
(never re-dumped). Selected only via ``--reference-format yaml-list``.
Auto-detection never returns this format.
"""

from __future__ import annotations

import re
from pathlib import Path

from acts.entry_hash import entry_content_hash
from acts.reference_formats import Entry, FormatError

YAML_LIST = "yaml-list"

_LIST_ITEM_START = re.compile(r"^( *)- ")


def _yaml():
    """Inline import so the default TARE path never loads PyYAML (G-d)."""
    import yaml  # type: ignore

    return yaml


def _reject_multi_document(text: str) -> None:
    """Semgrep rejects multi-document YAML; so do we."""
    body = text
    if body.startswith("---"):
        rest = body[3:]
        if rest.startswith("\n") or rest.startswith("\r") or rest == "":
            body = rest.lstrip("\r\n")
    if re.search(r"(?m)^\s*---\s*$", body):
        raise FormatError("yaml-list rejects multi-document YAML")


def _top_list_key(data: dict) -> str:
    if not isinstance(data, dict) or len(data) != 1:
        raise FormatError("yaml-list top level must be a mapping with only the list key")
    key = next(iter(data))
    if not isinstance(data[key], list):
        raise FormatError("yaml-list top-level value must be a list")
    return key


def _find_list_key_line(stripped_lines: list[str], key: str) -> int:
    prefix = f"{key}:"
    for index, line in enumerate(stripped_lines):
        if line[:1].isspace():
            continue
        if line == prefix or line.startswith(prefix + " ") or line.startswith(prefix + "\t"):
            return index
    raise FormatError(f"yaml-list header key {key!r} not found in text")


def _first_item_index(stripped_lines: list[str], start: int) -> tuple[int, int]:
    for index in range(start + 1, len(stripped_lines)):
        line = stripped_lines[index]
        if not line.strip():
            continue
        matched = _LIST_ITEM_START.match(line)
        if matched:
            return index, len(matched.group(1))
        raise FormatError("yaml-list: content before the first list item is not a list item")
    raise FormatError("yaml-list: list is empty")


def _split_items(stripped_lines: list[str], first: int, item_indent: int) -> list[tuple[int, int]]:
    """Half-open line spans [start, end) for each top-level list item."""
    spans: list[tuple[int, int]] = []
    start = first
    for index in range(first + 1, len(stripped_lines)):
        matched = _LIST_ITEM_START.match(stripped_lines[index])
        if matched and len(matched.group(1)) == item_indent:
            spans.append((start, index))
            start = index
    spans.append((start, len(stripped_lines)))
    return spans


def _item_key(raw: str, key_field: str) -> str:
    yaml = _yaml()
    try:
        loaded = yaml.safe_load(raw)
    except yaml.YAMLError as exc:  # type: ignore[attr-defined]
        raise FormatError(f"yaml-list item is not valid YAML: {exc}") from exc
    if isinstance(loaded, list):
        if len(loaded) != 1 or not isinstance(loaded[0], dict):
            raise FormatError("yaml-list item did not parse as a single mapping")
        mapping = loaded[0]
    elif isinstance(loaded, dict):
        mapping = loaded
    else:
        raise FormatError("yaml-list item did not parse as a mapping")
    if key_field not in mapping:
        raise FormatError(f"yaml-list item missing key field {key_field!r}")
    value = mapping[key_field]
    if not isinstance(value, str) or not value:
        raise FormatError(f"yaml-list key field {key_field!r} must be a non-empty string")
    return value


def parse_yaml_list_text(text: str, *, key_field: str = "id") -> list[Entry]:
    """Parse a yaml-list document into Entries, preserving each item's raw bytes."""
    if not text:
        raise FormatError("empty yaml-list")
    _reject_multi_document(text)
    yaml = _yaml()
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:  # type: ignore[attr-defined]
        raise FormatError(f"yaml-list is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise FormatError("yaml-list top level must be a mapping")
    list_key = _top_list_key(data)
    if not data[list_key]:
        raise FormatError("yaml-list is empty")

    lines = text.splitlines(keepends=True)
    if not lines:
        raise FormatError("empty yaml-list")
    stripped = [ln.rstrip("\n\r") for ln in lines]
    key_line = _find_list_key_line(stripped, list_key)
    first, item_indent = _first_item_index(stripped, key_line)
    spans = _split_items(stripped, first, item_indent)

    header = "".join(lines[:first])
    entries: list[Entry] = []
    seen: set[str] = set()
    for start, end in spans:
        raw = "".join(lines[start:end])
        ident = _item_key(raw, key_field)
        if ident in seen:
            raise FormatError(f"yaml-list duplicate id {ident!r}")
        seen.add(ident)
        entries.append(
            Entry(
                raw=raw,
                length=len(raw.encode()),
                content_hash=entry_content_hash(raw, ()),
                keys=(ident,),
                format_name=YAML_LIST,
                document_header=header,
            )
        )

    rebuilt = header + "".join(entry.raw for entry in entries)
    if rebuilt != text:
        raise FormatError("yaml-list byte round-trip failed on parse")
    return entries


def parse_yaml_list(path: Path, *, key_field: str = "id") -> list[Entry]:
    return parse_yaml_list_text(path.read_text(), key_field=key_field)


def write_yaml_list(entries: list[Entry], path: Path) -> Path:
    """Write header once, then selected items' raw bytes in the given order."""
    if not entries:
        raise FormatError("yaml-list write needs at least one entry")
    if any(entry.format_name != YAML_LIST for entry in entries):
        raise FormatError("yaml-list write got a non-yaml-list entry")
    header = entries[0].document_header
    if header is None:
        raise FormatError("yaml-list entry missing document_header")
    if any(entry.document_header != header for entry in entries):
        raise FormatError("yaml-list entries do not share one document_header")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "".join(entry.raw for entry in entries))
    return path


def concat_yaml_list_files(
    paths: list[Path],
    *,
    key_field: str = "id",
    on_duplicate: str = "error",
) -> tuple[str, int]:
    """Build one yaml-list document from many files (test helper).

    Items are re-indented to column-0 list style so mixed source indents stay
    one flat list. The returned text round-trips through parse/write.

    ``on_duplicate`` is ``error`` (default) or ``skip``. Semgrep's public
    python rules reuse bare ids across packages; skip keeps the first.
    Returns ``(text, n_skipped)``.
    """
    chunks: list[str] = []
    seen: set[str] = set()
    skipped = 0
    for path in paths:
        for entry in parse_yaml_list(path, key_field=key_field):
            if entry.primary in seen:
                if on_duplicate == "skip":
                    skipped += 1
                    continue
                raise FormatError(f"concat duplicate id {entry.primary!r}")
            seen.add(entry.primary)
            chunk = _dedent_item(entry.raw)
            if not chunk.endswith("\n"):
                chunk += "\n"
            chunks.append(chunk)
    return "rules:\n" + "".join(chunks), skipped


def _dedent_item(raw: str) -> str:
    """Shift a list item so its ``- `` marker starts at column 0."""
    lines = raw.splitlines(keepends=True)
    if not lines:
        return raw
    matched = _LIST_ITEM_START.match(lines[0].rstrip("\n\r"))
    if not matched:
        raise FormatError("yaml-list item does not start with a list marker")
    indent = len(matched.group(1))
    if indent == 0:
        return raw
    out: list[str] = []
    for line in lines:
        if not line.strip():
            out.append(line)
            continue
        if line.startswith(" " * indent):
            out.append(line[indent:])
        else:
            raise FormatError("yaml-list item line indent is inconsistent")
    return "".join(out)
