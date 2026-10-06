"""Content hash of one reference entry after volatile lines are dropped.

The tag list is format data supplied by the caller. This module does not
know which tags a format uses.
"""

from __future__ import annotations

import hashlib


def _first_token(line: str) -> str:
    stripped = line.lstrip()
    if not stripped:
        return ""
    return stripped.split(None, 1)[0]


def drop_volatile_lines(text: str, tags: tuple[str, ...]) -> str:
    """Drop lines whose first whitespace-delimited token is in `tags`.

    Remaining lines stay in order, newlines included. An empty tag list
    returns `text` unchanged.
    """
    if not tags:
        return text
    banned = set(tags)
    kept: list[str] = []
    for line in text.splitlines(keepends=True):
        if _first_token(line) in banned:
            continue
        kept.append(line)
    return "".join(kept)


def entry_content_hash(text: str, tags: tuple[str, ...]) -> str:
    """SHA-256 hex of the entry with volatile lines removed."""
    return hashlib.sha256(drop_volatile_lines(text, tags).encode()).hexdigest()
