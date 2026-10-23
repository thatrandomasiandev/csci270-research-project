# Finalize runbook (one command after CARC)

## Command

```bash
cd pipeline && ../pipeline/paper/tare/finalize.sh
# or from repo root:
./pipeline/paper/tare/finalize.sh
```

Requires SSH alias `discovery`. Pulls results only (never writes under
`headline_bounded`, `tare-w8`, or `tare-w5x` staged trees).

## Exit codes

| Code | Meaning |
|---|---|
| 0 | All collectors COLLECTED; macros filled; checker and anonymity clean |
| 2 | At least one experiment STILL RUNNING — safe to re-run later |
| 1 | Hard failure (missing control, FAILED collector, anonymity leak, LaTeX) |

## Per-experiment both-outcome wording (pre-written)

### W13 — headline under bounded audit

- **Holds:** Under the bounded-audit default ($s{=}299$), the median $S_g$ on the nine previously EXACT genomes is \HeadlineBoundedMedian$\times$ (95\% CI \HeadlineBoundedCIlow--\HeadlineBoundedCIhigh), with every paired B byte-identical to stock.
- **Does not hold:** The bounded-audit re-timing did not reproduce a median at least the prior $4.24\times$ claim (or failed exactness); we report the measured median and withdraw the stronger claim.

### W8 — release chain

- **Holds:** Chained updates 37.3$\rightarrow$38.2 paid back within \ReleaseChainPayback updates under the pre-registered genomes; each shipped step was byte-identical to stock.
- **Does not hold:** Cumulative payback exceeded the pre-registered bound, or a step failed exactness; we report per-step $S_g$ and do not claim chain payback.

### W5x — Table 4 on x86

- **Holds:** On exclusive EPYC, first-run $\rho$ is \BaselinesEpycRho versus stock under the locked harness.
- **Does not hold / blocked:** A system is `BLOCKED` with the recorded ptrace/seccomp error, or $\rho$ is inconclusive; Table 4 keeps the honest status cell.

### W12a — expert script

- **Holds:** Median TARE/expert ratio is \ExpertScriptRatio on five genomes (r=3), bodies byte-identical.
- **Does not hold:** Ratio or exactness fails; we keep the laptop estimate labeled indicative only.

### W12b — iSeqSearch

- **Holds:** Declared-pin TARE timing is \ISeqSearchSpeedup versus stock DIAMOND under the locked arms.
- **Does not hold / limitation:** Confirm or measured failed a second locked time; iSeqSearch timing is a stated limitation (no speed number).

### WA2 — pfscanV3

- **Holds (timing only if correctness PASS):** pfscanV3 median speedup \PfscanTiming.
- **Correctness INCONCLUSIVE (current):** 18/20 SHIP, pooled floor miss — no timing claim.
- **Does not hold:** Any UNSAFE — unrelated-program sentence withdrawn.

## Freeze note (2026-10-22)

While jobs `13260162`, `13260163`, and `13260165` are pending or running:
no `sbatch`, and no rsync/write into those three staged directories.
