# Cross-field literature for TARE's generality claim (Google Scholar Labs, 2026-10-23)

Seven Scholar Labs questions: general reuse after reference updates, security rescans,
IR collection statistics, mass-spectrometry search, astronomy catalog releases, rule-set
changes in program analysis, and an exact-replay prior-art check. Each paper is scored on:

- **S** structure match: records scored against a versioned reference, ideally with a
  reference-size (global) normalizer
- **G** gap: the field reruns everything, or settles for approximate or versioned answers
- **T** testable: public tools and data we could run
- **X** threat: already does exact incremental replay (must cite, and narrow our claim)

Scale: ●●● strong, ●● some, ● weak, – none.

## Ranked by benefit to the paper

| # | Paper | Field | S | G | T | X | Use in TARE |
|---|---|---|---|---|---|---|---|
| 1 | Hadjieleftheriou, Koudas, Srivastava. Incremental maintenance of length normalized indexes for approximate string matching. SIGMOD 2009 (c66) | IR / databases | ●●● | ●●● | ●● | – | The closest cross-field analog. An update changes IDF, a global normalizer, which forces touching many lists, so they *relax exactness* with quality guarantees. TARE gets exactness by pinning. Discussion + related work. |
| 2 | Staudinger, Piroi, Rauber. Reproducible hybrid time-travel retrieval in evolving corpora. SIGIR 2024; TimIR, ECIR 2025; Bösch 2017 thesis | IR | ●●● | ●●● | ●● | – | The IR community documents that IDF drift changes rankings when a collection updates, and solves it by versioning statistics (reproducibility, not speed). Motivation: the size-dependent-normalizer problem is general. |
| 3 | Frank et al. Spectral archives. Nature Methods 2011 (c127); Wang et al. MassIVE-KB. Cell Systems 2018 (c273) | MS proteomics | ●●● | ●● | ●●● | ● | E-values scale with database size; archives update incrementally with FDR re-estimated; MassIVE-KB reuses results and adjusts scores. The same normalizer structure in another analytical field. Candidate third domain (Comet or X!Tandem on PRIDE data). |
| 4 | Aggarwal et al. FDR: the Achilles' heel of proteogenomics. Brief. Bioinform. 2022 (c56) | MS proteomics | ●●● | ●● | ● | – | States that E-values depend on database size while target-decoy FDR is a global, cross-record statistic: a clean example of TARE's refuse/recompute class. |
| 5 | Delchambre et al. Gaia DR3 Apsis III. A&A 2023 (c123) | Astronomy | ●● | ●● | ● | – | Class probabilities are recomputed under a new global prior *without rerunning the classifier*: the same move as TARE rescaling a global normalizer instead of rerunning. Strong analogy, not a test domain. |
| 6 | Budavári, Szalay. Probabilistic cross-identification. ApJ 2008 (c210) | Astronomy | ●● | ●● | ● | – | Cross-match priors depend on source density (a global statistic); catalog releases re-run the match. Analogy. |
| 7 | Oberheide, Cooke, Jahanian. CloudAV. USENIX Security 2008 (c499) | Security | ●● | ●● | ● | – | Establishes "retrospective detection": archives rescanned after signature updates, with roughly 48-day detection lag. Motivation for the security case. Their cache is per file, not per signature delta. |
| 8 | Garcia-Contreras et al. Incremental analysis with assertion changes. LOPSTR 2019 (c18); Groher, Reder, Egyed 2010 (c58); McCall et al. SafeTAPΔ 2021 (6× when rules are added) | Program analysis | ●● | ● | ● | ●● | Closest prior work for **rules change, subject fixed**. All are white-box, inside one analyzer. TARE is black-box, tool-agnostic, byte-identical, and refuses when unsure. **Must cite if we do Semgrep.** |
| 9 | Szabó. Incrementalizing production CodeQL analyses. FSE 2023 (c44); Arzt, Bodden. Reviser. ICSE 2014 (c136) | Program analysis | ● | ● | ●● | ● | Incremental across *code* changes (the other axis). Related work; also shows that a rule-axis gap exists. |
| 10 | Majumder et al. JANUS. 2026 | Security / containers | ●● | ●● | ● | ● | Reuses layer scan reports and re-evaluates them against an evolving vulnerability DB (80.4% time cut). Records-changed axis plus a reference refresh. Related work. |
| 11 | Zhang, Cao. TokTier: exact stateful tokenization. arXiv 2026 | LLM serving | ● | ● | – | ● | The same safety pattern (splice only if a check passes, else fall back to the full reference) with a byte-identical contract. Cite for the pattern. |
| — | Dash et al. iBLAST. PLoS ONE 2021; Pedersen, Bongo. GeStore. FGCS 2017 | Bioinformatics | ●●● | – | ●●● | ●●● | Already cited and compared in the paper (iBLAST's E-value correction is tool-specific; GeStore is a baseline). No new exact prior art found. |

## What this means for the plan

1. **Novelty holds.** No paper found does black-box, tool-agnostic exact replay with a pinned
   global normalizer, inside or outside bioinformatics. The nearest exact work (iBLAST) is
   BLAST-specific and already cited.
2. **The general problem is documented in other fields.** IR (IDF drift), proteomics (E-values
   and FDR depend on database size) and astronomy (density priors, global class priors) each
   meet "a reference release changes a global statistic". They recompute, approximate (#1), or
   version statistics (#2). This supports the generality argument in the paper with citations,
   at no experimental cost.
3. **Test domain choice.**
   - Semgrep (rules change, code fixed): the most testable non-bio domain. Cite #8 and #9 as
     the closest prior work; our difference is black-box exactness with refusal.
   - Mass-spectrometry search (#3, #4): the best structural match, with a database-size E-value
     and an FDR coupling. It is bio-adjacent, so it shows generality across tools more than
     across fields.
   - IR BM25 re-scoring (#1, #2): the strongest analogy, but BM25 sums IDF over query terms, so
     there is no single pinnable flag in standard engines. Use it as motivation, not a run.
   - ClamAV: the cost model predicts no benefit (NONBIO_DOMAIN_PLAN.md). It is the "gate
     declines" case.
