"""Equivalence-gated 2× search — reusable STAR protocol, not a 2×-anything compiler."""

from egas.amdahl import AmdahlResult, evaluate_amdahl
from egas.decide import Decision, DecideInput, decide

__version__ = "0.1.0"
__all__ = [
    "AmdahlResult",
    "Decision",
    "DecideInput",
    "decide",
    "evaluate_amdahl",
]
