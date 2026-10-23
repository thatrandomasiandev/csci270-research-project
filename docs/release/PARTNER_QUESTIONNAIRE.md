# Partner environment questionnaire (TARE 1.0)

Josh: send one copy per lab. Engineering never contacts partners directly.

Lab / PI: _______________________  
Contact: _______________________  
Date: _______________________

## Cluster

1. Cluster name (what users type / docs call it):
2. Scheduler (Slurm / PBS / other) and version if known:
3. Login node access model (SSH, Duo, VPN, Jump):
4. OS and architecture on compute nodes (e.g. Rocky 8 x86_64):
5. Container runtime available? (Apptainer / Singularity / Docker / none) · version:
6. Shared filesystem type for project data (NFS / Lustre / GPFS / other):
7. Home / scratch / project paths users should use for caches (node-local preferred for SQLite):
8. Do compute nodes have outbound internet? (yes / no / restricted)
9. Max walltime / memory / cores a typical annotation job can request:
10. Module system or conda/bioconda already in use for HMMER / Infernal?

## Workload

11. Primary tools you care about first (HMMER / Infernal / other):
12. References you update (Pfam / Rfam / UniProt / other) and how you obtain them today:
13. Typical number of genomes / proteomes per update:
14. Typical size of one input (sequences or residues):
15. Do you need Nextflow, Snakemake, or plain Slurm arrays?

## Policy

16. Can unpublished sequences leave the cluster? (no is expected)
17. Preferred install path (user conda · shared module · container · pip):
18. Who must approve software installs (PI · cluster admin · both):
19. Willing to run `tare selftest` and return the JSON manifest (no sequences)? (yes / no)
20. Willing to join a beta with **full comparison ON** and report mismatches? (yes / no)

## Anything else

Notes: