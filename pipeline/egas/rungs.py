"""Typed transform classes. Free-form rewrites are out of scope."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RungClass(str, Enum):
    T1_COPY = "T1_COPY"
    T2_DEAD_PATH = "T2_DEAD_PATH"
    T3_CLOSED_FORM = "T3_CLOSED_FORM"
    T4_BUILD = "T4_BUILD"
    T5_ALGORITHM = "T5_ALGORITHM"


@dataclass(frozen=True)
class Rung:
    id: str
    cls: RungClass
    title: str
    automated: bool
    hint: str
    symbol: str = ""


# Patterns that actually produced STAR ≥2×. Used to write a propose plan.
STAR_KNOWN: tuple[Rung, ...] = (
    Rung(
        "star_s1_bounded_copy",
        RungClass.T1_COPY,
        "Bounded Transcript exon-row copy",
        False,
        "Stock copied 20 unused padding rows; copy nExons+1 clamped.",
        "Transcript",
    ),
    Rung(
        "star_s2_s3_ref_undo",
        RungClass.T1_COPY,
        "stitchWindowAligns pass-by-ref + undo",
        False,
        "Remove per-node full object copies; stitch in place and undo on fail.",
        "stitchWindowAligns",
    ),
    Rung(
        "star_s3b_dead_stitch",
        RungClass.T2_DEAD_PATH,
        "Pre-skip stitches that hit −1000001/−1000002",
        False,
        "~74% of stitch attempts die on two integer compares.",
        "stitchWindowAligns",
    ),
    Rung(
        "star_s4_tls_adopt",
        RungClass.T1_COPY,
        "TLS leaf + adoptStitchState",
        False,
        "Leaf finalize without empty STL clone.",
        "stitchWindowAligns",
    ),
    Rung(
        "star_s7_closed_form",
        RungClass.T3_CLOSED_FORM,
        "Closed-form L * scoreMatch",
        False,
        "scoreMatch is constexpr 1; stock looped.",
        "stitchAlignToTranscript",
    ),
    Rung(
        "star_s8_move_assign",
        RungClass.T1_COPY,
        "Leaf insert via std::move",
        False,
        "Avoid cloning STL containers on every recorded transcript.",
        "stitchWindowAligns",
    ),
    Rung(
        "star_verified_patch",
        RungClass.T1_COPY,
        "Apply star-2x-verified.patch (S1–S8)",
        True,
        "One already-landed source rung; then T4 PGO/jemalloc via the STAR build script.",
        "stitchWindowAligns",
    ),
    Rung(
        "star_t4_pgo_jemalloc",
        RungClass.T4_BUILD,
        "PGO + LTO + jemalloc",
        True,
        "Build extras. Score separately from S1–S8. WITH_PGO=1 WITH_JEMALLOC=1.",
    ),
)


def propose_from_symbol(symbol: str, fraction: float) -> list[Rung]:
    """Generic T1–T3 brief for a hot legal symbol. Not a patch."""
    low = symbol.lower()
    out: list[Rung] = []
    if any(k in low for k in ("copy", "clone", "assign", "transcript", "stitch", "insert")):
        out.append(
            Rung(
                f"t1_{symbol}",
                RungClass.T1_COPY,
                f"Copy/API waste in {symbol}",
                False,
                f"{symbol} is {fraction:.1%} of time. Look for by-value objects, padding copies, "
                "STL clone on the success path, missing std::move.",
                symbol,
            )
        )
    out.append(
        Rung(
            f"t2_{symbol}",
            RungClass.T2_DEAD_PATH,
            f"Dead-path skip in {symbol}",
            False,
            f"Profile early-exit rates. If most calls fail a cheap predicate, hoist it.",
            symbol,
        )
    )
    if any(k in low for k in ("score", "loop", "accum", "sum")):
        out.append(
            Rung(
                f"t3_{symbol}",
                RungClass.T3_CLOSED_FORM,
                f"Closed form in {symbol}",
                False,
                "Replace a constant-iteration score loop with a multiply if the paper/code allows.",
                symbol,
            )
        )
    if not out:
        out.append(
            Rung(
                f"t1_{symbol}",
                RungClass.T1_COPY,
                f"Inspect {symbol} for copy and API waste",
                False,
                f"{symbol} is {fraction:.1%} — start with object copies before inventing a new algorithm.",
                symbol,
            )
        )
    return out


def generic_t4() -> tuple[Rung, ...]:
    return (
        Rung(
            "t4_o3_lto",
            RungClass.T4_BUILD,
            "Rebuild stock flags: -O3 -flto",
            True,
            "No-source-change. Will not 2× a copy-bound C++ hot path by itself.",
        ),
        Rung(
            "t4_pgo",
            RungClass.T4_BUILD,
            "Profile-guided optimize on diagnostic workloads only",
            True,
            "Train PGO on development inputs; verify on held-out. Never claim a PGO-only 2× on the train set.",
        ),
        Rung(
            "t4_jemalloc",
            RungClass.T4_BUILD,
            "Link jemalloc if the allocator shows in the illegal remainder",
            True,
            "Score separately from algorithmic rungs.",
        ),
    )
