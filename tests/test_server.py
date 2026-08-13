"""Tests for the HTTP server with fake providers — no Windows APIs touched."""
import json
import sys
import threading
import time
import urllib.error
import urllib.request

from pc_energy_optimizer import __version__
from pc_energy_optimizer.config import Config, ServerConfig, SleepConfig
from pc_energy_optimizer.server import create_server

TOKEN = "test-token-123"


class Fakes:
    def __init__(self):
        self.idle_s = 9999.0
        self.cpu = 5.0
        self.sleep_calls = 0

    def idle_fn(self):
        return self.idle_s

    def cpu_fn(self):
        return self.cpu

    def sleep_fn(self):
        self.sleep_calls += 1
        return True


def start_test_server(fakes):
    cfg = Config(
        server=ServerConfig(bind_host="127.0.0.1", port=0, token=TOKEN),
        sleep=SleepConfig(response_delay_seconds=0),
    )
    srv = create_server(
        cfg, idle_fn=fakes.idle_fn, cpu_fn=fakes.cpu_fn, sleep_fn=fakes.sleep_fn
    )
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def request(url, method="GET", token=None, body=None):
    req = urllib.request.Request(url, method=method)
    if token is not None:
        req.add_header("Authorization", f"Bearer {token}")
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def main():
    fakes = Fakes()
    srv, base = start_test_server(fakes)

    status, body = request(f"{base}/health")
    assert status == 200 and body == {"status": "ok", "version": __version__}
    print("OK: /health no auth")

    status, body = request(f"{base}/status")
    assert status == 401 and body == {"error": "unauthorized"}
    print("OK: /status 401 without token")

    status, body = request(f"{base}/status", token="wrong-length")
    assert status == 401
    print("OK: /status 401 wrong token")

    status, body = request(f"{base}/status", token=TOKEN)
    assert status == 200
    for key in ("hostname", "idle_s", "cpu_percent", "uptime_s", "version"):
        assert key in body, f"missing {key}"
    assert body["idle_s"] == 9999.0 and body["cpu_percent"] == 5.0
    print("OK: /status 200 with keys")

    status, body = request(f"{base}/nope", token=TOKEN)
    assert status == 404
    print("OK: 404 unknown path")

    status, body = request(f"{base}/sleep", method="POST", token=TOKEN)
    assert status == 202 and body["result"] == "sleeping" and body["forced"] is False
    time.sleep(0.5)
    assert fakes.sleep_calls == 1
    print("OK: /sleep 202 and sleep_fn called")

    fakes.idle_s = 42.0
    fakes.cpu = 87.2
    status, body = request(f"{base}/sleep", method="POST", token=TOKEN)
    assert status == 409 and body["result"] == "refused"
    assert [r["code"] for r in body["reasons"]] == ["user_active", "cpu_high"]
    assert fakes.sleep_calls == 1
    print("OK: /sleep 409 with reasons")

    status, body = request(
        f"{base}/sleep", method="POST", token=TOKEN, body={"force": True}
    )
    assert status == 202 and body["forced"] is True
    time.sleep(0.5)
    assert fakes.sleep_calls == 2
    print("OK: /sleep force override")

    status, body = request(f"{base}/sleep", method="POST")
    assert status == 401
    assert fakes.sleep_calls == 2
    print("OK: /sleep 401 without token")

    status, body = request(f"{base}/sleep", method="GET", token=TOKEN)
    assert status == 405
    print("OK: /sleep GET 405")

    srv.shutdown()
    print("OK: test_server")


if __name__ == "__main__":
    main()
    sys.exit(0)
