# What this is

This repo holds **two separate projects**. They share a disk, not a claim.

The living claim lock — numbers, refusals, what not to invent — is [`WHAT_WE_ARE_BUILDING.md`](WHAT_WE_ARE_BUILDING.md). This file is the plain-language version of that document. Layman’s walkthrough: [`LAYMANS_MANUAL.md`](LAYMANS_MANUAL.md).

## The two objects

**1. A graded CSCI 270 artifact (Zhang).**  
A patched [STAR](https://github.com/alexdobin/STAR) RNA-seq aligner that is at least **twice as fast** as stock STAR on a locked 10-dataset Illumina bake-off (Suite B), **one thread**, **same output** (MATCH). Sealed on Mac **10/10**. Mechanism: copy-elision in `stitchWindowAligns`, plus a short stack of related hot-path patches. Do not delete `star/`. Do not invent a second timer.

**2. A research method (not graded).**  
A CLI wrapper, `python3 -m acts`, that tries to speed up an **unmodified** scientific tool by remembering what it already computed. First strategy: **record-level incremental memoization**. If the tool’s answer for each record depends only on that record, cache those answers across runs and reassemble. Keep the result only if it is **byte-identical** to a full run. The headline is a later run that pays only for unseen records.

EGAS (`python3 -m egas`) is the source-edit driver that produced the STAR speedup. It is not a third method.

## Why the research method exists

Whole-command caches (Rattle, Riker, ProcessCache, ccache) rerun the entire job when any input byte changes. Hand-built per-tool caches (Oculus, SeAlM, lab VEP wrappers) work for one program and do not generalize. Official VEP `--cache` is a **reference-data** store (transcripts, known variants), not a memo of prior user VCFs.

The gap this method is trying to own: **automatic record-level reuse for unmodified binaries**, persisted across runs, accepted only on `cmp`.

It is not “2× any program.” It is not “first automatic cache keys.” It is not Dune’s statistical audit rebranded. It is not KumQuat’s parallelism.

## What has been measured

- **STAR as an instance of the cache** is dead. BAM is not a per-read function (identity fails). Cross-sample read overlap is too rare to matter.
- **SnpEff on chr22 variants** is a live instance, timed and capped. Body MATCH on 52,638 records. CARC exclusive median **1.17×**. Startup cost caps the tool at about **1.3×** even at 100% hits.
- Record inference is **generic for VCF** (since `8540926`; subset-invariance and late-key probes in `3f47a00`). Field roles come from probes, not hard-coded ANN/LOF/NMD. The SnpEff 1.17× is that path. STAR argv still refuses identity. The next format is FASTA-in / table-out.
- The next research step is that FASTA table format, then a headline tool that is not capped the way SnpEff is.

## How to talk about it

| Audience | Say |
|----------|-----|
| Zhang | STAR ≥2×, Suite B, MATCH, one thread. |
| Ourselves / lab | Incremental record cache. STAR source 2× is the course object. |
| Do not say | “We 2× STAR without touching code.” “First statistical cache.” “VEP’s cache is our competitor.” |

## Where to go next

| If you want… | Open |
|--------------|------|
| The locked claim, numbers, and refusals | [`WHAT_WE_ARE_BUILDING.md`](WHAT_WE_ARE_BUILDING.md) |
| STAR scoreboard | [`STATUS.md`](STATUS.md) |
| STAR reproduce path | [`star/docs/REPRODUCE.md`](star/docs/REPRODUCE.md) |
| Method claim lock | [`pipeline/SCOPE.md`](pipeline/SCOPE.md) |
| Commands | [`pipeline/README.md`](pipeline/README.md) |
| Session protocol | [`AGENTS.md`](AGENTS.md) |
