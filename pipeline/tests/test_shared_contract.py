"""Opt-in --contract-store: reuse, isolation, contradiction, corruption, concurrency, default."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acts.contract_store import (
    CONFIRM_N,
    ContractStore,
    contract_key,
    fit_signatures_match,
    release_content_hash,
    shareable_payload,
)
from acts.reference_fit import PROBE_SEED, partition_indices, verify_stored_fit
from acts.reference_formats import parse_entryline, parse_reference, read_records, write_entries
from acts.reference_run import ReferenceIncremental, body_lines, confirm_stored_fit

FIX = Path(__file__).resolve().parent / "fixtures" / "reference_fitter"
HITS = {"e1", "e3", "e4"}
ARGV = ["law", "{reference}", "{input}", "{output}"]
SEED_A = 20261331
SEED_B = 20261332


def _render(records, entries, scale: float, *, hits=HITS, footer: str = "", fmt: str = ".3g"):
    lines = ["# record entry evalue"]
    for rec in records:
        for entry in entries:
            if entry.primary not in hits:
                continue
            lines.append(f"{rec.key} {entry.primary} {format(scale * float(rec.description), fmt)}")
    if footer:
        lines.append(f"# {footer}")
    return {"out": "\n".join(lines) + "\n"}


def stock(records, entries):
    return _render(records, entries, len(entries), footer=f"run on {len(entries)} entries")


def honest_pin(records, entries, values):
    return _render(records, entries, values["entry_count"], footer="pinned")


def _genome(tmp: Path, name: str, text: str) -> Path:
    path = tmp / name
    path.write_text(text)
    return path


def _run(
    tmp: Path,
    *,
    genome: Path,
    ref: Path,
    cache: Path,
    out: Path,
    store: Path | None,
    pin_runner=honest_pin,
    runner=stock,
    pin="-Z {entry_count}",
    argv=None,
):
    return ReferenceIncremental(
        argv=argv or ARGV,
        input_path=genome,
        out_dir=out,
        reference=ref,
        cache_path=cache,
        verify="full",
        runner=runner,
        pin=pin,
        pin_runner=pin_runner,
        contract_store=store,
    ).run()


class SharedContractTests(unittest.TestCase):
    def _ref(self, tmp: Path) -> Path:
        return FIX / "ab.entryline"

    def _genomes(self, tmp: Path) -> tuple[Path, Path]:
        # ab.faa is too small for a stable entry_count vs identity distinction;
        # use four records with distinct descriptions so both genomes fit the same member.
        g_a = _genome(
            tmp,
            "a.faa",
            ">a0 2.0\nACDE\n>a1 3.0\nFGHI\n>a2 1.5\nKLMN\n>a3 4.0\nOPQR\n",
        )
        g_b = _genome(
            tmp,
            "b.faa",
            ">b0 2.5\nACDE\n>b1 3.5\nFGHI\n>b2 1.0\nKLMN\n>b3 5.0\nOPQR\n",
        )
        return g_a, g_b

    def test_reuse_byte_identical_to_stock_and_no_store(self) -> None:
        """Genome B reuses A's stored contract; output matches stock and no-store B."""
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ref = self._ref(tmp)
            store = tmp / "store"
            g_a, g_b = self._genomes(tmp)
            a = _run(
                tmp,
                genome=g_a,
                ref=ref,
                cache=tmp / "cache_a.sqlite",
                out=tmp / "out_a",
                store=store,
            )
            self.assertEqual(a.decision, "SHIP", a.reason)
            self.assertEqual(a.extra.get("contract_store"), "stored")
            b_store = _run(
                tmp,
                genome=g_b,
                ref=ref,
                cache=tmp / "cache_b.sqlite",
                out=tmp / "out_b_store",
                store=store,
            )
            self.assertEqual(b_store.decision, "SHIP", b_store.reason)
            self.assertEqual(b_store.extra.get("contract_store"), "reused", b_store.extra)
            self.assertIn("stored_verified", b_store.extra.get("contract_confirmations") or [])
            b_plain = _run(
                tmp,
                genome=g_b,
                ref=ref,
                cache=tmp / "cache_b_plain.sqlite",
                out=tmp / "out_b_plain",
                store=None,
            )
            self.assertEqual(b_plain.decision, "SHIP", b_plain.reason)
            got_store = (tmp / "out_b_store" / "tables" / "out").read_text()
            got_plain = (tmp / "out_b_plain" / "tables" / "out").read_text()
            want = stock(read_records(g_b), parse_reference(ref))["out"]
            self.assertEqual(body_lines(got_store), body_lines(want))
            self.assertEqual(body_lines(got_store), body_lines(got_plain))

    def test_key_isolation_binary_argv_release(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ref = self._ref(tmp)
            store = tmp / "store"
            g, _ = self._genomes(tmp)
            first = _run(
                tmp, genome=g, ref=ref, cache=tmp / "c1.sqlite", out=tmp / "o1", store=store
            )
            self.assertEqual(first.extra.get("contract_store"), "stored")
            key = first.extra["contract_key"]

            # Different argv → different key, miss.
            other = _run(
                tmp,
                genome=g,
                ref=ref,
                cache=tmp / "c2.sqlite",
                out=tmp / "o2",
                store=store,
                argv=["law", "--cpu", "1", "{reference}", "{input}", "{output}"],
            )
            self.assertEqual(other.extra.get("contract_store"), "stored")
            self.assertNotEqual(other.extra.get("contract_key"), key)

            # Different release content → miss.
            ref2 = tmp / "other.entryline"
            write_entries(
                parse_reference(ref) + parse_entryline("e9 7\n"),
                ref2,
            )
            rel = _run(
                tmp, genome=g, ref=ref2, cache=tmp / "c3.sqlite", out=tmp / "o3", store=store
            )
            self.assertNotEqual(rel.extra.get("contract_key"), key)
            self.assertIn(rel.extra.get("contract_store"), {"stored", "reused"})

            # Binary digest is part of the key (unresolved marker for in-process).
            info = contract_key(ARGV, ref, pin="-Z {entry_count}")
            self.assertEqual(info["key"], key)
            self.assertEqual(info["release_hash"], release_content_hash(ref))

            # Distinct on-disk binaries → distinct keys.
            bin_a = tmp / "tool_a"
            bin_b = tmp / "tool_b"
            bin_a.write_text("#!/bin/sh\n# a\n")
            bin_b.write_text("#!/bin/sh\n# b\n")
            bin_a.chmod(0o755)
            bin_b.chmod(0o755)
            ka = contract_key([str(bin_a), "{reference}", "{input}"], ref)
            kb = contract_key([str(bin_b), "{reference}", "{input}"], ref)
            self.assertNotEqual(ka["binary_digest"], kb["binary_digest"])
            self.assertNotEqual(ka["key"], kb["key"])

    def test_contradiction_falls_back_to_full_probe(self) -> None:
        """Genome B's sample contradicts stored roles → confirm_fail, still correct."""

        def scaled(records, entries):
            # Genome-dependent: records named c* get identity-valued columns;
            # others get entry_count scaling. Fits disagree across genomes.
            if any(rec.key.startswith("c") for rec in records):
                lines = ["# record entry evalue"]
                for rec in records:
                    for entry in entries:
                        if entry.primary not in HITS:
                            continue
                        lines.append(f"{rec.key} {entry.primary} {float(rec.description):.3g}")
                lines.append("# identity")
                return {"out": "\n".join(lines) + "\n"}
            return _render(records, entries, len(entries), footer="scaled")

        def scaled_pin(records, entries, values):
            if any(rec.key.startswith("c") for rec in records):
                return scaled(records, entries)
            return _render(records, entries, values["entry_count"], footer="pinned")

        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ref = self._ref(tmp)
            store = tmp / "store"
            g_a, _ = self._genomes(tmp)
            g_b = _genome(
                tmp,
                "const.faa",
                ">c0 1.0\nAAAA\n>c1 2.0\nBBBB\n>c2 3.0\nCCCC\n>c3 4.0\nDDDD\n",
            )
            a = _run(
                tmp,
                genome=g_a,
                ref=ref,
                cache=tmp / "ca.sqlite",
                out=tmp / "oa",
                store=store,
                runner=scaled,
                pin_runner=scaled_pin,
            )
            self.assertEqual(a.decision, "SHIP", a.reason)
            b = _run(
                tmp,
                genome=g_b,
                ref=ref,
                cache=tmp / "cb.sqlite",
                out=tmp / "ob",
                store=store,
                runner=scaled,
                pin_runner=scaled_pin,
            )
            # B must not silently ship on A's entry_count contract.
            self.assertEqual(b.extra.get("contract_store"), "confirm_fail", b.extra)
            self.assertTrue(
                b.decision in {"SHIP", "REFUSE", "REFUSE_PIN", "FALLBACK"},
                b.decision,
            )
            if b.decision == "SHIP":
                got = (tmp / "ob" / "tables" / "out").read_text()
                want = scaled(read_records(g_b), parse_reference(ref))["out"]
                self.assertEqual(body_lines(got), body_lines(want))

    def test_corruption_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ref = self._ref(tmp)
            store_dir = tmp / "store"
            g, _ = self._genomes(tmp)
            a = _run(
                tmp, genome=g, ref=ref, cache=tmp / "c.sqlite", out=tmp / "o", store=store_dir
            )
            key = a.extra["contract_key"]
            path = ContractStore(store_dir).path_for(key)
            path.write_text("{not-json")
            b = _run(
                tmp,
                genome=g,
                ref=ref,
                cache=tmp / "c2.sqlite",
                out=tmp / "o2",
                store=store_dir,
            )
            self.assertEqual(b.extra.get("contract_store"), "corrupt")
            self.assertEqual(b.decision, "SHIP", b.reason)
            # Truncation
            path.write_text('{"version": 1, "key": "%s"' % key)
            c = _run(
                tmp,
                genome=g,
                ref=ref,
                cache=tmp / "c3.sqlite",
                out=tmp / "o3",
                store=store_dir,
            )
            self.assertEqual(c.extra.get("contract_store"), "corrupt")

    def test_concurrency_one_entry_no_partial(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            store = ContractStore(tmp / "store")
            ref = self._ref(tmp)
            key_info = contract_key(ARGV, ref, pin="-Z {entry_count}")
            fit = {
                "decision": "SHIP",
                "reason": "ok",
                "tables": [],
                "exact_eligible": False,
                "column_only_refusal": False,
            }
            errors: list[BaseException] = []

            def writer() -> None:
                try:
                    store.save(key_info, fit)
                except BaseException as exc:  # noqa: BLE001 — collect for join
                    errors.append(exc)

            threads = [threading.Thread(target=writer) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(errors, [])
            payload, err = store.load(key_info["key"])
            self.assertIsNone(err)
            self.assertIsNotNone(payload)
            self.assertEqual(payload["fit"]["decision"], "SHIP")
            # No leftover temps
            leftovers = list((tmp / "store").glob("*.tmp"))
            self.assertEqual(leftovers, [])

    def test_default_path_does_not_import_contract_store(self) -> None:
        """Subprocess: run without --contract-store never imports the module."""
        code = r"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(%r)))
from acts.reference_run import ReferenceIncremental

FIX = Path(%r)
HITS = {"e1", "e3", "e4"}

def stock(records, entries):
    lines = ["# record entry evalue"]
    for rec in records:
        for entry in entries:
            if entry.primary not in HITS:
                continue
            lines.append(f"{rec.key} {entry.primary} {len(entries) * float(rec.description):.3g}")
    return {"out": "\n".join(lines) + "\n"}

def pin(records, entries, values):
    lines = ["# record entry evalue"]
    for rec in records:
        for entry in entries:
            if entry.primary not in HITS:
                continue
            lines.append(f"{rec.key} {entry.primary} {values['entry_count'] * float(rec.description):.3g}")
    return {"out": "\n".join(lines) + "\n"}

import tempfile
with tempfile.TemporaryDirectory() as raw:
    tmp = Path(raw)
    faa = tmp / "g.faa"
    faa.write_text(">a0 2.0\nACDE\n>a1 3.0\nFGHI\n>a2 1.5\nKLMN\n>a3 4.0\nOPQR\n")
    ReferenceIncremental(
        argv=["law", "{reference}", "{input}", "{output}"],
        input_path=faa,
        out_dir=tmp / "out",
        reference=FIX / "ab.entryline",
        cache_path=tmp / "c.sqlite",
        verify="full",
        runner=stock,
        pin="-Z {entry_count}",
        pin_runner=pin,
    ).run()
print("imported", "acts.contract_store" in sys.modules)
""" % (
            str(Path(__file__).resolve().parents[1]),
            str(FIX),
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("imported False", proc.stdout)

    def test_fit_signature_helper_and_shareable_strips_pin_checks(self) -> None:
        a = {
            "decision": "SHIP",
            "tables": [
                {
                    "name": "out",
                    "record_col": 0,
                    "entry_col": 1,
                    "index_col": None,
                    "columns": [{"index": 2, "role": "numeric", "member": "entry_count"}],
                }
            ],
            "exact_eligible": False,
            "column_only_refusal": False,
            "pin_checks": {"-Z {entry_count}": {"ok": True}},
        }
        b = json.loads(json.dumps(a))
        ok, _ = fit_signatures_match(a, b)
        self.assertTrue(ok)
        b["tables"][0]["columns"][0]["member"] = "identity"
        ok, why = fit_signatures_match(a, b)
        self.assertFalse(ok)
        self.assertIn("member", why)
        self.assertIn("entry_count", why)
        self.assertIn("identity", why)
        shared = shareable_payload(a)
        self.assertNotIn("pin_checks", shared)

    def test_verify_self_consistency_positive(self) -> None:
        """Stored contract from genome A verifies on A's own sample (positive)."""
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ref = self._ref(tmp)
            store = tmp / "store"
            g_a, _ = self._genomes(tmp)
            a = _run(
                tmp,
                genome=g_a,
                ref=ref,
                cache=tmp / "ca.sqlite",
                out=tmp / "oa",
                store=store,
            )
            self.assertEqual(a.decision, "SHIP", a.reason)
            self.assertEqual(a.extra.get("contract_store"), "stored")
            key = a.extra["contract_key"]
            payload, err = ContractStore(store).load(key)
            self.assertIsNone(err)
            assert payload is not None
            entries = parse_reference(ref)
            records = read_records(g_a)
            ri = ReferenceIncremental(
                argv=ARGV,
                input_path=g_a,
                out_dir=tmp / "verify_out",
                reference=ref,
                cache_path=tmp / "cv.sqlite",
                verify="none",
                runner=stock,
                pin="-Z {entry_count}",
                pin_runner=honest_pin,
            )
            ok, why = confirm_stored_fit(
                payload["fit"],
                entries,
                records,
                ri._invoke(ref),
                n_p=min(CONFIRM_N, len(records)),
                seed=PROBE_SEED,
            )
            self.assertTrue(ok, why)
            self.assertNotEqual(why, "no_rows")
            # Second run on the same genome must reuse.
            again = _run(
                tmp,
                genome=g_a,
                ref=ref,
                cache=tmp / "ca2.sqlite",
                out=tmp / "oa2",
                store=store,
            )
            self.assertEqual(again.extra.get("contract_store"), "reused", again.extra)
            self.assertEqual(again.decision, "SHIP", again.reason)

    def test_verify_poisoned_store_negative(self) -> None:
        """Poison numeric member to identity → confirm_fail (negative control)."""
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ref = self._ref(tmp)
            store_dir = tmp / "store"
            g_a, g_b = self._genomes(tmp)
            a = _run(
                tmp,
                genome=g_a,
                ref=ref,
                cache=tmp / "ca.sqlite",
                out=tmp / "oa",
                store=store_dir,
            )
            self.assertEqual(a.extra.get("contract_store"), "stored")
            key = a.extra["contract_key"]
            path = ContractStore(store_dir).path_for(key)
            payload = json.loads(path.read_text())
            poisoned = False
            for table in payload["fit"].get("tables") or []:
                for col in table.get("columns") or []:
                    if col.get("role") == "numeric" and col.get("member") not in (
                        None,
                        "identity",
                        "byte",
                    ):
                        col["member"] = "identity"
                        col["count_table"] = None
                        poisoned = True
                        break
                if poisoned:
                    break
            self.assertTrue(poisoned, "fixture fit has no poisonable numeric member")
            path.write_text(json.dumps(payload, indent=2) + "\n")
            b = _run(
                tmp,
                genome=g_b,
                ref=ref,
                cache=tmp / "cb.sqlite",
                out=tmp / "ob",
                store=store_dir,
            )
            self.assertEqual(b.extra.get("contract_store"), "confirm_fail", b.extra)
            reason = b.extra.get("contract_store_reason") or ""
            self.assertTrue(
                "identity" in reason or "differ" in reason or "member" in reason,
                reason,
            )
            if b.decision == "SHIP":
                got = (tmp / "ob" / "tables" / "out").read_text()
                want = stock(read_records(g_b), parse_reference(ref))["out"]
                self.assertEqual(body_lines(got), body_lines(want))

    def test_verify_hand_planted_wrong_member_negative(self) -> None:
        """Hand-plant identity on a scaled numeric column → confirm_stored_fit fails.

        Distinct from the poisoned-store path: this calls the verification API
        directly. On this fixture's PROBE_SEED bipartition, entry_count,
        total_entry_length, and per_key_row_count share φ=2, so identity is the
        discriminating wrong member.
        """
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ref = self._ref(tmp)
            store = tmp / "store"
            g_a, g_b = self._genomes(tmp)
            a = _run(
                tmp,
                genome=g_a,
                ref=ref,
                cache=tmp / "ca.sqlite",
                out=tmp / "oa",
                store=store,
            )
            self.assertEqual(a.decision, "SHIP", a.reason)
            payload, err = ContractStore(store).load(a.extra["contract_key"])
            self.assertIsNone(err)
            assert payload is not None
            fit = json.loads(json.dumps(payload["fit"]))
            planted = False
            for table in fit.get("tables") or []:
                for col in table.get("columns") or []:
                    if col.get("member") == "entry_count":
                        col["member"] = "identity"
                        col["count_table"] = None
                        planted = True
                        break
                if planted:
                    break
            self.assertTrue(planted, "expected an entry_count column to re-label")
            entries = parse_reference(ref)
            records = read_records(g_b)
            ri = ReferenceIncremental(
                argv=ARGV,
                input_path=g_b,
                out_dir=tmp / "v",
                reference=ref,
                cache_path=tmp / "cv.sqlite",
                verify="none",
                runner=stock,
                pin="-Z {entry_count}",
                pin_runner=honest_pin,
            )
            ok, why = confirm_stored_fit(
                fit,
                entries,
                records,
                ri._invoke(ref),
                n_p=min(CONFIRM_N, len(records)),
                seed=PROBE_SEED,
            )
            self.assertFalse(ok, f"wrong member must fail, got ok why={why!r}")
            self.assertIn("identity", why)
            self.assertIn("differ", why)

    def test_verify_stored_fit_unit_no_rows_is_not_contradiction(self) -> None:
        """Empty observations accept the stored contract (vacuous, not a fail)."""
        tables = [
            {
                "name": "out",
                "record_col": 0,
                "entry_col": 1,
                "index_col": None,
                "columns": [
                    {"index": 0, "role": "byte", "member": "byte"},
                    {"index": 1, "role": "byte", "member": "byte"},
                    {"index": 2, "role": "numeric", "member": "entry_count"},
                ],
            }
        ]
        parts = partition_indices(4, 2, PROBE_SEED)
        empty = {"out": "# header only\n"}
        ok, why = verify_stored_fit(
            tables,
            entries_n=4,
            lengths=[10, 10, 10, 10],
            part_index_lists=parts,
            alias_to_index={"e1": 0, "e2": 1, "e3": 2, "e4": 3},
            whole_tables=empty,
            part_tables=[empty, empty],
        )
        self.assertTrue(ok)
        self.assertEqual(why, "no_rows")

    def test_verify_per_key_row_count_needs_sibling_count_table(self) -> None:
        """P2d regression: own==stored per_key_row_count must verify with siblings.

        Layer-C used to call verify_stored_fit([domtbl]) alone; sibling tbl
        counts vanished and φ was NaN → false rejection. Full contract and
        per-table-with-count_key_tables must accept; poisoned member, wrong
        member, and wrong count_table must still fail.
        """
        # Four entries; parts {e1,e2} vs {e3,e4}. q0 hits e1+e2 in part0 and e3 in part1
        # → tbl counts (2,1)/whole 3 so per_key φ ∈ {1.5, 3}, distinct from entry_count φ=2.
        parts = [[0, 1], [2, 3]]
        aliases = {"e1": 0, "e2": 1, "e3": 2, "e4": 3}
        lengths = [10, 10, 10, 10]
        # tbl: entry_col=0 record_col=2. Cells byte-identical part↔whole for same key.
        whole = {
            "tbl": "#\ne1 a q0 b\ne2 a q0 b\ne3 a q0 b\n",
            "domtbl": (
                "#\n"
                # entry acc tlen query acc qlen E score bias # of c-Ev i-Ev ...
                # part0 φ_tbl=1.5 → c=1.0e-3*1.5=1.5e-3; i uses entry_count φ=2
                "e1 a 100 q0 b 50 1.0 10 0 1 1 1.5e-3 4.0e-3 10 0 1 10 1 10 1 10 0.9 d\n"
                # part1 φ_tbl=3 → c=1.0e-3*3=3.0e-3
                "e3 a 100 q0 b 50 2.0 10 0 1 1 3.0e-3 4.0e-3 10 0 1 10 1 10 1 10 0.9 d\n"
            ),
        }
        part0 = {
            "tbl": "#\ne1 a q0 b\ne2 a q0 b\n",
            "domtbl": (
                "#\n"
                "e1 a 100 q0 b 50 1.0 10 0 1 1 1.0e-3 2.0e-3 10 0 1 10 1 10 1 10 0.9 d\n"
            ),
        }
        part1 = {
            "tbl": "#\ne3 a q0 b\n",
            "domtbl": (
                "#\n"
                "e3 a 100 q0 b 50 2.0 10 0 1 1 1.0e-3 2.0e-3 10 0 1 10 1 10 1 10 0.9 d\n"
            ),
        }
        stored = [
            {
                "name": "tbl",
                "record_col": 2,
                "entry_col": 0,
                "index_col": None,
                "columns": [
                    {"index": 0, "role": "byte", "member": "byte"},
                    {"index": 1, "role": "byte", "member": "byte"},
                    {"index": 2, "role": "byte", "member": "byte"},
                    {"index": 3, "role": "byte", "member": "byte"},
                ],
            },
            {
                "name": "domtbl",
                "record_col": 3,
                "entry_col": 0,
                "index_col": 9,
                "columns": [
                    {"index": 0, "role": "byte", "member": "byte"},
                    {"index": 1, "role": "byte", "member": "byte"},
                    {"index": 2, "role": "numeric", "member": "identity"},
                    {"index": 3, "role": "byte", "member": "byte"},
                    {"index": 4, "role": "byte", "member": "byte"},
                    {"index": 5, "role": "numeric", "member": "identity"},
                    {"index": 6, "role": "numeric", "member": "identity"},
                    {"index": 7, "role": "numeric", "member": "identity"},
                    {"index": 8, "role": "numeric", "member": "identity"},
                    {"index": 9, "role": "numeric", "member": "identity"},
                    {"index": 10, "role": "numeric", "member": "identity"},
                    {
                        "index": 11,
                        "role": "numeric",
                        "member": "per_key_row_count",
                        "count_table": "tbl",
                    },
                    {"index": 12, "role": "numeric", "member": "entry_count"},
                    {"index": 13, "role": "numeric", "member": "identity"},
                    {"index": 14, "role": "numeric", "member": "identity"},
                    {"index": 15, "role": "numeric", "member": "identity"},
                    {"index": 16, "role": "numeric", "member": "identity"},
                    {"index": 17, "role": "numeric", "member": "identity"},
                    {"index": 18, "role": "numeric", "member": "identity"},
                    {"index": 19, "role": "numeric", "member": "identity"},
                    {"index": 20, "role": "numeric", "member": "identity"},
                    {"index": 21, "role": "numeric", "member": "identity"},
                    {"index": 22, "role": "byte", "member": "byte"},
                ],
            },
        ]
        common = dict(
            entries_n=4,
            lengths=lengths,
            part_index_lists=parts,
            alias_to_index=aliases,
            whole_tables=whole,
            part_tables=[part0, part1],
        )
        # Positive: full contract (own == stored).
        ok, why = verify_stored_fit(stored, **common)
        self.assertTrue(ok, why)
        # Positive: Layer-C style one table, but with full count_key_tables.
        dom = [stored[1]]
        ok, why = verify_stored_fit(dom, count_key_tables=stored, **common)
        self.assertTrue(ok, why)
        # The P2d bug shape: one table, no siblings → false rejection.
        ok_bug, why_bug = verify_stored_fit(dom, **common)
        self.assertFalse(ok_bug, "missing sibling counts must fail this sample")
        self.assertIn("per_key_row_count", why_bug)

        # Negative: poisoned identity on the scaled column.
        poisoned = json.loads(json.dumps(stored))
        for col in poisoned[1]["columns"]:
            if col["index"] == 11:
                col["member"] = "identity"
                col["count_table"] = None
        ok, why = verify_stored_fit(poisoned, **common)
        self.assertFalse(ok, why)
        self.assertIn("identity", why)

        # Negative: hand-planted wrong member (entry_count φ=2 ≠ per_key φ).
        wrong = json.loads(json.dumps(stored))
        for col in wrong[1]["columns"]:
            if col["index"] == 11:
                col["member"] = "entry_count"
                col["count_table"] = None
        ok, why = verify_stored_fit(wrong, **common)
        self.assertFalse(ok, why)

        # Negative: wrong count_table name.
        bad_ct = json.loads(json.dumps(stored))
        for col in bad_ct[1]["columns"]:
            if col["index"] == 11:
                col["count_table"] = "domtbl"
        ok, why = verify_stored_fit(bad_ct, **common)
        self.assertFalse(ok, why)

    def test_confirm_n_matches_calibration(self) -> None:
        self.assertEqual(CONFIRM_N, 10)

    def test_layer_a_refside_parse_and_prep_cache(self) -> None:
        """Cached prepared reference → body-identical to a fresh-prep run."""
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ref = self._ref(tmp)
            store = tmp / "store"
            g_a, g_b = self._genomes(tmp)
            prep_script = tmp / "prep.py"
            prep_script.write_text(
                "import sys\nfrom pathlib import Path\n"
                "Path(sys.argv[1] + '.idx').write_text('ok\\n')\n"
            )
            prep = f"{sys.executable} {prep_script} {{reference}}"

            def run(genome, cache, out, store_path):
                return ReferenceIncremental(
                    argv=ARGV,
                    input_path=genome,
                    out_dir=out,
                    reference=ref,
                    cache_path=cache,
                    verify="full",
                    runner=stock,
                    pin="-Z {entry_count}",
                    pin_runner=honest_pin,
                    prep=prep,
                    contract_store=store_path,
                ).run()

            a = run(g_a, tmp / "ca.sqlite", tmp / "oa", store)
            self.assertEqual(a.decision, "SHIP", a.reason)
            self.assertEqual(a.extra.get("contract_refside_parse"), "stored")
            self.assertEqual(a.extra.get("contract_refside_prep"), "stored")
            b = run(g_b, tmp / "cb.sqlite", tmp / "ob", store)
            self.assertEqual(b.decision, "SHIP", b.reason)
            self.assertEqual(b.extra.get("contract_refside_parse"), "hit")
            self.assertEqual(b.extra.get("contract_refside_prep"), "hit")
            # Fresh prep, no store — body must match the cached-prep run.
            plain = ReferenceIncremental(
                argv=ARGV,
                input_path=g_b,
                out_dir=tmp / "ob_plain",
                reference=ref,
                cache_path=tmp / "cb_plain.sqlite",
                verify="full",
                runner=stock,
                pin="-Z {entry_count}",
                pin_runner=honest_pin,
                prep=prep,
            ).run()
            self.assertEqual(plain.decision, "SHIP", plain.reason)
            got = (tmp / "ob" / "tables" / "out").read_text()
            want = (tmp / "ob_plain" / "tables" / "out").read_text()
            self.assertEqual(body_lines(got), body_lines(want))

    def test_layer_a_prep_command_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ref = self._ref(tmp)
            store = tmp / "store"
            g, _ = self._genomes(tmp)
            prep_a = tmp / "prep_a.py"
            prep_b = tmp / "prep_b.py"
            prep_a.write_text(
                "import sys\nfrom pathlib import Path\nPath(sys.argv[1]+'.idx').write_text('a\\n')\n"
            )
            prep_b.write_text(
                "import sys\nfrom pathlib import Path\nPath(sys.argv[1]+'.idx').write_text('b\\n')\n"
            )
            a = ReferenceIncremental(
                argv=ARGV,
                input_path=g,
                out_dir=tmp / "oa",
                reference=ref,
                cache_path=tmp / "ca.sqlite",
                verify="full",
                runner=stock,
                pin="-Z {entry_count}",
                pin_runner=honest_pin,
                prep=f"{sys.executable} {prep_a} {{reference}}",
                contract_store=store,
            ).run()
            b = ReferenceIncremental(
                argv=ARGV,
                input_path=g,
                out_dir=tmp / "ob",
                reference=ref,
                cache_path=tmp / "cb.sqlite",
                verify="full",
                runner=stock,
                pin="-Z {entry_count}",
                pin_runner=honest_pin,
                prep=f"{sys.executable} {prep_b} {{reference}}",
                contract_store=store,
            ).run()
            self.assertNotEqual(
                a.extra.get("contract_refside_key"),
                b.extra.get("contract_refside_key"),
            )
            self.assertEqual(b.extra.get("contract_refside_prep"), "stored")

    def test_layer_b_refinement_conflict_not_merged(self) -> None:
        from acts.contract_store import merge_undetermined_fields

        stored = {
            "decision": "SHIP",
            "tables": [
                {
                    "name": "out",
                    "record_col": 0,
                    "entry_col": 1,
                    "index_col": 9,
                    "columns": [
                        {"index": 2, "role": "numeric", "member": "entry_count"}
                    ],
                }
            ],
            "exact_eligible": False,
            "column_only_refusal": False,
        }
        richer = json.loads(json.dumps(stored))
        richer["tables"][0]["index_col"] = 5
        merged, events = merge_undetermined_fields(stored, richer)
        self.assertIsNone(merged)
        self.assertTrue(any(e.get("action") == "conflict" for e in events))
        # Fill undetermined index_col.
        weak = json.loads(json.dumps(stored))
        weak["tables"][0]["index_col"] = None
        merged, events = merge_undetermined_fields(weak, stored)
        self.assertIsNotNone(merged)
        self.assertEqual(merged["tables"][0]["index_col"], 9)
        self.assertTrue(any(e.get("action") == "fill" for e in events))

    def test_layer_c_recorded_on_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            ref = self._ref(tmp)
            store = tmp / "store"
            g_a, g_b = self._genomes(tmp)
            _run(
                tmp, genome=g_a, ref=ref, cache=tmp / "ca.sqlite", out=tmp / "oa", store=store
            )
            b = _run(
                tmp, genome=g_b, ref=ref, cache=tmp / "cb.sqlite", out=tmp / "ob", store=store
            )
            self.assertEqual(b.extra.get("contract_store"), "reused")
            self.assertEqual(b.extra.get("contract_layer_c"), "all_tables_verified")
            conf = b.extra.get("contract_confirmations") or []
            self.assertTrue(any(str(c).startswith("layer_c_tables=") for c in conf))


if __name__ == "__main__":
    unittest.main()
