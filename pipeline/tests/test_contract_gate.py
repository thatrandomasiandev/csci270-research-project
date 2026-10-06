"""Guard: a pinned byte MATCH satisfies the locked whitespace MATCH of the same type.

The 2026-10-05 savings jobs halted with STOP_CONTRACT because the runner
required match_ws even after the layout probe had pinned column widths and
switched the check to byte equality. Byte equality of body lines implies
whitespace-normalized equality for both order and multiset (ws_line is a
function of each line). An unpinned contract with match_ws false does not.
"""

from __future__ import annotations

import importlib.util
import random
import sys
import unittest
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))
sys.path.insert(0, str(PIPE / "scripts"))

from acts.infer_fasta import TableContract, contract_satisfies  # noqa: E402
from acts.table import tables_match  # noqa: E402

FIXTURE = PIPE / "tests" / "fixtures" / "savings" / "A_hmmsearch.contract.json"


def _contract(**overrides: object) -> TableContract:
    raw: dict = {
        "kind": "fasta",
        "argv": ["tool"],
        "query_col": 0,
        "desc_cols": [],
        "produced_cols": [1],
        "delim": "ws",
        "match": "order",
        "n_cols": 2,
        "match_ws": False,
        "layout": {"delim": "ws", "pinned": False, "columns": []},
    }
    raw.update(overrides)
    return TableContract(**raw)


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "run_hmmer_savings", PIPE / "scripts" / "run_hmmer_savings.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ContractSatisfiesTests(unittest.TestCase):
    def test_byte_equality_implies_whitespace_equality_same_match_type(self) -> None:
        """The reason a pinned contract may stand in for whitespace MATCH.

        Order is list equality of body lines; multiset is Counter equality.
        Both are preserved by ws_line. The converse is false: padding that
        whitespace normalization erases fails the byte check.
        """
        rng = random.Random(20261006)
        lines = [
            " ".join(rng.choice(["aa", "b", "ccc"]) for _ in range(4))
            for _ in range(5)
        ]
        body = "# meta stays out\n" + "\n".join(lines) + "\n\n"
        shuffled = "# other meta\n" + "\n".join(reversed(lines)) + "\n"
        for match in ("order", "multiset"):
            self.assertTrue(tables_match(body, body, match, match_ws=False))
            self.assertTrue(tables_match(body, body, match, match_ws=True))
        self.assertTrue(tables_match(body, shuffled, "multiset", match_ws=False))
        self.assertTrue(tables_match(body, shuffled, "multiset", match_ws=True))
        self.assertFalse(tables_match(body, shuffled, "order", match_ws=False))
        one = lines[0] + "\n"
        one_padded = lines[0].replace(" ", "   ", 1) + "\n"
        self.assertNotEqual(one, one_padded)
        for match in ("order", "multiset"):
            self.assertFalse(tables_match(one, one_padded, match, match_ws=False))
            self.assertTrue(tables_match(one, one_padded, match, match_ws=True))
        # Distinct lines that collapse under split() do not break the forward implication.
        collapsed_a = "a  b\na b\n"
        collapsed_b = "a b\na  b\n"
        self.assertTrue(tables_match(collapsed_a, collapsed_b, "multiset", match_ws=False))
        self.assertTrue(tables_match(collapsed_a, collapsed_b, "multiset", match_ws=True))

    def test_pinned_contract_with_the_right_match_passes(self) -> None:
        for match in ("order", "multiset"):
            ok, reason = contract_satisfies(
                _contract(match=match, match_ws=False, layout={"pinned": True}),
                match,
            )
            self.assertTrue(ok, reason)
            self.assertIn("pinned byte MATCH", reason)

    def test_unpinned_match_ws_false_is_rejected(self) -> None:
        ok, reason = contract_satisfies(
            _contract(match="order", match_ws=False, layout={"pinned": False}),
            "order",
        )
        self.assertFalse(ok)
        self.assertIn("unpinned", reason)

    def test_whitespace_contract_still_passes(self) -> None:
        ok, reason = contract_satisfies(
            _contract(match="multiset", match_ws=True, layout={"pinned": False}),
            "multiset",
        )
        self.assertTrue(ok, reason)
        self.assertIn("whitespace-normalized MATCH", reason)

    def test_wrong_match_type_is_rejected_pinned_or_not(self) -> None:
        for pinned in (True, False):
            for match_ws in (True, False):
                ok, reason = contract_satisfies(
                    _contract(
                        match="order",
                        match_ws=match_ws,
                        layout={"pinned": pinned},
                    ),
                    "multiset",
                )
                self.assertFalse(ok, (pinned, match_ws, reason))
                self.assertIn("!= expected", reason)

    def test_carc_hmmsearch_contract_passes_the_gate(self) -> None:
        """Job 12629414 inferred this contract at f8e3685, then STOP_CONTRACT.

        traced_files (34 host library paths) are dropped from the fixture.
        """
        contract = TableContract.load(FIXTURE)
        self.assertEqual(contract.traced_files, [])
        self.assertEqual(contract.decision, "OK")
        self.assertEqual(contract.reason, "probe passed")
        self.assertEqual(contract.match, "multiset")
        self.assertFalse(contract.match_ws)
        self.assertTrue(contract.layout.get("pinned"))
        ok, reason = contract_satisfies(contract, "multiset")
        self.assertTrue(ok, reason)
        self.assertFalse(contract_satisfies(contract, "order")[0])

    def test_runners_use_the_shared_predicate(self) -> None:
        runner = _load_runner()
        self.assertIs(runner.contract_satisfies, contract_satisfies)
        import confirm_run

        self.assertIs(confirm_run.contract_satisfies, contract_satisfies)

    def test_pinned_match_is_byte_match_with_no_whitespace_fallback(self) -> None:
        runner = _load_runner()
        contract = _contract(match="multiset", match_ws=False, layout={"pinned": True})
        stock = "q1  1.0  hit\nq2  2.0  hit\n"
        padded = "q2   2.0  hit\nq1  1.0  hit\n"
        self.assertTrue(tables_match(stock, padded, "multiset", match_ws=True))
        self.assertFalse(runner.do_match(padded, stock, contract))
        self.assertTrue(runner.do_match(stock, "q2  2.0  hit\nq1  1.0  hit\n", contract))


if __name__ == "__main__":
    unittest.main()
