"""Tests for the open-loop load client (scripts/loadgen.py)."""
import importlib.util
import os
import threading
import time

import pytest
from werkzeug.serving import make_server

import grpc_server
from app import create_app
from inora_core import Store

_spec = importlib.util.spec_from_file_location(
    "loadgen", os.path.join(os.path.dirname(__file__), "..", "scripts", "loadgen.py"))
loadgen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(loadgen)


def test_percentile_nearest_rank():
    values = list(range(1, 101))
    assert loadgen.percentile(values, 50) == 50
    assert loadgen.percentile(values, 95) == 95
    assert loadgen.percentile(values, 100) == 100
    assert loadgen.percentile([], 95) is None
    assert loadgen.percentile([7], 95) == 7


class _SlowWsgi:
    """Wraps the app and delays every response, to prove the client does not wait for responses."""

    def __init__(self, app, delay):
        self.app, self.delay = app, delay

    def __call__(self, environ, start_response):
        time.sleep(self.delay)
        return self.app(environ, start_response)


@pytest.fixture
def http_base(tmp_path):
    app = create_app(db_path=str(tmp_path / "lg.db"), rate_limit=1000, rate_window=10)
    server = make_server("127.0.0.1", 0, _SlowWsgi(app, 0.3), threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_http_is_open_loop_and_counts_everything(http_base):
    t = time.perf_counter()
    s = loadgen.run_http(http_base, rate=30, duration=1, timeout_s=5, name="t")
    wall = time.perf_counter() - t
    assert s["sent"] == 30 and s["ok"] == 30 and s["failed"] == 0
    assert s["completed"] == 30 and s["error_rate_pct"] == 0.0
    assert s["p50_ms"] >= 280                           # every response took >= 0.3 s ...
    assert wall < 3.5                                   # ... yet 30 of them finished in ~1.3 s, not 9 s: open loop
    assert s["retries"] == "none"
    assert sum(s["client_view_replicas"].values()) == 30
    assert sum(x.get("ok", 0) + x.get("failed", 0) for x in s["per_second"]) == 30     # per-second timeline adds up


def test_http_failures_are_counted_not_retried():
    s = loadgen.run_http("http://127.0.0.1:9", rate=10, duration=1, timeout_s=1, name="down")
    assert s["sent"] == 10 and s["ok"] == 0 and s["failed"] == 10
    assert s["error_rate_pct"] == 100.0 and s["p95_ms"] is None
    assert sum(s["errors"].values()) == 10


def test_grpc_run_uses_one_channel_and_reports_replicas(tmp_path):
    server, port = grpc_server.build_server(Store(str(tmp_path / "g.db")), port=0)
    server.start()
    try:
        s = loadgen.run_grpc(f"127.0.0.1:{port}", rate=20, duration=1, timeout_s=5, name="g")
    finally:
        server.stop(0)
    assert s["sent"] == 20 and s["ok"] == 20 and s["failed"] == 0
    assert list(s["client_view_share_pct"].values()) == [100.0]


def test_grpc_failures_report_status_code():
    s = loadgen.run_grpc("127.0.0.1:9", rate=5, duration=1, timeout_s=1, name="g-down")
    assert s["sent"] == 5 and s["failed"] == 5 and s["ok"] == 0
    assert "UNAVAILABLE" in s["errors"] or "DEADLINE_EXCEEDED" in s["errors"]
