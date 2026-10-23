# A non-biology domain for TARE: semantics review and gated plan (2026-10-23)

Goal: show that TARE's method is a general systems technique, not a HMMER trick, without
risking the December 8 OSDI deadline. Every phase ends in a gate; a failed gate produces a
paper sentence, not a redesign.

## 1. ClamAV semantics review (no runs)

Model: records = files, entries = signatures, releases = daily.cvd versions (daily updates,
shipped as small CDIFF deltas). Sources: clamscan(1), docs.clamav.net (Scanning, Allow Lists),
ClamAV blog on CVDs/CDIFFs.

| Behavior | How it shows up | TARE class | Handling |
|---|---|---|---|
| Default reports only the **first** matching signature per file | Which name is printed depends on engine order across entries | order / neighbor (F2/F8) | Refuse. Only `--allmatch` (`-z`) makes output per (file, signature). |
| `--allmatch` | One line per (file, signature) | entry-local | Replay candidate |
| Allow lists `.fp` / `.sfp` (file hash) | A new allow entry silences that file for **every** signature | cross-entry, global | `--invalidate-group`: an allow-list change rescans its files |
| `.ign2` (ignore a named signature) | Silences one named signature | entry-addressed | Treat as a change to that entry |
| Summary `Known viruses: N` | Changes with database size every release | size-dependent field (like HMMER's Z), summary only | `--no-summary`, or a pinned or rescaled summary line |
| Archive limits (`--max-filesize`, `--max-scansize`) | Same per file across releases | constant knob | Part of argv; keyed in the namespace |
| Bytecode signatures, PUA options | Signatures that run code; options that toggle categories | argv-dependent | Fixed argv; bytecode entries treated like other entries |

**The decisive issue is cost, not semantics (Amdahl first).** HMMER's work scales with
records × models, so replaying 13% of the models costs about 13% and gives about 4×. ClamAV
matches every signature at once with multi-pattern automata (Aho-Corasick and Wu-Manber), so
per-file cost is driven by reading, unpacking and parsing bytes, and is only weakly tied to the
number of signatures. Database load is the part that scales with signature count, and a
production clamd daemon already loads once. Prediction: replaying a daily delta still pays most
of a full scan, so the speedup is small (roughly 1.1–2×). TARE's own break-even gate,
f > (1 − c)/a, should then decline: a (the share of cost proportional to entries) is small.

**Power problem:** a benign corpus gives almost no detections, so an exactness test would be
blind (few observable rows). A malware corpus on a university cluster is a policy and safety
risk. Do not use live malware.

**Verdict:** ClamAV is a poor domain in which to ship a speedup. It is a good domain for showing
the cost model predicts when TARE should *not* replay, and for showing that TARE's gate declines
on its own. Both can be measured on benign files with no detections needed.

## 2. A domain predicted to benefit: rule-based static analysis (Semgrep)

Model: records = source files, entries = rules (the public semgrep-rules repository, thousands of
rules with git history, so each commit is a release), output = JSON findings per (file, rule).
Rules are matched largely independently, so cost should scale with the number of rules.
Findings are plentiful on open-source code, so power is not an issue. No database-size field is
expected (identity normalizer, TARE's no-pin path). Couplings to check in the pilot: `nosemgrep`
comments (rule-addressed), cross-rule deduplication, max-findings limits, output ordering,
the timeout and memory policy per rule, and taint rules spanning files.

Novelty check needed before building: incremental static analysis usually reuses work across
*code* changes (diff-aware scans). Reuse across *rule-set* releases with an exactness guarantee
looks less studied. Confirm with a literature search before any claim.

## 3. Gated plan

| Phase | Work | Where | Time | Gate (pass → next phase; fail → the stated result) |
|---|---|---|---|---|
| G0 | This review; novelty search for rule-release incrementality | desk | 0.5 day | Prior exact system found → cite it and narrow the claim |
| G1 cost-shape probe | For ClamAV and Semgrep: time the tool on a fixed corpus with entry subsets f ∈ {0, 0.01, 0.1, 0.5, 1}, r = 3; fit T(f) = c + a·f; compute the predicted S at a real release's changed fraction | laptop (shape only), then one CARC node | 1–2 days | Semgrep predicted S ≥ 2 → G2. ClamAV: record a, c and the gate's decision as the "declines" case. Semgrep S < 2 → write the model-predicted limitation and stop. |
| G2 pilot | Semgrep on disjoint repos and releases (own seed): stock-vs-stock identity, positive control (known-good replay ships), negative control (injected dropped finding must refuse), inference reports no pin, coupling list above checked | laptop | 2–3 days | Any blind check or a failed control → fix the test once; a second failure → limitation |
| G3 pre-register + measured | Fresh repos and three consecutive rule releases; exclusive EPYC node; alternating stock/TARE r = 3; exactness on every line; ClamAV gate-decline run on the same node | CARC | 3–4 days wall | Report what comes out, either way |
| G4 paper | Half a page "Beyond biology": the cost model predicts both outcomes; Semgrep ships (or not) with S, exactness, controls; ClamAV declines by its own gate | hub | 1 day | — |

Seeds: 20261321–20261329 (check the repo for collisions first). Installs and downloads need
Josh's approval first (ClamAV through Homebrew plus a signature download of a few hundred MB;
Semgrep through pip): state the name, source and size.

## 4. Why this helps the paper either way

- Semgrep ships → a third domain, outside biology, with a measured speedup: the method is general.
- Semgrep does not ship, or ClamAV declines → the cost model predicted it in advance from a
  cheap probe, and TARE's gate refused on its own. That is evidence the model is predictive and
  the system is safe beyond biology, which is a claim reviewers rarely see backed by data.
- No outcome requires a redesign or threatens December 8. G1 alone (2 days) decides
  whether the bigger investment is worth making.

## 5. Runs in parallel

The shared-probe change (learn the contract once per tool, argv and release, and reuse it
across genomes) proceeds independently. It addresses W5x's 4.20× first-run cost on small
inputs and does not depend on any gate here.
