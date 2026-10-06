"""Reference-side fitter: closed family, T3 oracles, ship controls, name guard."""

from __future__ import annotations

import gzip
import hashlib
import json
import random
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acts.entry_hash import entry_content_hash
from acts.reference_fit import (
    MEMBERS,
    PROBE_SEED,
    disambiguating_indices,
    partition_indices,
    shuffled_indices,
)
from acts.reference_formats import parse_reference, read_records, write_entries
from acts.reference_run import ReferenceIncremental, detect_reference, probe_fit

PIPE = Path(__file__).resolve().parents[1]
FIX = Path(__file__).resolve().parent / "fixtures" / "reference_fitter"
ACTS = PIPE / "acts"
FORBIDDEN = ("HMMER", "Pfam", "BLAST", "DIAMOND", "MMseqs")
# The profile grammar's own header token. It is format data, not a tool name.
ALLOW_TOKEN = "HMMER3/f"


def _table(records, entries, value_of) -> dict[str, str]:
    lines = ["# record entry evalue"]
    for rec in records:
        for entry in entries:
            value = value_of(rec, entry, records, entries)
            if value is None:
                continue
            lines.append(f"{rec.key} {entry.primary} {value:.6f}")
    return {"out": "\n".join(lines) + "\n"}


def _payload(rec) -> float:
    return float(rec.description)


def _law_count(rec, entry, records, entries):
    if entry.primary not in {"e1", "e3"}:
        return None
    return len(entries) * _payload(rec)


def _law_length(rec, entry, records, entries):
    if entry.primary not in {"e1", "e3"}:
        return None
    return sum(item.length for item in entries) * _payload(rec)


def _law_rows(rec, entry, records, entries):
    hits = set(rec.description.split(","))
    ids = [item.primary for item in entries if item.primary in hits]
    if entry.primary not in ids:
        return None
    return len(ids) * 0.5


def _law_rank(rec, entry, records, entries):
    order = sorted(entries, key=lambda item: item.content_hash)
    rank = {item.primary: i + 1 for i, item in enumerate(order)}
    return float(rank[entry.primary])


def _law_pairs(records, entries) -> dict[str, str]:
    lines = ["# record entry other evalue"]
    ids = [entry.primary for entry in entries]
    for rec in records:
        for i, left in enumerate(ids):
            for right in ids[i + 1 :]:
                lines.append(f"{rec.key} {left} {right} 1.000000")
    return {"out": "\n".join(lines) + "\n"}


def _numeric(result):
    cols = []
    for table in result.tables:
        for col in table.columns:
            if col.role == "numeric":
                cols.append(col)
    return cols


class ReferenceFitterTests(unittest.TestCase):
    def test_family_is_the_closed_four(self) -> None:
        self.assertEqual(
            MEMBERS,
            ("identity", "entry_count", "total_entry_length", "per_key_row_count"),
        )

    def test_fisher_yates_guard_and_not_shuffle(self) -> None:
        self.assertEqual(shuffled_indices(4, PROBE_SEED), [0, 3, 2, 1])
        parts = partition_indices(4, 2, PROBE_SEED)
        self.assertEqual(parts, [[0, 3], [2, 1]])
        rng = random.Random(PROBE_SEED)
        idx = list(range(4))
        rng.shuffle(idx)
        self.assertNotEqual(idx, [0, 3, 2, 1])

    def test_disambiguating_partition_on_ab(self) -> None:
        entries = parse_reference(FIX / "ab.entryline")
        split = disambiguating_indices(
            [entry.length for entry in entries],
            [entry.content_hash for entry in entries],
        )
        self.assertIsNotNone(split)
        assert split is not None
        self.assertEqual({entries[i].primary for i in split[0]}, {"e1", "e3"})
        self.assertEqual({entries[i].primary for i in split[1]}, {"e0", "e2"})

    def test_profile_hash_matches_historical_predicate(self) -> None:
        block = [
            "HMMER3/f [3.3 | Nov 2019]\n",
            "NAME  X\n",
            "ACC   PF00001.1\n",
            "LENG  10\n",
            "DATE  today\n",
            "BM    build\n",
            "SM    search\n",
            "COM   comment\n",
            "HMM   A\n",
            "//\n",
        ]
        self.assertEqual(_historical_strict(block), _library_strict(block))
        path = PIPE / "data" / "hmmer" / "Pfam-A.hmm.gz"
        if not path.is_file():
            return
        lines: list[str] = []
        with gzip.open(path, "rt") as handle:
            for line in handle:
                lines.append(line)
                if line.startswith("//"):
                    break
        self.assertEqual(_historical_strict(lines), _library_strict(lines))

    def test_t3_a_ships_entry_count_only_after_tie_break(self) -> None:
        result = probe_fit(*_load("ab.entryline", "ab.faa"), lambda recs, ents: _table(recs, ents, _law_count))
        self.assertEqual(result.decision, "SHIP", result.reason)
        self.assertTrue(result.used_tie_break)
        col = _numeric(result)[0]
        self.assertIn("entry_count", col.primary_fits)
        self.assertIn("total_entry_length", col.primary_fits)
        self.assertTrue(any(label.startswith("per_key_row_count") for label in col.primary_fits))
        self.assertEqual(col.member, "entry_count")
        self.assertTrue(col.tie_break["entry_count"]["fits"])
        self.assertFalse(col.tie_break["total_entry_length"]["fits"])

    def test_t3_b_ships_total_length_not_entry_count(self) -> None:
        result = probe_fit(*_load("ab.entryline", "ab.faa"), lambda recs, ents: _table(recs, ents, _law_length))
        self.assertEqual(result.decision, "SHIP", result.reason)
        self.assertTrue(result.used_tie_break)
        col = _numeric(result)[0]
        self.assertEqual(col.member, "total_entry_length")
        self.assertFalse(col.tie_break["entry_count"]["fits"])
        self.assertTrue(col.tie_break["total_entry_length"]["fits"])
        self.assertGreater(col.tie_break["entry_count"]["max_abs_residual"], 0.5)

    def test_t3_c_ships_per_key_row_count(self) -> None:
        result = probe_fit(*_load("c.entryline", "c.faa"), lambda recs, ents: _table(recs, ents, _law_rows))
        self.assertEqual(result.decision, "SHIP", result.reason)
        self.assertFalse(result.used_tie_break)
        col = _numeric(result)[0]
        self.assertEqual(col.member, "per_key_row_count")
        self.assertEqual(col.count_table, "out")

    def test_t3_d_rank_refuses(self) -> None:
        entries = parse_reference(FIX / "d.entryline")
        order = sorted(entries, key=lambda item: item.content_hash)
        rank = {item.primary: i + 1 for i, item in enumerate(order)}
        parts = partition_indices(len(entries), 2, PROBE_SEED)
        second = [entries[i] for i in parts[1]]
        part_rank = {
            item.primary: i + 1
            for i, item in enumerate(sorted(second, key=lambda item: item.content_hash))
        }
        self.assertEqual(rank["d2"], 3)
        self.assertEqual(part_rank["d2"], 2)
        result = probe_fit(*_load("d.entryline", "d.faa"), lambda recs, ents: _table(recs, ents, _law_rank))
        self.assertEqual(result.decision, "REFUSE", result.reason)

    def test_t3_e_pairs_refuse_on_decomposition(self) -> None:
        result = probe_fit(*_load("e.entryline", "e.faa"), _law_pairs)
        self.assertEqual(result.decision, "REFUSE", result.reason)
        self.assertIn("row-key", result.reason)

    def test_gestore_baseline_refuses_size_dependent_column(self) -> None:
        entries, records = _load("ab.entryline", "ab.faa")
        result = probe_fit(
            entries,
            records,
            lambda recs, ents: _table(recs, ents, _law_count),
            baseline="gestore",
        )
        self.assertEqual(result.decision, "REFUSE")
        self.assertIn("normalizer", result.reason)

    def test_incremental_rescale_matches_stock(self) -> None:
        with self._tmpdir() as tmp:
            ref1 = FIX / "ab.entryline"
            records = FIX / "ab.faa"
            ref2 = Path(tmp) / "v2.entryline"
            keep = [entry for entry in parse_reference(ref1) if entry.primary in {"e1", "e3"}]
            added = parse_reference_text_line()
            write_entries(keep + added, ref2)
            cache = Path(tmp) / "cache.sqlite"
            argv = ["law", "{reference}", "{input}", "{output}"]

            def run(ref: Path):
                return ReferenceIncremental(
                    argv=argv,
                    input_path=records,
                    out_dir=Path(tmp) / ref.stem,
                    reference=ref,
                    cache_path=cache,
                    verify="full",
                    runner=lambda recs, ents: _table(recs, ents, _law_count),
                ).run()

            first = run(ref1)
            self.assertEqual(first.decision, "SHIP", first.reason)
            second = run(ref2)
            self.assertEqual(second.decision, "SHIP", second.reason)
            self.assertGreater(int(second.extra["reused_rows"]), 0)
            text = (Path(tmp) / "v2" / "tables" / "out").read_text()
            self.assertIn("1.500000", text)
            self.assertIn("0.750000", text)

    def test_prep_command_builds_sidecar(self) -> None:
        with self._tmpdir() as tmp:
            tool = Path(tmp) / "tool.py"
            tool.write_text(
                "import sys\n"
                "from pathlib import Path\n"
                "ref, rec, dest = map(Path, sys.argv[1:4])\n"
                "if not Path(str(ref) + '.idx').is_file():\n"
                "    sys.stderr.write('missing sidecar\\n')\n"
                "    raise SystemExit(2)\n"
                "rows = []\n"
                "for record in rec.read_text().splitlines():\n"
                "    if not record.startswith('>'):\n"
                "        continue\n"
                "    name = record[1:].split()[0]\n"
                "    for line in ref.read_text().splitlines():\n"
                "        if line.strip():\n"
                "            rows.append(f'{name} {line.split()[0]} 1.000000')\n"
                "dest.write_text('# record entry evalue\\n' + '\\n'.join(rows) + '\\n')\n"
            )
            prep = Path(tmp) / "prep.py"
            prep.write_text(
                "import sys\nfrom pathlib import Path\n"
                "Path(sys.argv[1] + '.idx').write_text('1\\n')\n"
            )
            ref = FIX / "c.entryline"
            out = Path(tmp) / "out"
            rec = ReferenceIncremental(
                argv=[sys.executable, str(tool), "{reference}", "{input}", "{output}"],
                input_path=FIX / "c.faa",
                out_dir=out,
                reference=ref,
                prep=f"{sys.executable} {prep} {{reference}}",
                cache_path=Path(tmp) / "cache.sqlite",
                verify="full",
            ).run()
            self.assertEqual(rec.decision, "SHIP", rec.reason)

    def test_reference_autodetect_and_override(self) -> None:
        records = FIX / "ab.faa"
        ref = FIX / "ab.entryline"
        other = FIX / "c.entryline"
        found = detect_reference(["tool", str(ref), str(records), "{output}"], records, None)
        self.assertEqual(found.resolve(), ref.resolve())
        with self.assertRaises(Exception):
            detect_reference(["tool", str(ref), str(other), str(records)], records, None)
        chosen = detect_reference(
            ["tool", str(ref), str(other), str(records)], records, other
        )
        self.assertEqual(chosen.resolve(), other.resolve())

    def test_help_mentions_reference_controls(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "acts", "run", "--help"],
            cwd=PIPE,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        text = proc.stdout
        for needle in ("--reference", "--prep", "--baseline", "gestore", "reference"):
            self.assertIn(needle, text)

    def test_no_tool_names_in_acts(self) -> None:
        offenders: list[str] = []
        for path in ACTS.rglob("*"):
            if not path.is_file() or path.suffix in {".pyc"}:
                continue
            if "__pycache__" in path.parts:
                continue
            for lineno, line in enumerate(path.read_text(errors="replace").splitlines(), start=1):
                stripped = line
                for token in FORBIDDEN:
                    if token.lower() == "hmmer":
                        stripped = stripped.replace(ALLOW_TOKEN, "")
                lower = stripped.lower()
                for token in FORBIDDEN:
                    if token.lower() in lower:
                        offenders.append(f"{path.relative_to(PIPE)}:{lineno}:{line.strip()}")
                        break
        self.assertEqual(offenders, [])

    def test_ship_controls_unchanged(self) -> None:
        checks = json.loads((PIPE / "results" / "inference_checks.json").read_text())
        snpeff = checks["snpeff"]
        self.assertEqual(snpeff["n_reassembled"], 52638)
        self.assertEqual(snpeff["n_stock"], 52638)
        self.assertTrue(snpeff["bodies_equal"])
        fill = checks["fill_tags_real"]
        self.assertEqual(fill["n_reassembled"], 52638)
        self.assertEqual(fill["n_stock"], 52638)
        self.assertTrue(fill["bodies_equal"])
        self.assertEqual(fill["HG00099"]["n_hits"], 23072)
        self.assertIn("SAMPLES", fill["HG00099"]["cache_key_fields"])

    def _tmpdir(self):
        import tempfile

        return tempfile.TemporaryDirectory()


def _load(reference: str, records: str):
    return parse_reference(FIX / reference), read_records(FIX / records)


def parse_reference_text_line():
    from acts.reference_formats import parse_entryline

    return parse_entryline("e4 5\n")


def _historical_strict(block: list[str]) -> str:
    no_effect = ("DATE", "BM  ", "SM  ", "COM ")
    return hashlib.sha256(
        "".join(line for line in block if not line.startswith(no_effect)).encode()
    ).hexdigest()


def _library_strict(block: list[str]) -> str:
    from acts.reference_formats import PROFILE_VOLATILE_TAGS

    return entry_content_hash("".join(block), PROFILE_VOLATILE_TAGS)


if __name__ == "__main__":
    unittest.main()
