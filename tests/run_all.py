"""Run every test module as a subprocess; print OK: all if every one exits 0."""
import subprocess
import sys
from pathlib import Path

MODULES = [
    "test_config.py", "test_guardrails.py", "test_server.py", "test_wake.py",
    "test_powerreq.py", "test_energy.py", "test_webhook.py",
]

here = Path(__file__).parent
failed = []
for mod in MODULES:
    result = subprocess.run([sys.executable, str(here / mod)])
    if result.returncode != 0:
        failed.append(mod)

if failed:
    print(f"FAIL: {', '.join(failed)}")
    sys.exit(1)
print("OK: all")
