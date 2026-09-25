"""Suite B PE uniqueness. Reconstructible kill-test for the STAR instance."""

from __future__ import annotations

import csv
from pathlib import Path

from acts.overlap import OverlapReport, overlap
from acts.records import DupReport, iter_fastq_pe_keys, probe_fastq_pe

REPO = Path(__file__).resolve().parents[2]
SUITEB = REPO / "star" / "bench" / "datasets" / "suiteB"
IDS = tuple(f"i{i:02d}" for i in range(1, 11))


def find_pe(folder: Path) -> tuple[Path, Path]:
    r1s = sorted(folder.glob("*_R1.fastq.gz")) + sorted(folder.glob("*_1.fastq.gz"))
    r2s = sorted(folder.glob("*_R2.fastq.gz")) + sorted(folder.glob("*_2.fastq.gz"))
    if not r1s or not r2s:
        raise FileNotFoundError(f"no PE FASTQ pair in {folder}")
    return r1s[0], r2s[0]


def probe_one(instance: str, root: Path = SUITEB) -> tuple[str, Path, Path, DupReport]:
    fq = root / instance / "fastq"
    r1, r2 = find_pe(fq)
    return instance, r1, r2, probe_fastq_pe(r1, r2)


def probe_all(root: Path = SUITEB) -> list[tuple[str, Path, Path, DupReport]]:
    return [probe_one(i, root) for i in IDS]


def write_csv(rows: list[tuple[str, Path, Path, DupReport]], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "id",
                "r1",
                "r2",
                "n",
                "n_unique",
                "unique_frac",
                "max_speedup_if_pure",
                "max_mult",
                "duplicates_rare",
            ]
        )
        for inst, r1, r2, rep in rows:
            w.writerow(
                [
                    inst,
                    r1.name,
                    r2.name,
                    rep.n,
                    rep.n_unique,
                    f"{rep.unique_frac:.6f}",
                    f"{rep.max_speedup_if_pure:.4f}",
                    int(rep.extra.get("max_mult", 0)),
                    str(rep.duplicates_rare).lower(),
                ]
            )


GROUPS = {
    "human_airway": ("i01", "i02", "i03", "i04"),
    "fly": ("i05", "i06", "i07", "i08"),
    "nfcore": ("i09", "i10"),
}


def unique_pe(instance: str, root: Path = SUITEB) -> set[str]:
    r1, r2 = find_pe(root / instance / "fastq")
    return set(iter_fastq_pe_keys(r1, r2))


def probe_overlap(
    root: Path = SUITEB,
) -> list[tuple[str, str, str, OverlapReport]]:
    """Consecutive pairs inside each organism group: can sample N+1 reuse sample N?"""
    rows: list[tuple[str, str, str, OverlapReport]] = []
    for group, ids in GROUPS.items():
        sets = {i: unique_pe(i, root) for i in ids}
        for a, b in zip(ids, ids[1:]):
            rows.append((group, a, b, overlap(sets[a], sets[b])))
    return rows


def write_overlap_csv(
    rows: list[tuple[str, str, str, OverlapReport]], dest: Path
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "group",
                "prev",
                "new",
                "n_prev",
                "n_new",
                "n_shared",
                "recall_in_new",
                "jaccard",
                "overlap_rare",
            ]
        )
        for group, prev, new, rep in rows:
            w.writerow(
                [
                    group,
                    prev,
                    new,
                    rep.n_prev,
                    rep.n_new,
                    rep.n_shared,
                    f"{rep.recall_in_new:.6f}",
                    f"{rep.jaccard:.6f}",
                    str(rep.overlap_rare).lower(),
                ]
            )
