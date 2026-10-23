# OSDI '27 submission checklist (TARE)

Verified against the official Call for Papers:
https://www.usenix.org/conference/osdi27/call-for-papers
and Requirements for Authors:
https://www.usenix.org/conference/osdi27/requirements-authors
(checked 2026-10-22).

## Verified OSDI '27 facts

| Fact | Value | Source |
|---|---|---|
| Abstract registration | Tue Dec 1, 2026, 5:59 pm EST | CFP |
| Paper deadline | Tue Dec 8, 2026, 5:59 pm EST | CFP |
| Page limit (submission) | **12 pages** incl. figures/tables; unlimited references | CFP + Requirements |
| Appendices | **Not** free pages (references only unlimited) | Requirements |
| Format | USENIX 2-col, 10/12 pt, 7×9 in text block | Requirements |
| Anonymity | Double-blind; no identity by implication | Requirements |
| arXiv / prior non-peer-reviewed posting | Permitted | [CFP](https://www.usenix.org/conference/osdi27/call-for-papers) |
| System name vs arXiv | OSDI submission **must** use an anonymized system name **different** from any name used on arXiv (or other non-peer-reviewed contexts) | [CFP](https://www.usenix.org/conference/osdi27/call-for-papers): “your OSDI submission must use an anonymized name for your project or system that differs from any used in such contexts.” |
| Notification | Tue Mar 16, 2027 | CFP |
| Final papers | Thu Jun 3, 2027 (14 pages + refs if accepted) | CFP |
| Venue | Jul 7–9, 2027, Baltimore | CFP |

## System naming (arXiv vs OSDI)

- **arXiv name:** TARE (Tool Annotation Reuse, Exact). Build with `./pipeline/paper/tare/build_arxiv.sh` (real authors; refuses PENDING macros).
- **OSDI submission name:** PARE (Pin And Replay Exact). Default `\sys` in `main.tex`; figures via `TARE_SYS_NAME=PARE` (default).
- `anonymity_scan.py` fails on any leftover `\bTARE\b` in submission surfaces (paper body, `main.pdf`, included figure PDFs).

## Drafted submission-site fields

- **Title:** Pin and Replay, or Refuse: Exact Incremental Re-annotation Across Reference Database Releases
- **Track:** Research
- **Abstract:** (copy from `pipeline/paper/tare/main.tex` abstract after PENDING macros are filled; uses PARE / `\sys`)
- **Keywords (draft):** incremental computing; exact replay; reference databases; bioinformatics; systems for science
- **Topics:** storage/systems for data-intensive apps; reproducible/exact systems; OS+PL techniques for scientific computing

## Conflicts

> **JOSH FILLS THIS.** List recent collaborators, institutions, and advisors per USENIX conflict rules.

## JOSH-ONLY ACTIONS

1. Register the abstract by **2026-12-01 17:59 EST** (Duo / HotCRP account).
2. Enter conflicts on the submission site.
3. Host the anonymized artifact (tarball from `pipeline/artifact/export_tarball.sh`) on an anonymous mirror; paste URL into the submission form if required.
4. Run `./pipeline/paper/tare/finalize.sh` after W13/W8/W5x finish; confirm exit 0.
5. Press submit by **2026-12-08 17:59 EST**.
6. Any download/install still needing approval.

## Pre-submit gate (agent-complete except CARC wait)

- [ ] `finalize.sh` exit 0 (or exit 2 only while CARC still running — do not submit on exit 2)
- [x] Main text ≤ 12 pages (body ends on p12; refs unlimited; checked 2026-10-23 build)
- [ ] `check_paper_sources.py` 0 mismatches (PENDING macros expected until finalize fills W13/W8/W5x)
- [x] `anonymity_scan.py` OK on paper surfaces (includes no leftover `TARE`)
- [x] Artifact tarball builds; smoke `acts` import passes (`pipeline/artifact/export_tarball.sh`)
- [ ] No PENDING macros left in `macros_pending.tex`
- [ ] OSDI `main.pdf` uses PARE (not TARE); arXiv PDF via `build_arxiv.sh` only after macros filled

## Freeze note (submission-ready slice)

While jobs `13260162` / `13260163` / `13260165` are pending or running: no `sbatch`;
no rsync/write into those staged trees. Post-freeze: submit W12a, then W12b if alive,
then WA2 timing only if correctness PASSes; then `finalize.sh`.
