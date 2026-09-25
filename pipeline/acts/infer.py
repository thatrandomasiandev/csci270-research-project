"""Independence + identity risks. LLM hook is a later rung; probes come first."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IdentityRisk:
    tool: str
    can_be_byte_identical: bool
    reasons: tuple[str, ...]


def star_identity_risk() -> IdentityRisk:
    return IdentityRisk(
        tool="STAR",
        can_be_byte_identical=False,
        reasons=(
            "BAM QNAME is not a function of the sequence; duplicate reads keep distinct names.",
            "SortedByCoordinate is a global order over all alignments, not a per-record concat.",
            "Headers, @PG lines, and multimappers couple records.",
            "Oculus (2012) was nearly lossless, not cmp-identical — the same obstacle.",
        ),
    )


def identity_risk_for_argv(argv: list[str]) -> IdentityRisk | None:
    joined = " ".join(argv).lower()
    if "star" in joined:
        return star_identity_risk()
    # VEP/SnpEff: do not auto-refuse. Full-file cmp will fail on dated headers.
    # MATCH is the record body (docs/VEP_PROTOCOL.md). Stock-vs-stock first.
    return None
