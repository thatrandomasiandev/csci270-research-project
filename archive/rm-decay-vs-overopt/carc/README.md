# CARC (USC Discovery)

Repo path on cluster: `/project2/biyik_1165/$USER/rm-decay-vs-overopt`

```bash
export CARC_NETID=<netid>
./carc/scripts/sync_to_carc.sh
ssh discovery
cd /project2/biyik_1165/$USER/rm-decay-vs-overopt
# create conda env rmdiag with requirements.txt if needed
mkdir -p carc/logs
sbatch carc/jobs/smoke_synthetic.job
sbatch carc/jobs/synthetic_protocol_sweep.job
sbatch carc/jobs/mitigation_sweep.job
```

Synthetic point-mass runs are CPU-friendly; GPU partition still works. For DM Control / PEBBLE-scale follow-ons, extend `src/` with a dmc adapter and reuse the same diagnostic CSV schema.
