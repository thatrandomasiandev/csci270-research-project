# CARC GPU queue dashboard

Same local Discovery queue UI as the lab dashboard: your Slurm jobs, recent finished jobs, `gpu`/`debug` depth, node types, and priority — packaged so a teammate can run it on their Mac with their own SSH identity.

**Stack:** Python 3.9+ stdlib only (no `pip install`).

## Run (live — this is the real dashboard)

1. Connect to **USC VPN**.
2. Put this in `~/.ssh/config` (see `ssh_config.example`):

```
Host discovery
  HostName discovery.usc.edu
  User YOUR_NETID
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
```

3. Confirm BatchMode SSH works (no password prompt):

```bash
ssh -o BatchMode=yes discovery 'echo ok && whoami'
```

4. Start:

```bash
git clone https://github.com/thatrandomasiandev/carc-gpu-dashboard.git
cd carc-gpu-dashboard
./run.sh
```

5. Open **http://127.0.0.1:8767**

That is live mode: the server SSHes to Discovery, runs `sinfo` / `squeue` / `sacct` / `sprio`, and serves the same UI. Auto-refresh every 30s; **Refresh** forces a new pull.

Optional (display label only — queries always use the remote `$USER` from SSH):

```bash
export CARC_NETID=YOUR_NETID
./run.sh
```

Or copy `env.example` → `.env` and edit; `run.sh` sources it.

## Environment

| Variable | Default | Meaning |
|----------|---------|---------|
| `CARC_SSH_HOST` | `discovery` | SSH Host alias / hostname |
| `CARC_NETID` | *(auto from remote)* | Display label only |
| `CARC_DASH_HOST` | `127.0.0.1` | Bind address |
| `CARC_DASH_PORT` | `8767` | HTTP port |
| `CARC_DASH_TTL` | `25` | Cache seconds between SSH pulls |
| `CARC_DASH_HISTORY_HOURS` | `48` | `sacct` lookback |
| `CARC_DASH_PARTITIONS` | `gpu,debug` | `sinfo -p` list |

```bash
python3 server.py --port 8767 --ssh-host discovery
```

## What it shows

- GPU / debug running & pending counts  
- Your current queue jobs + start estimates  
- Recently finished jobs (`sacct`)  
- Partition / GRES node summary  
- Top pending on `gpu` + `sprio` detail  

## Layout

```
server.py              # HTTP + live SSH collector (default)
run.sh                 # launcher (sources .env if present)
ssh_config.example
env.example
static/                # UI
fixtures/              # optional offline smoke data only
```

## API

| Path | Notes |
|------|--------|
| `GET /` | UI |
| `GET /api/status` | Live JSON (`?force=1` bypasses cache) |
| `GET /api/health` | Bind / mode probe |

## Offline smoke test (optional)

UI-only check with fake data — **not** what you use day to day:

```bash
./run.sh --demo
```

## Notes

- SSH uses `BatchMode=yes` (key auth + VPN; no interactive password).
- If a refresh fails, the last good snapshot is kept (“stale”).
- Port **8767** by default (avoids colliding with other local dashboards on 8765).
