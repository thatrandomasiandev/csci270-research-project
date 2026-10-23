"""Declared-pin confirmation pass rule (W12b).

Job 13260166 refused correctly after replay (IC2 pad_hit) but the old
pass rule required a replay body, which REFUSE never writes.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "iseqsearch_timing.py"


@pytest.fixture(scope="module")
def iseq():
    spec = importlib.util.spec_from_file_location("iseqsearch_timing", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_known_good_refusal_passes(iseq):
    """Correct declared-pin path: replay then REFUSE, no shipped body."""
    update = {
        "decision": "REFUSE",
        "why": "IC2 neighbor out: pad_hit",
        "post_replay_refuse": True,
        "replay_body": False,
        "difference_class": None,
        "body_written": False,
        "phases": {"replay_s": 1.0, "ic2_neighbor_s": 1.1},
    }
    assert iseq.confirmation_declared_pass(update) is True
    assert iseq.post_replay_refuse(
        update["decision"], update["why"], update["phases"]
    )


def test_known_bad_ship_fails(iseq):
    """A SHIP with a body is not the declared-pin confirm outcome."""
    update = {
        "decision": "SHIP",
        "why": "exact replay under pinned normalizer",
        "post_replay_refuse": False,
        "replay_body": True,
        "difference_class": {"shared_byte_identical": 1},
        "body_written": True,
        "phases": {"replay_s": 1.0},
    }
    assert iseq.confirmation_declared_pass(update) is False


def test_refuse_pin_without_replay_fails(iseq):
    update = {
        "decision": "REFUSE_PIN",
        "why": "total_entry_length: no knob",
        "post_replay_refuse": False,
        "replay_body": False,
        "body_written": False,
        "phases": {},
    }
    assert iseq.confirmation_declared_pass(update) is False
