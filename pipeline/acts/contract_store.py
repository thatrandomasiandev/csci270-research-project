"""Opt-in shared contract store across genomes.

Keyed by program-binary digest, normalized argv (same ingredients as the
reference cache namespace), and the reference release content hash. Stores only
genome-independent fit facts. Callers must confirm before trusting a hit.
Atomic publish: write ``*.tmp`` then ``os.replace``.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from acts.reference_cache import argv_namespace, program_binary

STORE_VERSION = 1
# Smallest n with observed self-consistency on all 5 P2 genomes and poison catch.
# Evidence: pipeline/results/shared_contract/p2b_confirm_n.json (P2b).
CONFIRM_N = 25


def release_content_hash(reference: Path) -> str:
    """SHA-256 of the reference file bytes (the release identity)."""
    h = hashlib.sha256()
    with reference.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _drop_flag_values(argv: list[str], flags: tuple[str, ...]) -> list[str]:
    """Keep the flags, drop the following path. Same rule as reference_run."""
    skip = set(flags)
    out: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token in skip and index + 1 < len(argv):
            out.append(token)
            index += 2
            continue
        out.append(token)
        index += 1
    return out


def contract_key(
    argv: list[str],
    reference: Path,
    *,
    baseline: str | None = None,
    pin: str | None = None,
    slack: str | None = None,
    subset_aux: str | None = None,
    group_rule: str | None = None,
    strip_flags: tuple[str, ...] = (),
) -> dict[str, str]:
    """Stable key parts for one shared-contract entry.

    Uses ``argv_namespace`` (binary digest + argv with reference path removed +
    baseline) plus pin/slack/aux/group, then the release content hash so two
    releases never collide even when paths strip to the same argv blob.
    """
    hashed = list(argv)
    if strip_flags and group_rule:
        hashed = _drop_flag_values(hashed, strip_flags)
    argv_ns = argv_namespace(hashed, reference, baseline)
    extra = argv_ns + "\0pin:" + (pin or "") + "\0slack:" + (slack or "")
    if subset_aux:
        extra += "\0subset_aux:" + subset_aux
    if group_rule:
        extra += "\0group:" + group_rule
    argv_digest = hashlib.sha256(extra.encode()).hexdigest()
    binary = program_binary(argv)
    release = release_content_hash(reference)
    key = hashlib.sha256(
        f"{binary['digest']}\0{argv_digest}\0{release}".encode()
    ).hexdigest()
    return {
        "key": key,
        "binary_digest": binary["digest"],
        "argv_digest": argv_digest,
        "release_hash": release,
    }


def shareable_payload(stored: dict) -> dict:
    """Drop per-genome / soundness-risk runtime fields before publishing."""
    out = {
        "decision": stored.get("decision"),
        "reason": stored.get("reason"),
        "used_tie_break": stored.get("used_tie_break"),
        "primary_key_equal": stored.get("primary_key_equal"),
        "probe_invocations": stored.get("probe_invocations"),
        "column_only_refusal": stored.get("column_only_refusal"),
        "exact_eligible": stored.get("exact_eligible"),
        "tables": stored.get("tables") or [],
    }
    if "slack_factor" in stored:
        out["slack_factor"] = stored["slack_factor"]
    if isinstance(stored.get("inferred_pin"), dict):
        out["inferred_pin"] = dict(stored["inferred_pin"])
    # pin_checks are genome-sample body checks — never publish.
    return out


def _column_signature(col: dict) -> tuple:
    return (
        int(col.get("index", -1)),
        str(col.get("role") or ""),
        str(col.get("member") or ""),
        str(col.get("count_table") or ""),
    )


def _table_signature(table: dict) -> tuple:
    cols = tuple(_column_signature(c) for c in (table.get("columns") or []))
    return (
        str(table.get("name") or ""),
        int(table.get("record_col", -1)),
        int(table.get("entry_col", -1)),
        table.get("index_col"),
        cols,
    )


def _field(value: object) -> object:
    """Normalize a signature field for equality / reporting."""
    return value


def fit_signature_diffs(stored: dict, fitted: dict) -> list[dict]:
    """Exact differing fields between two shareable fits.

    Each item names the table (or ``""`` for fit-level fields), optional column
    index, the field name, and stored vs confirmed values. Empty list means
    every compared field matches.
    """
    diffs: list[dict] = []

    def add(
        table: str,
        field: str,
        stored_v: object,
        confirmed_v: object,
        *,
        column: int | None = None,
    ) -> None:
        item = {
            "table": table,
            "field": field,
            "stored": stored_v,
            "confirmed": confirmed_v,
        }
        if column is not None:
            item["column"] = column
        diffs.append(item)

    if stored.get("decision") != fitted.get("decision"):
        add("", "decision", stored.get("decision"), fitted.get("decision"))
    if bool(stored.get("exact_eligible")) != bool(fitted.get("exact_eligible")):
        add(
            "",
            "exact_eligible",
            bool(stored.get("exact_eligible")),
            bool(fitted.get("exact_eligible")),
        )
    if bool(stored.get("column_only_refusal")) != bool(fitted.get("column_only_refusal")):
        add(
            "",
            "column_only_refusal",
            bool(stored.get("column_only_refusal")),
            bool(fitted.get("column_only_refusal")),
        )
    saved = stored.get("inferred_pin")
    got = fitted.get("inferred_pin")
    if isinstance(saved, dict) and saved.get("template"):
        if got is not None and isinstance(got, dict) and got.get("template") not in (
            None,
            saved.get("template"),
        ):
            add("", "inferred_pin.template", saved.get("template"), got.get("template"))

    st = list(stored.get("tables") or [])
    ft = list(fitted.get("tables") or [])
    if len(st) != len(ft):
        add("", "table_count", len(st), len(ft))
    by_name = {t.get("name"): t for t in st}
    fitted_names = {t.get("name") for t in ft}
    for name, prior in by_name.items():
        if name not in fitted_names:
            add(str(name or ""), "table_present", True, False)
    for table in ft:
        name = str(table.get("name") or "")
        prior = by_name.get(table.get("name"))
        if prior is None:
            add(name, "table_present", False, True)
            continue
        for field in ("record_col", "entry_col", "index_col"):
            if prior.get(field) != table.get(field):
                add(name, field, prior.get(field), table.get(field))
        prior_cols = {int(c.get("index", -1)): c for c in (prior.get("columns") or [])}
        fitted_cols = {int(c.get("index", -1)): c for c in (table.get("columns") or [])}
        for index in sorted(set(prior_cols) | set(fitted_cols)):
            pc = prior_cols.get(index)
            fc = fitted_cols.get(index)
            if pc is None:
                add(name, "column_present", False, True, column=index)
                continue
            if fc is None:
                add(name, "column_present", True, False, column=index)
                continue
            for field in ("role", "member", "count_table"):
                if _field(pc.get(field)) != _field(fc.get(field)):
                    add(name, field, pc.get(field), fc.get(field), column=index)
    return diffs


def fit_signatures_match(stored: dict, fitted: dict) -> tuple[bool, str]:
    """Compare shareable fit facts. Layout/meta may still differ; roles must not."""
    diffs = fit_signature_diffs(stored, fitted)
    if not diffs:
        return True, ""
    # Compact reason for decision.txt; full list available via fit_signature_diffs.
    parts: list[str] = []
    for d in diffs[:12]:
        loc = d["table"] or "fit"
        if "column" in d:
            loc = f"{loc}[{d['column']}]"
        parts.append(f"{loc}.{d['field']}: stored={d['stored']!r} confirmed={d['confirmed']!r}")
    why = "; ".join(parts)
    if len(diffs) > 12:
        why += f"; …+{len(diffs) - 12} more"
    return False, why


class ContractStore:
    """Directory of one JSON file per contract key."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def load(self, key: str) -> tuple[dict | None, str | None]:
        """Return (payload, error_reason). Corrupt/truncated → (None, reason)."""
        path = self.path_for(key)
        if not path.is_file():
            return None, None
        try:
            raw = path.read_text()
        except OSError as exc:
            return None, f"unreadable: {exc}"
        if not raw.strip():
            return None, "empty entry"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            return None, f"corrupt json: {exc}"
        if not isinstance(payload, dict):
            return None, "corrupt: not an object"
        if int(payload.get("version") or 0) != STORE_VERSION:
            return None, f"unsupported version {payload.get('version')!r}"
        if payload.get("key") != key:
            return None, "key mismatch inside entry"
        fit = payload.get("fit")
        if not isinstance(fit, dict) or "decision" not in fit:
            return None, "missing fit"
        if payload.get("binary_digest") is None or payload.get("release_hash") is None:
            return None, "missing key parts"
        return payload, None

    def save(self, key_info: dict[str, str], fit: dict) -> Path:
        """Atomically publish a shareable fit. Returns the final path."""
        key = key_info["key"]
        payload: dict[str, Any] = {
            "version": STORE_VERSION,
            "key": key,
            "binary_digest": key_info["binary_digest"],
            "argv_digest": key_info["argv_digest"],
            "release_hash": key_info["release_hash"],
            "fit": shareable_payload(fit),
        }
        dest = self.path_for(key)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{key}.",
            suffix=".tmp",
            dir=str(self.root),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, sort_keys=True)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, dest)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        return dest
