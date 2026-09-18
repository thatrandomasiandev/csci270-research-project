# CARC GPU dashboard (local)

Live web UI for Discovery `gpu` / `debug` queue depth, your `rmdiag_*` jobs, and priority.

**Shareable / reproducible copy** (no hardcoded netid, demo mode, zip-ready):  
`tools/carc-gpu-dashboard/` in the repo root — also packaged as `tools/carc-gpu-dashboard.zip`.

## Run

1. USC VPN on
2. `ssh discovery` works from this Mac
3. From the repo root:

```bash
python3 carc/dashboard/server.py
```

4. Open **http://127.0.0.1:8767**

(Port **8767** so it does not collide with the LIRALab dashboard on 8765.)

Auto-refreshes every 30s. Click **Refresh** for a forced pull.
