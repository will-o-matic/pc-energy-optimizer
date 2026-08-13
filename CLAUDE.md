# pc-energy-optimizer — project conventions

- **Git: `main`-only with feature branches.** Deliberate: solo repo, no CI/CD
  pipeline. Do not create a `staging` branch or retarget PRs unless asked.
- **Stack:** Python + uv. One runtime dep (psutil). stdlib HTTP server — don't
  add a web framework without discussion.
- **Windows-only code lives in `src/pc_energy_optimizer/winapi.py`** (ctypes).
  Everything else must stay importable off-Windows. `server.py` takes injected
  provider callables so tests never touch Win32.
- **Tests are framework-free:** each test module prints `OK:` lines and exits
  0. Run all: `uv run python tests/run_all.py`.
- **Secrets:** the real `config.toml` is gitignored and holds the bearer
  token plus this PC's actual bind address. Never commit it; never echo
  tokens or real network details into docs or logs.
- **Deploy:** `install\install-task.ps1` registers the hidden at-logon
  Scheduled Task.
