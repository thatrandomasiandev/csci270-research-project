from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acts.vcf import bodies_equal, body_lines, body_map, shuffle_body, variant_key

PIPE = Path(__file__).resolve().parents[1]
FIX = PIPE / "fixtures" / "vcf_memo"
TINY = FIX / "tiny.vcf"

DUP = "22\t16050075\t.\tA\tG\t.\tPASS\t."


def _annotate(script: Path, text: str) -> str:
    proc = subprocess.run(
        [sys.executable, str(script)],
        input=text,
        text=True,
        check=True,
        capture_output=True,
    )
    return proc.stdout


class VcfMatchTests(unittest.TestCase):
    def test_header_date_does_not_break_body_match(self) -> None:
        a = TINY.read_text()
        b = a.replace("19700101", "20260101").replace("cmdline=fake", "cmdline=other")
        self.assertTrue(bodies_equal(a, b))
        self.assertNotEqual(a, b)

    def test_variant_key_ignores_id(self) -> None:
        self.assertEqual(
            variant_key("22\t1\trs1\tA\tG\t.\tPASS\t."),
            variant_key("22\t1\t.\tA\tG\t.\tPASS\t."),
        )

    def test_variant_key_keeps_full_alt(self) -> None:
        self.assertNotEqual(
            variant_key("22\t1\t.\tA\tG,T\t.\tPASS\t."),
            variant_key("22\t1\t.\tA\tG\t.\tPASS\t."),
        )

    def test_drop_duplicate_record_is_not_equal(self) -> None:
        a = TINY.read_text()
        lines = a.splitlines()
        dropped = False
        kept: list[str] = []
        for ln in lines:
            if not dropped and ln == DUP:
                dropped = True
                continue
            kept.append(ln)
        self.assertTrue(dropped)
        self.assertEqual(body_lines(a).count(DUP), 2)
        self.assertEqual(body_lines("\n".join(kept)).count(DUP), 1)
        self.assertFalse(bodies_equal(a, "\n".join(kept) + "\n"))

    def test_duplicating_a_record_is_not_equal(self) -> None:
        a = TINY.read_text()
        extra = a.rstrip("\n") + "\n" + DUP + "\n"
        self.assertFalse(bodies_equal(a, extra))

    def test_1to1_survives_shuffle(self) -> None:
        src = TINY.read_text()
        self.assertEqual(len(body_lines(src)), 4)
        out1 = _annotate(FIX / "annotate_1to1.py", src)
        out2 = _annotate(FIX / "annotate_1to1.py", shuffle_body(src, seed=7))
        self.assertTrue(bodies_equal(out1, out2))
        self.assertEqual(len(body_lines(out1)), 4)
        self.assertEqual(sum(len(v) for v in body_map(out1).values()), 4)

    def test_neighbors_fail_shuffle(self) -> None:
        src = TINY.read_text()
        out1 = _annotate(FIX / "annotate_neighbors.py", src)
        out2 = _annotate(FIX / "annotate_neighbors.py", shuffle_body(src, seed=7))
        self.assertFalse(bodies_equal(out1, out2))


if __name__ == "__main__":
    unittest.main()
