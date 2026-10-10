# Motivation evidence: re-annotation after a reference release

Written 2026-10-10. Access date for every web page below is **2026-10-10**.
This file does not edit the paper. It collects cited facts for the
introduction and for a reviewer's "does this matter?"

Labels:

- **CITED** — a sentence or figure from a page read that day (URL, DOI, or the database's own release notes).
- **MEASURED** — a number in a committed results file in this repo.
- **PROJECTED** — arithmetic from those inputs, with the formula written out. Not a timing.

A JavaScript shell whose rendered text was returned by a fetcher, and which a raw HTML download did not confirm, is marked **RENDERED**. Those figures are not used as the sole support for a claim.

## 1. Release cadence and churn

### Pfam

**CITED.** Pfam `relnotes.txt` for release 38.2
(<https://ftp.ebi.ac.uk/pub/databases/Pfam/current_release/relnotes.txt>).
The statistics table gives month/year and family count. Recent rows:

| Release | Date in the table | Families | Underlying sequence set |
|---|---|---:|---|
| 36.0 | 09/23 | 20,795 | UniProtKB reference proteomes 2022_05 |
| 37.0 | 05/24 | 21,979 | reference proteomes 2023_05 |
| 37.1 | 11/24 | 23,794 | same 2023_05 |
| 37.2 | 02/25 | 24,076 | same |
| 37.3 | 04/25 | 24,424 | same |
| 37.4 | 06/25 | 24,736 | same |
| 38.0 | 10/25 | 25,545 | reference proteomes 2025_03 |
| 38.1 | 01/26 | 27,481 | same 2025_03 |
| 38.2 | 06/26 | 30,134 | same 2025_03 |

Section 5: "Release 38.2 contains a total of 30134 families, with 2674 new families and 21 families killed since the last release." Sequence coverage of Pfamseq is 77.12% of proteins and 50.00% of residues. The notes do not say how many surviving HMMs were edited.

From 37.0 (05/24) through 38.2 (06/26) the table lists eight releases. Minor releases 37.1–37.4 and 38.1–38.2 keep the same reference-proteome snapshot. That matches the producers' own account of why minor releases exist.

**CITED.** Paysan-Lafosse et al., "InterPro in 2022," *Nucleic Acids Research* 51:D418–D427, 2023. DOI [10.1093/nar/gkac993](https://doi.org/10.1093/nar/gkac993), PMC9825450. "Like UniProtKB, InterPro follows an 8-week release cycle." Since the paper that described InterPro 81.0 (2020) there had been 9 InterPro releases, integrating 10 member-database updates, including Pfam 34.0.

**CITED.** Mistry et al. / the 2025 Pfam update, "The Pfam protein families database: embracing AI/ML," *Nucleic Acids Research*, 2025. DOI via PMC11701544 (full text XML). At the time of that manuscript the aim was still "more frequently than our current yearly release," with Pfam updates "at the same time as InterPro releases, every two months." The underlying UniProtKB reference proteomes "won't be updated for every Pfam release; that update process is a time-consuming step," and "the matches to the whole of UniProtKB will only be calculated during the InterPro release cycle."

The relnotes table shows that plan landing: after 37.0 the gaps are a few months, not a year, and several of those releases do not move the proteome snapshot.

**Not used.** The InterPro API record for Pfam 38.2 returned `releaseDate` `2026-03-26`, which disagrees with the relnotes month `06/26`. The relnotes are the source for Pfam dates.

### Cross-check against the measured 38.1 → 38.2 hash

**MEASURED.** `pipeline/results/reference_kill_r1.json`: Pfam 38.1 has `z_old` 27,481 models; 38.2 has `z_new` 30,134; `added` 2,674; `removed` 21; `shared` 27,460; `unchanged_strict` 26,082; `frac_new_unchanged_strict` 0.8655339483639742. Changed-or-new in the new release is 30,134 − 26,082 = 4,052, so the count churn is 4,052/30,134 = 0.13446605163602576.

The family count, the add count, and the kill count match section 5 of the relnotes exactly. The relnotes do not publish the rest. Of the 27,460 accessions present in both releases, 27,460 − 26,082 = 1,378 fail the strict entry hash. Those edited models, plus the 2,674 new families, are the 4,052. A cache keyed by the reference file misses on all of them. A cache keyed by the entry hash can keep the 86.6%.

### UniProt, Swiss-Prot, UniRef, UniParc

**CITED.** The UniProt Consortium, "UniProt: the Universal Protein Knowledgebase in 2025," *Nucleic Acids Research* 53:D609–D617, 2025. DOI [10.1093/nar/gkae1010](https://doi.org/10.1093/nar/gkae1010), PMC11701636. Data availability: "UniProt releases are published every 8 weeks."

**CITED.** UniProt release notes for 2026_03, 02-Sep-2026
(<https://ftp.uniprot.org/pub/databases/uniprot/current_release/relnotes.txt>):

- UniProtKB 150,006,383 entries (Swiss-Prot 575,748; TrEMBL 149,430,635)
- UniRef100 221,143,266; UniRef90 121,494,192; UniRef50 38,840,027
- UniParc 1,200,368,847 entries (1,128,904,654 active, 71,464,193 inactive)

**CITED.** Swiss-Prot statistics for the same release
(<https://web.expasy.org/docs/relnotes/relstat.html>): 575,748 entries and 209,017,843 amino acids. Since 2026_02, 247 sequences were added, the sequence of 29 existing entries was updated, and the annotations of 403,255 entries were revised. Sequence turnover on Swiss-Prot is small. Annotation revision is most of the reviewed set. That revision is curator and rule annotation, not an HMMER scan.

The FTP listing of `previous_releases/` timed out, so the 8-week claim is the 2025 paper's statement, not a count of 2024–2026 intervals measured from the directory.

### Ensembl and the VEP cache

**CITED.** Ensembl release-cycle page
(<https://www.ensembl.org/info/about/release_cycle.html>): "Ensembl data is released on an approximately three-month cycle (occasionally longer if a lot of development work is being undertaken)." The June 2026 archive
(<https://jun2026.archive.ensembl.org/info/website/archives/index.html>) says the main site "is updated with the latest data approximately every three months."

**CITED.** VEP cache documentation
(<https://www.ensembl.org/info/docs/tools/vep/script/vep_cache.html>), also the June 2026 archive of the same page: cache version 116 is for VEP 116, because "the cache (data content and structure) is generated every Ensembl release." A mismatched cache can be incompatible. The cache stores transcripts, identifiers, existing variants, regulatory regions, and SIFT/PolyPhen scores. It does not store a previous VCF's consequence calls. It is replaced, not diffed, each release.

### RefSeq

**CITED.** RefSeq release 237 distribution notes, dated August 31, 2026 in the file, FTP mtime 2026-09-04
(<https://ftp.ncbi.nlm.nih.gov/refseq/release/release-notes/RefSeq-release237.txt>). Section 5.2: "RefSeq releases occur in the first two weeks of odd-numbered months: January, March, May, July, September, November." Release 237 itself is dated 31 August 2026, which is not inside that window. The schedule sentence and this release's date are both in the file; the file does not explain the difference.

The same notes give the release size: 184,752 organisms; 6,703,188,511,506 nucleotide bases; 193,908,692,498 amino acids; 645,505,406 records.

### GTDB

**CITED.** GTDB statistics pages, release dates as printed on each page:

| Release | Date printed on that page | Bacterial genomes | Archaeal genomes |
|---|---|---:|---:|
| R06-RS202 | 27 April 2021 | 254,090 | 4,316 |
| R07-RS207 | 8 April 2022 | 311,480 | 6,062 |
| R08-RS214 | 28 April 2023 | 394,932 | 7,777 |
| R09-RS220 | 24 April 2024 | 584,382 | 12,477 |
| R10-RS226 | 16 April 2025 | 715,230 | 17,245 |

Sources: <https://gtdb.ecogenomic.org/stats/r202>, `r207`, `r214`, `r220`, `r226`. The R202–R226 dates are annual and in April.

**CITED.** Parks et al., "GTDB release 10," *Nucleic Acids Research*, 2026, PMC12807784 (text extraction of the article). R10-RS226 "released in April 2025" is "the 10th release … since its inception in November 2017." "After initial exploration of six and nine monthly releases, we have settled into an annual release in April of each year beginning with R06-RS202." The article's genome counts for R10 match the R226 statistics page (715,230 bacterial, 17,245 archaeal). It reports growth of "over 22% with each release since 2021," and 135,616 new genomes in R10-RS226.

**CITED, date not used.** Current `RELEASE_NOTES.txt`
(<https://data.gtdb.ecogenomic.org/releases/latest/RELEASE_NOTES.txt>) says R11-RS232 "comprises 901,341 genomes organised into 199,923 species clusters" and does not give a date. The R232 statistics page
(<https://gtdb.ecogenomic.org/stats/r232>) prints "GTDB release date: 15th April, 2025" and the counts 878,998 bacterial and 22,343 archaeal genomes (901,341 total), with growth from R10 of 22.90% (bacteria) and 29.56% (archaea). That date cannot sit beside R226's printed date of 16 April 2025. The R232 date line is not used. The genome counts are used, because they agree with the release notes.

## 2. Who re-annotates, and at what scale

### InterPro and UniProt

**CITED.** Paysan-Lafosse et al. 2023, as above: each InterPro release integrates member-database updates and creates entries from their signatures. The release is the moment member databases are reapplied.

**RENDERED, not load-bearing.** InterPro release notes for 109.0, rendered text of <https://www.ebi.ac.uk/interpro/release_notes/109.0/>. The raw HTML is a JavaScript shell and was not confirmed by a second download. The rendered text says InterPro 109.0 is dated 10 June 2026, includes Pfam 38.2 (30,134 signatures), and calculates protein matches for UniProtKB 2026_02 (149,810,139 proteins). Treat those counts as unchecked against the raw page.

**CITED.** MacDougall et al., "UniRule: a unified rule resource for automatic annotation in the UniProt Knowledgebase," *Bioinformatics* 36:4643–4648, 2020. DOI [10.1093/bioinformatics/btaa485](https://doi.org/10.1093/bioinformatics/btaa485), PMC7750954. "At each release of UniProtKB, every unreviewed UniProtKB/TrEMBL record is evaluated against every UniRule." Because new proteins arrive and existing attributes change, "the predictions for all unreviewed proteins have to be re-computed using the latest version of the UniRule rules and the latest data for protein attributes." For release 2020_01 that application took "∼1.5 h on 100 CPU cores" against "∼180 million unreviewed proteins." Release 2020_01 had 6,496 rules annotating 53 million proteins, 30% of 178 million records.

That 1.5 h is the rule application after protein attributes, including InterPro signatures, already exist. It is not the cost of scanning those proteins with HMMER.

### MGnify

**CITED.** MGnify Proteins documentation
(<https://docs.mgnify.org/src/docs/mgnify-proteins.html>): from just under 50 million sequences in August 2017 to "over 5.7 billion sequences." Release 2026_07 is what the FTP, the HMMER sequence search, and the proteins portal use. The Google Cloud public dataset "is still on the 2024-04 release."

**CITED.** MGnify Proteins "about" page
(<https://www.ebi.ac.uk/metagenomics/proteins/about>): "Pfam annotations are provided for the proteins by running HMMER using the Pfam significance thresholds (i.e. using --cut-ga parameter in HMMER)." The same pages do not give CPU-hours for that scan.

**CITED.** MGnify analysis pipeline v5.0
(<https://docs.mgnify.org/src/docs/analysis.html>): functional annotation runs InterProScan 75.0 (Gene3D, TIGRFAMs, Pfam, PRINTS, PROSITE patterns) and a separate HMMER 3.2.1 search against a modified KOfam (2019-04-06, based on KEGG 90.0). Assemblies additionally run eggNOG-mapper. No CPU-hour total is on that page.

### JGI IMG

**CITED.** Chen et al., "The IMG/M data management and analysis system v.6.0," *Nucleic Acids Research* 49:D751–D763, 2021. DOI [10.1093/nar/gkaa939](https://doi.org/10.1093/nar/gkaa939), PMC7778900. "Due to the size of IMG data (currently over 65 billion genes), it is impossible to upgrade all genome and metagenome annotations to the latest version of the annotation pipeline." Pipeline version is recorded per dataset because "pipeline differences can lead to annotation discrepancies." A user can request reannotation of a chosen set, which then uses the latest pipeline. As of August 2020 the same paper reports 364.3 million genes from isolate genomes and 64.66 billion metagenome genes. No CPU-hour figure for one reannotation pass is in the sections read.

### NCBI PGAP / RefSeq prokaryotes

**CITED.** Li et al., "RefSeq: expanding the Prokaryotic Genome Annotation Pipeline reach with protein family model curation," *Nucleic Acids Research* 49:D1020–D1028, 2021. DOI [10.1093/nar/gkaa1105](https://doi.org/10.1093/nar/gkaa1105), PMC7779008. "While the sequence records deposited in GenBank are updated only rarely, RefSeq regularly reannotates genomes with PGAP." Through August 2020 the RefSeq prokaryotic collection was 198,640 assemblies (their Table 1). "In the past, all RefSeq genome assemblies were reannotated once every few years." Passing 200,000 assemblies "makes re-annotation of the entire set in a short amount of time more difficult as it requires securing at once a significant amount of computing resources." The replacement is "a rolling re-annotation model in which every day the 750 oldest live assemblies are re-annotated." As of 16 August 2020, "the median annotation age for a RefSeq assembly is 4.5 months and 95% of assemblies had been annotated in the past 12 months."

**CITED.** NCBI PGAP release notes
(<https://www.ncbi.nlm.nih.gov/refseq/annotation_prok/release_notes/>). Version 6.10 (31 March 2025): "PFam release 37.1 is being used for structural and functional annotation." Version 6.11 (6 April 2026): "PFam release 38 is being used." The 6.11 note does not give a minor version. Pfam's own table had already published 37.2 (02/25) before 6.10, and 38.1 (01/26) before 6.11. The notes do not say the lag is because of cost.

### eggNOG-mapper

**CITED.** eggNOG-mapper v3 `USAGE.md` on `main`
(<https://github.com/eggnogdb/eggnog-mapper/blob/main/USAGE.md>). v3 requires eggNOG 7. A minor database bump "means the DB structure or annotation sources changed — you must re-download data." Core databases are "annotation DB ~22 GB, DIAMOND DB ~23 GB, taxonomy + GO OBO + caches < 0.4 GB → ~45 GB total." The free web service is described as the option "when you don't want to host the ~45 GB database." `--md5` appends the query MD5 as a column. The v3 usage text read here does not document `-m cache`.

**CITED.** GitHub release 2.0.5, published 2021-02-02
(<https://github.com/eggnogdb/eggnog-mapper/releases/tag/2.0.5>, body via the releases API): "`-m cache` mode and `-c FILE` options, to annotate using an annotations file with md5 hashes as cached results. A fasta file with unannotated sequences is output also, which can be used in a subsequent conventional emapper annotation run." Also "`--md5`."

No CPU-hour figure for a full eggNOG rebuild or for a typical emapper run is in those two texts. Citation counts were not collected.

### Published wall times for the scan itself

**CITED.** InterProScan 5 performance notes
(<https://interproscan-docs.readthedocs.io/en/v5/ImprovingPerformance.html>). Observed runs, all at `-cpu 16`:

| Sequences | Input size | Max memory | Run time |
|---:|---:|---:|---|
| 8,000 | 3 MB | 8 GB | 2 hrs |
| 16,000 | 6 MB | 12 GB | 4 hrs |
| 160,000 | 56 MB | 15 GB | 12 hrs |

The page calls these "observed numbers that may act as a guide." They are InterProScan with its member-database analyses, not `hmmscan` against Pfam alone.

**CITED.** InterProScan 5 FAQ
(<https://interproscan-docs.readthedocs.io/en/v5/FAQ.html>): an *E. coli* proteome of "~3.000 protein sequences" annotated "within ~1hour" on their farm in standalone mode; "16,000 protein sequences have taken ~5 hours" on 8 cores and 8 GB RAM. "InterProScan is a computationally expensive program, sometimes taking a couple of minutes to characterise a single sequence" (How to run, <https://interproscan-docs.readthedocs.io/en/v5/HowToRun.html>).

These are the only scan wall times read this session. No paper read here states a CPU-hour total for one HMMER pass over UniProtKB or over MGnify's 5.7 billion sequences. A 2026 DIAMOND clustering paper reports ~250,000 CPU hours to cluster ~19 billion sequences; that job is clustering, not profile annotation, and it is not used below.

## 3. Stale versions, and the reason given

The cleanest statements are from the producers, not from a methods section that says "we kept Pfam 31 because HMMER was too expensive." That user-paper was not found. See the gaps.

**CITED.** Chen et al. 2021, quoted in section 2. The reason they name is size: more than 65 billion genes make a full upgrade impossible. Datasets therefore keep the pipeline version they were annotated with. That is version drift by policy.

**CITED.** Li et al. 2021, quoted in section 2. The reason they name is compute: re-annotating the whole RefSeq prokaryotic set at once required more resources than they would reserve, so annotation age is managed by a queue. On 16 August 2020 the median age was 4.5 months.

**CITED.** Finn et al., "The Pfam protein families database: towards a more sustainable future," *Nucleic Acids Research* 44:D279–D285, 2016. DOI [10.1093/nar/gkv1344](https://doi.org/10.1093/nar/gkv1344), PMC4702930. The gap between Pfam 27.0 and 28.0 was "close to two years." Over that gap the sequence database grew "nearly 4-fold" and 1,445 new entries were added, and those entries "reside internally for many months." "The performance of HMMER3 is such that the limiting factor is not the calculation of matches, but rather other aspects of the database generation, particularly our internal quality control procedures." Updating pfamseq "usually results in one-third to one-half of seed alignments undergoing some kind of modification," "several weeks" of biocuration. Overlap resolution was "typically one to two months." This is the producer's cost of *making* a release. It is not a user's HMMER bill, and the authors say the HMMER search itself was not what slowed them down.

**CITED.** Paysan-Lafosse et al. 2023: "Saved or imported results will eventually become outdated as new versions of InterPro data are released." The website then warns and offers to re-run the job on the newest release. That is an acknowledgement that a stored InterPro result goes stale. It does not say users decline the re-run.

**CITED.** MGnify, section 2: the Google Cloud copy of the proteins database was still the 2024-04 release while FTP and the HMMER service were on 2026_07. The page does not give a reason beyond the update not having landed.

**CITED.** PGAP 6.10 and 6.11, section 2: the production annotator names a Pfam release and, on the two dates above, that name is behind the Pfam FTP minor version already in the relnotes. Motive not stated.

## 4. Tools that partly address it

Placement matches `pipeline/docs/REFERENCE_PRIOR_ART.md` (verdict NARROW, written 2026-10-06). This section does not reopen that verdict.

**InterProScan precalculated match lookup. CITED.** How to run, v5 docs (URL above). InterProScan "calculates an MD5 checksum for the amino acid sequence" and returns pre-calculated matches for sequences "already found in UniProtKB." Otherwise it runs the searches. `--disable-precalc` "Disables use of the precalculated match lookup service. All match calculations will be run locally." The lookup key is the query sequence. It does not split a new Pfam release into unchanged and edited models, and it does not rescale a numeric column. When the member databases move, the precomputed table is EBI's to rebuild; a local run with lookup disabled pays the full scan.

**eggNOG-mapper `-m cache`. CITED.** Release 2.0.5, quoted in section 2. The cache is an annotations file keyed by query MD5. Misses are written out for a later real search. v3 usage, also quoted above, versions the database by major.minor and requires a re-download on a minor bump. Neither text describes rescaling E-values, or reusing hits, when the eggNOG reference grows. Query-side memoization of one tool.

**iBLAST and iSeqSearch.** The readings in `REFERENCE_PRIOR_ART.md` (iBLAST, Dash et al., *PLoS ONE* 2021, DOI [10.1371/journal.pone.0249410](https://doi.org/10.1371/journal.pone.0249410); iSeqSearch, Yoo et al., *PeerJ* 2025, DOI [10.7717/peerj.19171](https://doi.org/10.7717/peerj.19171)) were not repeated this session. As that file records them: both are hand-built for tools that already emit the hits; the E-value repair is a written Karlin–Altschul or Spouge formula; growth is new sequences appended to the database. They do not infer, for an unmodified CLI, which column is a normalizer. They also do not cover a Pfam HMM that is edited rather than appended. GeStore's HMMER plugin, in the same file, does not rescale.

## 5. PROJECTED cost of one re-annotation

The model is the one in the paper's formal section. It is not a new measurement.

One invocation on \(n\) proteins, startup \(a\), per-record cost \(b\), fraction \(c\) of reference entries that are new or changed:

\[
\begin{align*}
T_{\mathrm{full}}(n) &= a + b n, \\
T_{\mathrm{reuse}}(n, c) &= a + c\, b n, \\
S(n, c) &= (1 - c)\, b n.
\end{align*}
\]

For \(N\) genomes, protein counts \(n_1,\ldots,n_N\), one invocation each (startup paid per genome):

\[
\begin{align*}
T_{\mathrm{full}}(N) &= N a + b \sum_i n_i, \\
T_{\mathrm{reuse}}(N, c) &= N a + c\, b \sum_i n_i.
\end{align*}
\]

Assumptions, copied from the paper, none of them re-measured here: \(a\) does not shrink on the smaller reference; \(b\) scales with the fraction of entries searched; merge and rescale are ignored next to those terms; per-entry cost is not uniform, which is why a timed release is still required before a speedup is claimed. If every protein is packed into one invocation, the \(N a\) term collapses to one \(a\). That packing is not how the screen was run.

**MEASURED inputs.**

- \(a = 31.959641573764316\,\mathrm{s}\), \(b = 0.7228553909794854\,\mathrm{s}/\mathrm{record}\), from `pipeline/results/headline_screen.json`, hmmscan, `--cpu 32`, `--cut_ga`, Pfam 38.2, host AMD EPYC 7542, \(N = 4192\) proteins (`BW25113.faa.gz`).
- \(c = 4052/30134 = 0.13446605163602576\), from `reference_kill_r1.json` as in section 1.

**PROJECTED, one proteome at the screen's \(n = 4192\).**

\[
\begin{align*}
b n &= 3030.2097989860026\,\mathrm{s}, \\
T_{\mathrm{full}} &= 3062.169440559767\,\mathrm{s}, \\
T_{\mathrm{reuse}} &= 439.4199888722074\,\mathrm{s}, \\
S &= 2622.7494516875595\,\mathrm{s}, \\
T_{\mathrm{full}}/T_{\mathrm{reuse}} &= 6.968662141244353.
\end{align*}
\]

The same ratio is `primary_at_n_4192` in `pipeline/results/reference_reannot_predictions.json`. If \(a\) were zero the ratio would be \(1/c = 30134/4052 = 7.436821322803553\). Startup is why the projected ratio is lower.

**PROJECTED, \(N = 5\) proteomes whose protein counts are in that same predictions file** (5,117; 4,091; 5,176; 4,197; 4,191; sum 22,772).

\[
\begin{align*}
T_{\mathrm{full}} &= 16620.66117125366\,\mathrm{s}\ (4.617\,\mathrm{h}), \\
T_{\mathrm{reuse}} &= 2373.2254570768714\,\mathrm{s}\ (0.659\,\mathrm{h}), \\
T_{\mathrm{full}}/T_{\mathrm{reuse}} &= 7.00340590131943.
\end{align*}
\]

That ratio sums the five runs and then divides. The file's `primary_mean` of 6.99924607283027 is the unweighted mean of the five per-genome ratios. Both are projections. Neither is a timed 38.1→38.2 run. The paper marks that timing pending.

Do not multiply \(a\) and \(b\) by UniProtKB's 150,006,383 entries or by MGnify's 5.7 billion sequences. Those constants were fit on one 4,192-protein hmmscan. InterProScan's own table is a different program and is already super-linear in the three rows above (8,000 sequences in 2 h; 160,000 in 12 h, not in 40 h).

## 6. Gaps

- No CPU-hour total, read this session, for HMMER `--cut_ga` over UniProtKB or over MGnify Proteins. The UniRule 1.5 h figure is the rule engine, not that scan.
- No methods paper found that says a lab kept a named old Pfam because re-running was too expensive. The direct "too big to refresh" quotes are IMG and RefSeq/PGAP, about their own corpora.
- Finn et al. 2016 say HMMER match calculation was *not* the Pfam release bottleneck. A reviewer can use that sentence against a claim that the producer's pain is the search. The user-side evidence is IMG, the PGAP rolling queue, and the InterProScan wall times, not Finn's release engineering.
- InterPro's current release interval was not counted from a machine-readable list. The 8-week sentence is the 2023 paper. The 2025 Pfam paper still described a future two-month InterPro cadence. The relnotes show Pfam's own recent spacing; they are not an InterPro release calendar.
- UniProt "every 8 weeks" was not checked against the FTP release directory (listing timed out).
- GTDB R11's date on the statistics page conflicts with R10's date. Counts are used; the R11 date is not.
- InterPro 109.0's match counts are RENDERED only.
- eggNOG-mapper citation counts and a published emapper CPU-hour were not collected.
- iBLAST and iSeqSearch were not re-read; section 4 points at the prior-art file.

## 7. Suggested introduction paragraph

Not inserted into the paper.

Reference databases are re-released on a published calendar, and the annotation that depends on them is redone or allowed to age. UniProt's 2025 paper says a release every eight weeks; InterPro's 2022 paper says it follows that eight-week cycle; Ensembl's release cycle is about three months, and the VEP cache is regenerated for each of those releases; RefSeq's current distribution notes still schedule a flat-file release in each odd-numbered month; GTDB's statistics pages show an April release each year from 2021 through 2025. The collections are large enough that a full refresh is treated as optional: IMG stated that more than 65 billion genes made it impossible to move every dataset to the latest pipeline, and RefSeq adopted a rolling re-annotation of the 750 oldest prokaryotic assemblies per day because redoing the whole set at once cost more compute than they would reserve, leaving a median annotation age of 4.5 months in August 2020. On the one Pfam pair we hashed, release 38.2's own notes account for 2,674 new families and 21 killed ones, and 26,082 of the 30,134 models are unchanged under a strict entry hash, so a cache of the reference file misses while most of the models do not need to be searched again.
