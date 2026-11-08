"""failure_test.py - Part D experiment 3: stop replica B during traffic, then start it again.

  python scripts/failure_test.py --interface http --json-out evidence/part-d/failure-http/run.json
  python scripts/failure_test.py --interface grpc --json-out evidence/part-d/failure-grpc/run.json

Needs Envoy on the `health-check` stage (python scripts/envoy_stage.py health-check). Timeline (defaults):
  0 s traffic starts at 40 req/s  ->  20 s `docker stop` of B (HTTP: api-2, gRPC: grpc-2)  ->  45 s `docker start`  ->  90 s end.
While it runs, Envoy's admin port is polled every 0.5 s to see when B's health flag changes. Reported:
  removal time  = B really down -> Envoy marks it unhealthy        recovery time = B started -> Envoy marks it healthy again
plus client successes/failures and the per-second spread of answers by replica (in the JSON, key per_second).
The result is the normal loadgen JSON plus a `failure_test` section. Retries and circuit breakers stay off.
"""
import argparse
import datetime
import importlib.util
import json
import os
import subprocess
import threading
import time

import requests
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
ADMIN = "http://127.0.0.1:9901"
spec = importlib.util.spec_from_file_location("loadgen", os.path.join(HERE, "loadgen.py"))
loadgen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loadgen)


def hhmmss(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%H:%M:%S.%f")[:-3]


def docker(*args):
    return subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")


def container_ip(name):
    return docker("inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", name).stdout.strip()


def flags_of(cluster, hostport):
    for line in requests.get(f"{ADMIN}/clusters", timeout=2).text.splitlines():
        p = line.split("::")
        if len(p) >= 4 and p[0] == cluster and p[1] == hostport and p[2] == "health_flags":
            return p[3]
    return "(not in cluster)"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interface", choices=["http", "grpc"], required=True)
    ap.add_argument("--rate", type=float, default=40)
    ap.add_argument("--duration", type=float, default=90)
    ap.add_argument("--stop-at", type=float, default=20)
    ap.add_argument("--down-for", type=float, default=25)
    ap.add_argument("--name", default=None)
    ap.add_argument("--json-out", required=True)
    a = ap.parse_args()
    http = a.interface == "http"
    cname = f"inora-observability-part3-{'api' if http else 'grpc'}-2"
    cluster, port = ("http_backend", 5000) if http else ("grpc_backend", 50051)
    ip = container_ip(cname)
    hostport = f"{ip}:{port}"
    state = flags_of(cluster, hostport)
    if state != "healthy":
        raise SystemExit(f"B ({hostport}) is '{state}' in Envoy before the test. Run: python scripts/envoy_stage.py health-check")
    hc = next(c for c in yaml.safe_load(open(os.path.join(ROOT, "envoy", "envoy.yaml"), encoding="utf-8"))
              ["static_resources"]["clusters"] if c["name"] == cluster).get("health_checks")
    if not hc:
        raise SystemExit("envoy/envoy.yaml has no health_checks: run python scripts/envoy_stage.py health-check first")

    changes, stop_poll = [], threading.Event()
    last = {"v": state}

    def poll():
        while not stop_poll.is_set():
            try:
                v = flags_of(cluster, hostport)
                if v != last["v"]:
                    changes.append((time.time(), last["v"], v))
                    last["v"] = v
            except requests.RequestException:
                pass
            time.sleep(0.5)

    holder = {}
    name = a.name or f"failure-{a.interface}"

    def load():
        fn = loadgen.run_http if http else loadgen.run_grpc
        holder["s"] = fn(rate=a.rate, duration=a.duration, name=name)

    threading.Thread(target=poll, daemon=True).start()
    lt = threading.Thread(target=load)
    t_begin = time.time()
    lt.start()
    time.sleep(a.stop_at)
    t_stop_issued = time.time()
    docker("stop", "-t", "1", cname)
    t_down = time.time()
    time.sleep(max(0, a.down_for - (time.time() - t_down)))
    t_start_issued = time.time()
    docker("start", cname)
    t_up = time.time()
    lt.join()
    time.sleep(3)
    stop_poll.set()
    s = holder["s"]
    ip_after = container_ip(cname)
    unhealthy = next((t for t, _, v in changes if t >= t_stop_issued and v != "healthy"), None)
    healthy_again = next((t for t, _, v in changes if t >= t_up and v == "healthy"), None)
    ft = {
        "replica": "B", "container": cname, "cluster": cluster, "host": hostport, "ip_after_restart": ip_after,
        "health_check": hc[0],
        "events_utc": {"traffic_start": hhmmss(t_begin), "stop_issued": hhmmss(t_stop_issued), "stopped": hhmmss(t_down),
                       "start_issued": hhmmss(t_start_issued), "started": hhmmss(t_up),
                       "marked_unhealthy": hhmmss(unhealthy) if unhealthy else None,
                       "marked_healthy_again": hhmmss(healthy_again) if healthy_again else None},
        "health_flag_changes": [{"t_utc": hhmmss(t), "from": f, "to": v} for t, f, v in changes],
        "removal_seconds": round(unhealthy - t_down, 2) if unhealthy else None,
        "recovery_seconds": round(healthy_again - t_up, 2) if healthy_again else None,
    }
    s["failure_test"] = ft
    os.makedirs(os.path.dirname(os.path.abspath(a.json_out)), exist_ok=True)
    json.dump(s, open(a.json_out, "w", encoding="utf-8"), indent=2)
    loadgen.print_summary(s)
    print("\nFAILURE TEST", a.interface)
    for k, v in ft["events_utc"].items():
        print(f"  {k:<22} {v}")
    print(f"  health check          {ft['health_check']}")
    print(f"  removal  (B stopped -> unhealthy in Envoy)   {ft['removal_seconds']} s")
    print(f"  recovery (B started -> healthy in Envoy)     {ft['recovery_seconds']} s")
    print(f"  client failures       {s['failed']} of {s['sent']}  {s['errors']}")
    if ip_after != ip:
        print(f"  WARNING: B's address changed ({ip} -> {ip_after}); Envoy keeps the old one (DNS refresh is 600 s). "
              "Recovery time is not valid. Run: python scripts/envoy_stage.py health-check, then repeat.")


if __name__ == "__main__":
    main()
