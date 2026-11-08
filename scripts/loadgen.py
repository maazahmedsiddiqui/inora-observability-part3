"""loadgen.py - fixed-rate, fixed-duration, OPEN-LOOP test client (Assignment 3, Parts B-D).

Open loop = requests are started on a fixed schedule (request i at t0 + i / rate) and the client does NOT wait for
a response before sending the next one. A slow or dead replica therefore cannot slow the offered load down.

* HTTP : GET  /products/{id}                       through Envoy :10000  (read-only)
* gRPC : inora.v1.CatalogService/GetProduct (unary) through Envoy :10001  (read-only), ONE channel for all calls
* NO retries and no circuit breaker anywhere in this client (gRPC retries are switched off explicitly).
* Every request carries its own W3C traceparent, so any single request can be found again in Kibana.

What it records (printed, and written as JSON with --json-out): target rate, requests sent, successes, failures
(by cause), client-side p50/p95/p99 (successful requests, measured from the scheduled start time), the achieved
send rate, the replica that answered each request (X-Replica header / x-replica metadata, so the client's own view
of the traffic split can be compared with the dashboard), and the UTC start/end time of the run (use it to line up
Prometheus, Grafana and Kibana).

Examples (project root, venv active, stack up):
  python scripts/loadgen.py --interface http --rate 40 --duration 60 --name B-baseline-http
  python scripts/loadgen.py --interface grpc --rate 40 --duration 60 --name B-baseline-grpc --json-out runs/b-grpc.json
"""
import argparse
import collections
import concurrent.futures
import datetime
import json
import os
import sys
import threading
import time

import grpc
import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from inora.v1 import inora_pb2, inora_pb2_grpc  # noqa: E402
from inora_obs import make_traceparent  # noqa: E402

DEFAULT_HTTP = "http://127.0.0.1:10000"      # 127.0.0.1, not localhost: avoids a slow IPv6 fallback on Windows
DEFAULT_GRPC = "127.0.0.1:10001"


def percentile(sorted_values, p):
    """Nearest-rank percentile of an already sorted list (p in 0..100). None for an empty list."""
    if not sorted_values:
        return None
    k = max(1, int(-(-p * len(sorted_values) // 100)))      # ceil(p/100 * n)
    return sorted_values[min(k, len(sorted_values)) - 1]


class Recorder:
    def __init__(self):
        self._lock = threading.Lock()
        self.latencies_ok = []
        self.ok = 0
        self.failed = 0
        self.errors = collections.Counter()
        self.replicas = collections.Counter()
        self.done = 0

    def add(self, ok, latency_s, replica, error=None):
        with self._lock:
            self.done += 1
            if ok:
                self.ok += 1
                self.latencies_ok.append(latency_s)
            else:
                self.failed += 1
                self.errors[error or "unknown"] += 1
            if replica:
                self.replicas[replica] += 1


def _wait_for_completion(rec, sent, timeout_s):
    deadline = time.perf_counter() + timeout_s + 2.0
    while rec.done < sent and time.perf_counter() < deadline:
        time.sleep(0.05)


def _summarise(name, interface, target, product, rate, duration, timeout_s, sent, rec, started, ended,
               send_phase_s, lags, t_end_all):
    lat = sorted(rec.latencies_ok)
    ms = lambda v: None if v is None else round(v * 1000.0, 2)          # noqa: E731
    lags_sorted = sorted(lags)
    total_replied = sum(rec.replicas.values())
    return {
        "name": name, "interface": interface, "target": target, "operation": (
            f"GET /products/{product}" if interface == "http" else "inora.v1.CatalogService/GetProduct"),
        "product_id": product,
        "started_utc": started.strftime("%Y-%m-%dT%H:%M:%SZ"), "ended_utc": ended.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "target_rps": rate, "duration_s": duration, "request_timeout_s": timeout_s,
        "retries": "none", "circuit_breaker": "none",
        "sent": sent, "completed": rec.done, "ok": rec.ok, "failed": rec.failed,
        "error_rate_pct": round(100.0 * rec.failed / sent, 2) if sent else 0.0,
        "actual_send_rps": round(sent / send_phase_s, 2) if send_phase_s > 0 else None,
        "completed_rps": round(rec.done / t_end_all, 2) if t_end_all > 0 else None,
        "p50_ms": ms(percentile(lat, 50)), "p95_ms": ms(percentile(lat, 95)), "p99_ms": ms(percentile(lat, 99)),
        "max_ms": ms(lat[-1] if lat else None),
        "max_schedule_lag_ms": ms(lags_sorted[-1] if lags_sorted else None),
        "p95_schedule_lag_ms": ms(percentile(lags_sorted, 95)),
        "errors": dict(rec.errors),
        "client_view_replicas": dict(sorted(rec.replicas.items())),
        "client_view_share_pct": {r: round(100.0 * n / total_replied, 1) for r, n in sorted(rec.replicas.items())}
        if total_replied else {},
    }


def _schedule(rate, duration, fire):
    """Call fire(i, scheduled_time) at t0 + i/rate for i in range(rate*duration). Never waits for a response."""
    total = int(round(rate * duration))
    interval = 1.0 / rate
    lags = []
    t0 = time.perf_counter()
    for i in range(total):
        target = t0 + i * interval
        delay = target - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
        lags.append(max(0.0, time.perf_counter() - target))
        fire(i, target)
    return total, time.perf_counter() - t0 + interval, lags, t0


def run_http(base=DEFAULT_HTTP, product="clover-pendant", rate=40, duration=60, timeout_s=5.0, name="http-run"):
    rec = Recorder()
    local = threading.local()
    url = f"{base.rstrip('/')}/products/{product}"
    workers = min(512, max(32, int(rate * timeout_s) + 16))

    def call(sched):
        session = getattr(local, "session", None)
        if session is None:
            session = local.session = requests.Session()           # no retry adapter mounted: no retries
        try:
            r = session.get(url, headers={"traceparent": make_traceparent()}, timeout=timeout_s)
            latency = time.perf_counter() - sched
            if r.status_code == 200:
                rec.add(True, latency, r.headers.get("X-Replica"))
            else:
                rec.add(False, latency, r.headers.get("X-Replica"), f"HTTP {r.status_code}")
        except requests.RequestException as exc:
            rec.add(False, time.perf_counter() - sched, None, type(exc).__name__)

    started = datetime.datetime.now(datetime.timezone.utc)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        sent, send_phase, lags, t0 = _schedule(rate, duration, lambda i, sched: pool.submit(call, sched))
        _wait_for_completion(rec, sent, timeout_s)
        t_end_all = time.perf_counter() - t0
    ended = datetime.datetime.now(datetime.timezone.utc)
    return _summarise(name, "http", base, product, rate, duration, timeout_s, sent, rec, started, ended,
                      send_phase, lags, t_end_all)


def run_grpc(target=DEFAULT_GRPC, product="clover-pendant", rate=40, duration=60, timeout_s=5.0, name="grpc-run"):
    rec = Recorder()
    channel = grpc.insecure_channel(target, options=[("grpc.enable_retries", 0)])     # one connection, no retries
    stub = inora_pb2_grpc.CatalogServiceStub(channel)
    request = inora_pb2.GetProductRequest(product_id=product)

    def fire(i, sched):
        future = stub.GetProduct.future(request, timeout=timeout_s, metadata=(("traceparent", make_traceparent()),))

        def done(f, sched=sched):
            latency = time.perf_counter() - sched
            code = f.code()
            replica = dict(f.initial_metadata() or ()).get("x-replica")
            if code == grpc.StatusCode.OK:
                rec.add(True, latency, replica)
            else:
                rec.add(False, latency, replica, code.name)

        future.add_done_callback(done)

    started = datetime.datetime.now(datetime.timezone.utc)
    try:
        sent, send_phase, lags, t0 = _schedule(rate, duration, fire)
        _wait_for_completion(rec, sent, timeout_s)
        t_end_all = time.perf_counter() - t0
    finally:
        channel.close()
    ended = datetime.datetime.now(datetime.timezone.utc)
    return _summarise(name, "grpc", target, product, rate, duration, timeout_s, sent, rec, started, ended,
                      send_phase, lags, t_end_all)


def print_summary(s):
    print()
    print(f"Run            : {s['name']}   ({s['interface']}, {s['operation']})")
    print(f"Target         : {s['target']}")
    print(f"Window (UTC)   : {s['started_utc']}  ->  {s['ended_utc']}")
    print(f"Target rate    : {s['target_rps']} req/s for {s['duration_s']} s   (retries: {s['retries']}, "
          f"circuit breaker: {s['circuit_breaker']}, timeout {s['request_timeout_s']} s)")
    print(f"Actual send    : {s['actual_send_rps']} req/s   (max schedule lag {s['max_schedule_lag_ms']} ms)")
    print(f"Sent           : {s['sent']}    completed {s['completed']}")
    print(f"Successes      : {s['ok']}")
    print(f"Failures       : {s['failed']}   ({s['error_rate_pct']} %)   {s['errors'] or ''}")
    print(f"Client latency : p50 {s['p50_ms']} ms   p95 {s['p95_ms']} ms   p99 {s['p99_ms']} ms   max {s['max_ms']} ms")
    print(f"Client view of replicas that answered: {s['client_view_replicas']}   shares % {s['client_view_share_pct']}")
    print()
    print("JSON:", json.dumps(s))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interface", choices=["http", "grpc"], required=True)
    ap.add_argument("--rate", type=float, default=40, help="requests per second (default 40)")
    ap.add_argument("--duration", type=float, default=60, help="seconds (default 60)")
    ap.add_argument("--timeout", type=float, default=5.0, help="per-request timeout in seconds (default 5)")
    ap.add_argument("--product", default="clover-pendant")
    ap.add_argument("--name", default=None, help="label for this run, e.g. B-baseline-http")
    ap.add_argument("--http", default=os.environ.get("INORA_HTTP_BASE", DEFAULT_HTTP))
    ap.add_argument("--grpc", default=os.environ.get("INORA_GRPC_TARGET", DEFAULT_GRPC))
    ap.add_argument("--json-out", default=None, help="also write the summary to this JSON file")
    a = ap.parse_args()
    name = a.name or f"{a.interface}-{int(a.rate)}rps-{int(a.duration)}s"
    print(f"Sending {a.rate} req/s for {a.duration} s ({int(round(a.rate * a.duration))} requests) over {a.interface} ...")
    if a.interface == "http":
        s = run_http(a.http, a.product, a.rate, a.duration, a.timeout, name)
    else:
        s = run_grpc(a.grpc, a.product, a.rate, a.duration, a.timeout, name)
    print_summary(s)
    if a.json_out:
        os.makedirs(os.path.dirname(os.path.abspath(a.json_out)), exist_ok=True)
        with open(a.json_out, "w", encoding="utf-8") as fh:
            json.dump(s, fh, indent=2)
        print(f"summary written to {a.json_out}")


if __name__ == "__main__":
    main()
