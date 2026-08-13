# pc-energy-optimizer

Background agent for Windows PCs on the tailnet. Lets Home Assistant put a PC
to sleep over HTTP (with guardrails), and exposes status/health endpoints.
Future: energy telemetry into the homelab pipeline (Grafana Cloud/Alloy).

## How it works

A single Python process (stdlib HTTP server + psutil) runs hidden at logon via
Task Scheduler, bound to the PC's Tailscale IP. Tailscale is the security
boundary; requests need a per-PC bearer token (except `/health`).

## API

| Endpoint | Auth | Response |
|---|---|---|
| `GET /health` | none | `200 {"status": "ok", "version": ...}` |
| `GET /status` | Bearer | `200 {"hostname", "idle_s", "cpu_percent", "uptime_s", "version"}` |
| `POST /sleep` | Bearer | `202` sleeping (after ~3s delay) or `409` refused with reasons |

`POST /sleep` body is optional: `{"force": true}` bypasses the guardrails.
Refusal reasons: `user_active` (input within `min_idle_minutes`) and
`cpu_high` (above `max_cpu_percent`).

## Install (per PC)

```powershell
git clone <repo> ; cd pc-energy-optimizer
copy config.example.toml config.toml
# edit config.toml: bind_host = this PC's Tailscale IP, token = output of:
python -c "import secrets; print(secrets.token_urlsafe(32))"
powershell -ExecutionPolicy Bypass -File install\install-task.ps1
```

The installer runs `uv sync`, registers a hidden at-logon task running
`.venv\Scripts\pythonw.exe -m pc_energy_optimizer` (restart-on-failure, single
instance), starts it, and polls `/health`.

Uninstall: `install\uninstall-task.ps1`.

Notes:
- The agent retries binding for up to 10 minutes at startup, because at logon
  the Tailscale IP may not be up yet.
- Sleep uses `SetSuspendState(bHibernate=FALSE)`. If hibernation is enabled,
  Windows still honors suspend for this call, but for strict behavior run
  `powercfg /h off`. Startup logs `powercfg /a` into `logs\agent.log` so you
  can see what this PC supports.
- Logs: `logs\agent.log` (rotating, 1 MB x 5).

## Home Assistant

Add the token to HA `secrets.yaml` as e.g. `desktop_pc_energy_token: "Bearer <token>"`,
then per PC (replace `100.64.0.10` with the PC's Tailscale IP):

```yaml
rest_command:
  desktop_pc_sleep:
    url: "http://100.64.0.10:8787/sleep"
    method: post
    content_type: application/json
    payload: '{"force": false}'
    headers:
      Authorization: !secret desktop_pc_energy_token

sensor:
  - platform: rest
    name: "Desktop PC Status"
    resource: "http://100.64.0.10:8787/status"
    headers:
      Authorization: !secret desktop_pc_energy_token
    value_template: "{{ (value_json.idle_s / 60) | round(1) }}"
    unit_of_measurement: "min"
    json_attributes:
      - cpu_percent
      - uptime_s
      - idle_s
      - hostname
    scan_interval: 60
```

The sensor state is minutes idle; automations can call `rest_command.desktop_pc_sleep`
and treat a 409 as "PC was busy".

## Monitoring (onboarding convention)

Add an Uptime Kuma HTTP monitor per PC: `http://<tailnet-ip>:8787/health`,
keyword `ok`, 60s interval, on the `home` status page.

## Development

```powershell
uv sync
uv run python tests/run_all.py     # framework-free; passes when it prints OK: all
uv run python -m pc_energy_optimizer   # foreground run (reads .\config.toml)
```

Manual verification checklist (not covered by tests):
1. Real sleep+wake: `curl -X POST -H "Authorization: Bearer <t>" -d '{"force":true}' http://<ip>:8787/sleep` — PC should suspend ~3s later; wake and check the log.
2. Bind retry: stop Tailscale, start the agent, confirm retry lines in the log, start Tailscale, confirm it binds.

## Git

This repo is deliberately `main`-only with feature branches — no `staging`
branch (fresh solo repo, no CI/CD pipeline). See CLAUDE.md.
