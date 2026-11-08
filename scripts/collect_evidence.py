"""collect_evidence.py - redo the A-only baseline and the round-robin runs (HTTP and gRPC) and save everything to evidence/.

  python scripts/collect_evidence.py            # takes about 12 minutes; leaves Envoy on round-robin

For each stage it: switches Envoy, runs both workloads with Filebeat stopped (then starts Filebeat again), compares the
shares (Prometheus / Envoy logs / client), runs the Kibana-style trace search for each interface and the rate-limit demo.
Finally it copies the configs, writes evidence/README.md (index + exact screenshot list with Grafana links).
"""
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
EV = os.path.join(ROOT, "evidence")
PY = sys.executable
ENV = dict(os.environ, PYTHONIOENCODING="utf-8")
RATE, DURATION = "40", "60"
STAGES = [("a-only", "A=100,B=0,C=0"), ("round-robin", None)]


def run(cmd, outfile=None, check=False):
    print("  $", " ".join(cmd))
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV)
    text = (p.stdout or "") + (p.stderr or "")
    if outfile:
        with open(outfile, "w", encoding="utf-8") as f:
            f.write(text)
    if check and p.returncode:
        sys.exit(f"command failed: {' '.join(cmd)}\n{text}")
    return p.returncode, text


def script(name, *args):
    return [PY, os.path.join("scripts", name), *args]


def main():
    shutil.rmtree(EV, ignore_errors=True)
    for d in ("config", "system", "screenshots"):
        os.makedirs(os.path.join(EV, d))
    windows, trace_ids, results = {}, {}, {}
    for stage, expect in STAGES:
        sd = os.path.join(EV, stage)
        os.makedirs(sd)
        print(f"\n=== stage {stage} ===")
        run(script("envoy_stage.py", stage), os.path.join(sd, "cluster-members.txt"), check=True)
        for iface in ("http", "grpc"):
            run(["docker", "stop", "filebeat"])
            jf = os.path.join(sd, f"{iface}-run.json")
            run(script("loadgen.py", "--interface", iface, "--rate", RATE, "--duration", DURATION,
                       "--name", f"{stage}-{iface}", "--json-out", jf), os.path.join(sd, f"{iface}-run.txt"), check=True)
            run(["docker", "start", "filebeat"])
            r = json.load(open(jf, encoding="utf-8"))
            windows[(stage, iface)] = (r["started_utc"], r["ended_utc"])
            results[(stage, iface)] = r
        time.sleep(5)
        for iface in ("http", "grpc"):
            args = [os.path.join("evidence", stage, f"{iface}-run.json")] + (["--expect", expect] if expect else [])
            run(script("run_report.py", *args), os.path.join(sd, f"{iface}-shares.txt"))
        for iface in ("http", "grpc"):
            _, text = run(script("es_trace_search.py", "--latest", iface), os.path.join(sd, f"{iface}-trace-search.txt"))
            m = re.search(r"trace_id ([0-9a-f]{32})", text)
            trace_ids[(stage, iface)] = m.group(1) if m else "(not found)"
        time.sleep(12)
        run(script("ratelimit_demo.py", "--count", "15"), os.path.join(sd, "ratelimit-demo.txt"))
        time.sleep(12)
    # ---- system and config copies
    run(["docker", "compose", "ps"], os.path.join(EV, "system", "docker-compose-ps.txt"))
    run([PY, "-m", "pytest", "-q"], os.path.join(EV, "system", "tests.txt"))
    try:
        import requests
        t = requests.get("http://localhost:9090/api/v1/targets", timeout=10).json()["data"]["activeTargets"]
        with open(os.path.join(EV, "system", "prometheus-targets.txt"), "w", encoding="utf-8") as f:
            for x in sorted(t, key=lambda x: (x["labels"].get("job", ""), x["scrapeUrl"])):
                f.write(f"{x['labels'].get('job'):<14} replica={x['labels'].get('replica', '-'):<2} {x['health']:<5} {x['scrapeUrl']}\n")
    except Exception as exc:                                    # noqa: BLE001
        print("could not read Prometheus targets:", exc)
    for src, dst in (("envoy/stages/a-only.yaml", "config"), ("envoy/stages/round-robin.yaml", "config"),
                     ("prometheus.yml", "config"), ("filebeat.yml", "config"), ("docker-compose.yml", "config"),
                     ("grafana/dashboards/inora-a3-load-balancing.json", "config")):
        shutil.copy(os.path.join(ROOT, src), os.path.join(EV, dst))
    # ---- index
    ms = lambda s: int(datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)  # noqa: E731
    L = ["# Evidence (Assignment 3, Parts A-C)", "",
         f"Generated {datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d %H:%M} UTC by `scripts/collect_evidence.py`. "
         f"Workload: {RATE} requests/s for {DURATION} s, open loop, no retries, Filebeat stopped during each run.", "",
         "## Results", "", "| Stage | Interface | Sent | OK | Failed | Client p95 (ms) | Window (UTC) |", "|---|---|---|---|---|---|---|"]
    for (stage, iface), r in results.items():
        L.append(f"| {stage} | {iface} | {r['sent']} | {r['ok']} | {r['failed']} | {r['p95_ms']} | {r['started_utc']} - {r['ended_utc']} |")
    L += ["", "Share tables: `<stage>/<iface>-shares.txt`. Trace searches: `<stage>/<iface>-trace-search.txt`. "
          "Rate limit: `<stage>/ratelimit-demo.txt`. Envoy members: `<stage>/cluster-members.txt`.", "",
          "## Screenshots to take (save in `evidence/screenshots/`, exact file names)", "",
          "Open each Grafana link, wait for the panels to load, scroll so the whole HTTP or gRPC section is visible, take the screenshot.", ""]
    n = 1
    for stage, _ in STAGES:
        for iface in ("http", "grpc"):
            a, b = windows[(stage, iface)]
            url = f"http://localhost:3000/d/inora-a3-load-balancing?orgId=1&from={ms(a) - 30000}&to={ms(b) + 30000}"
            L.append(f"{n}. `{stage}-{iface}-dashboard.png` - {stage}, {iface.upper()} rows: {url}")
            n += 1
    a, b = windows[("round-robin", "grpc")]
    L.append(f"{n}. `envoy-panels.png` - Envoy row (members, responses, in-flight), round-robin: "
             f"http://localhost:3000/d/inora-a3-load-balancing?orgId=1&from={ms(a) - 30000}&to={ms(b) + 30000}")
    L.append(f"{n + 1}. `prometheus-targets.png` - http://localhost:9090/targets (all UP)")
    L.append(f"{n + 2}. `kibana-http-correlation.png` - saved search http://localhost:5601/app/discover#/view/inora-a3-correlation , "
             f"time range last 1 hour, query `trace_id : \"{trace_ids[('round-robin', 'http')]}\"` (2 rows)")
    L.append(f"{n + 3}. `kibana-grpc-correlation.png` - same page, query `trace_id : \"{trace_ids[('round-robin', 'grpc')]}\"` (2 rows)")
    open(os.path.join(EV, "README.md"), "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
    print("\nDone. Envoy is left on round-robin. Open evidence/README.md for the screenshot list.")


if __name__ == "__main__":
    main()
