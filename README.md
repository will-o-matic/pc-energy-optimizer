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
| `GET /health` | none | `200 {"status": "ok", "version": ..., "features": [...]}` |
| `GET /status` | Bearer | `200 {"hostname", "idle_s", "cpu_percent", "uptime_s", "since_wake_s", "estimated_watts", "gpu_watts", "energy_kwh", "version"}` |
| `POST /sleep` | Bearer | `202` sleeping (after ~3s delay) or `409` refused with reasons |

`POST /sleep` body is optional: `{"force": true}` bypasses the guardrails.
Refusal reasons: `user_active` (input within `min_idle_minutes`),
`recently_woke` (less than `wake_grace_minutes` + `min_idle_minutes` since
resume or agent start), `cpu_high` (above `max_cpu_percent`) and
`power_request` (something holds a Windows power request of a type in
`power_request_types`; the reason lists them as `{"type", "kind", "name",
"reason"}`). The agent's own requests and anything matching
`ignore_power_requests` are skipped.

`power_request` reads `powercfg /requests`, which **needs an elevated
process**. The at-logon task runs non-elevated, so by default the check
can't read requests: it logs a warning and is skipped (never refuses).

`features` in `/health` lets clients detect what an agent supports:
`since_wake`, `webhook`, `power_estimate`, `power_request`.

### Power estimate

A background thread samples CPU (and NVIDIA board power via `nvidia-smi`,
when present) every `sample_seconds` and estimates whole-system wall draw:

    estimated_watts = base_watts + cpu_watts * (cpu%/100) ** cpu_exponent
                      + gpu_watts / psu_efficiency     (or gpu_fallback_watts)

`gpu_watts` is the measured board power, or `null` without `nvidia-smi`.
`energy_kwh` integrates the estimate while awake (sleep gaps add nothing)
and is persisted to `state\energy.json` every ~5 minutes and before each
sleep, so it only resets if that file is lost. The `[power]` constants are
meant to be calibrated against a wall meter.

### Webhook push

With `[webhook].url` set, the agent POSTs JSON events (fire-and-forget;
failures are only logged and never affect sleep):

```json
{"event": "started", "hostname": "DESK", "version": "0.2.0", "ts": "2026-10-20T07:18:03-04:00"}
{"event": "sleeping", ..., "forced": false}
{"event": "woke", ..., "slept_s": 3600.0}
```

`sleeping` is sent once, during the response delay before suspend.
`started` and `woke` retry with backoff for `retry_seconds`, since the
network is often not up yet at logon or resume. The URL holds the webhook
id, so keep it only in `config.toml`; it is never logged.

The wake grace exists because a remote wake involves no input, so `idle_s`
still reflects the last input before sleep and the PC would otherwise be
put straight back to sleep. With the defaults, sleep is allowed no sooner
than 20 minutes after wake. Resume is detected by a 5s heartbeat thread
seeing the wall clock jump by more than 30s.

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
