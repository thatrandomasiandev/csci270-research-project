# Staging note (2026-10-20)

Freeze commit for measured_v2: `83f9bf5ffaa85ba150784c1485dd5056b476ead2`.

CARC jobs:
- array `tare_a_v2` jobid `13259447` (`--array=0-19`)
- aggregate `tare_a_v2agg` jobid `13259448` (`afterok:13259447`)

Do not `rsync --delete` over `/project2/.../tare-exp-a/` without
excluding `pfscan/` and `logs/`. A full `--delete` on 2026-10-20 removed
the previously built `pfscan/bin/pfscanV3`; it was restored from
`/scratch1/jjt_373/tare-exp-a/build/src/C/pfscanV3` (built 2026-10-18)
before submit. No second source download.
