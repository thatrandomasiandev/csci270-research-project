"""Lock the measured_v2 draw against UNRELATED_SHIP_PROTOCOL_V2.md."""
from __future__ import annotations

import random
import unittest
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
REPO = PIPE.parent
PROTOCOL = PIPE / "docs" / "UNRELATED_SHIP_PROTOCOL_V2.md"
PILOT = PIPE / "results" / "unrelated_ship" / "pilot.json"
MEASURED = PIPE / "results" / "unrelated_ship" / "measured.json"
GENOMES = (
    PIPE / "data" / "recurrence" / "A"
    if (PIPE / "data" / "recurrence" / "A").is_dir()
    else REPO.parent / "ACTS" / "pipeline" / "data" / "recurrence" / "A"
)
# Shared checkout path used when the worktree has no data mirror.
if not GENOMES.is_dir():
    GENOMES = Path("/Users/joshuaterranova/Desktop/CSCI270/ACTS/pipeline/data/recurrence/A")

LOCKED = [
    "GCF_004377995.2_protein.faa.gz",
    "GCF_055556535.1_protein.faa.gz",
    "GCF_002853805.1_protein.faa.gz",
    "GCF_904866455.1_protein.faa.gz",
    "GCF_052050745.1_protein.faa.gz",
    "GCF_032384295.1_protein.faa.gz",
    "GCF_048568975.1_protein.faa.gz",
    "GCF_041235215.1_protein.faa.gz",
    "GCF_048404355.1_protein.faa.gz",
    "GCF_003722195.1_protein.faa.gz",
    "GCF_018415995.1_protein.faa.gz",
    "GCF_900196535.2_protein.faa.gz",
    "GCF_002058765.1_protein.faa.gz",
    "GCF_036498065.1_protein.faa.gz",
    "GCF_015571655.1_protein.faa.gz",
    "GCF_037231045.1_protein.faa.gz",
    "GCF_024918035.1_protein.faa.gz",
    "GCF_001900595.1_protein.faa.gz",
    "GCF_049354865.1_protein.faa.gz",
    "GCF_057812745.1_protein.faa.gz",
]


class MeasuredV2DrawTests(unittest.TestCase):
    def test_protocol_locks_floors_and_seed(self) -> None:
        text = PROTOCOL.read_text()
        self.assertIn("20261272", text)
        self.assertIn("38120", text)
        self.assertIn("1906", text)
        for name in LOCKED:
            self.assertIn(name, text)

    def test_draw_matches_preregistration(self) -> None:
        if not GENOMES.is_dir():
            self.skipTest(f"missing genome pool {GENOMES}")
        import json

        pilot = json.loads(PILOT.read_text())
        measured = json.loads(MEASURED.read_text())
        excluded = (
            set(pilot["genomes_drawn"])
            | set(measured["genomes_drawn"])
            | {"GCF_001513615.1_protein.faa.gz"}
        )
        names = sorted(path.name for path in GENOMES.glob("*.faa.gz"))
        self.assertEqual(len(names), 100)
        rest = [name for name in names if name not in excluded]
        drawn = random.Random(20261272).sample(rest, 20)
        self.assertEqual(drawn, LOCKED)
        self.assertFalse(set(drawn) & excluded)


if __name__ == "__main__":
    unittest.main()
