"""run_experiments.py - run the Part D experiments end to end and save everything to evidence/part-d/.

  python scripts/run_experiments.py all            # about 20 minutes
  python scripts/run_experiments.py weighted       # experiment 1: weights 2:1:1
  python scripts/run_experiments.py delay          # experiment 2: delay on B, round robin then least request
  python scripts/run_experiments.py failure        # experiment 3: stop B, start B (active health checks)

Every run: 40 req/s for 60 s (failure test: 90 s), open loop, no retries, Filebeat stopped while measuring.
Afterwards Envoy is put back on round-robin and the delay is cleared, whatever happens.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PD = os.path.join(ROOT, "evidence", "part-d")
PY = sys.executable
ENV = dict(os.environ, PYTHONIOENCODING="utf-8")
RATE, DURATION, DELAY_S = "40", "60", "0.4"
REGISTRY = os.path.join(PD, "runs.json")


def run(cmd, outfile=None, check=False):
    print("  $", " ".join(os.path.basename(c) if c == PY else c for c in cmd))
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV)
    text = (p.stdout or "") + (p.stderr or "")
    if outfile:
        with open(outfile, "w", encoding="utf-8") as f:
            f.write(text)
    if check and p.returncode:
        sys.exit(f"command failed: {' '.join(cmd)}\n{text}")
    return p.returncode, text


def sc(name, *args):
    return [PY, os.path.join("scripts", name), *args]


def registry():
    return json.load(open(REGISTRY, encoding="utf-8")) if os.path.exists(REGISTRY) else []


def register(entry):
    r = [e for e in registry() if e["id"] != entry["id"]] + [entry]
    json.dump(r, open(REGISTRY, "w", encoding="utf-8"), indent=2)


def stage(name):
    run(sc("envoy_stage.py", name), os.path.join(PD, f"stage-{name}.txt"), check=True)


def prepare(exp, iface):
    d = os.path.join(PD, exp, iface)
    os.makedirs(d, exist_ok=True)
    return d


def measure(exp, iface, policy, fault, expect=None, failure=False):
    """Run one measured load and register it. Filebeat is stopped while it runs."""
    d = prepare(exp, iface)
    jf = os.path.join(d, "run.json")
    run(["docker", "stop", "filebeat"])
    try:
        if failure:
            run(sc("failure_test.py", "--interface", iface, "--json-out", jf, "--name", f"{exp}-{iface}"),
                os.path.join(d, "run.txt"), check=True)
        else:
            run(sc("loadgen.py", "--interface", iface, "--rate", RATE, "--duration", DURATION,
                   "--name", f"{exp}-{iface}", "--json-out", jf), os.path.join(d, "run.txt"), check=True)
    finally:
        run(["docker", "start", "filebeat"])
    register({"id": f"{exp}-{iface}", "interface": iface, "policy": policy, "fault": fault,
              "run_json": os.path.relpath(jf, ROOT), "expect": expect})


def reports(exp_ifaces):
    for exp, iface, expect in exp_ifaces:
        d = os.path.join(PD, exp, iface)
        args = [os.path.relpath(os.path.join(d, "run.json"), ROOT)] + (["--expect", expect] if expect else [])
        run(sc("run_report.py", *args), os.path.join(d, "shares.txt"))


def exp_weighted():
    print("\n=== experiment 1: weighted 2:1:1 ===")
    stage("weighted-2-1-1")
    for i in ("http", "grpc"):
        measure("weighted", i, "weighted round robin 2:1:1", "none", "A=50,B=25,C=25")
    time.sleep(5)
    reports([("weighted", i, "A=50,B=25,C=25") for i in ("http", "grpc")])


def exp_delay():
    print("\n=== experiment 2: delay on B ===")
    run(sc("fault.py", "set", "B", DELAY_S), check=True)
    for exp, st, pol in (("delay-rr", "round-robin", "round robin"), ("delay-lr", "least-request", "least request")):
        stage(st)
        for i in ("http", "grpc"):
            measure(exp, i, pol, f"B +{int(float(DELAY_S) * 1000)} ms")
        time.sleep(5)
        reports([(exp, i, None) for i in ("http", "grpc")])
    run(sc("fault.py", "clear"), check=True)


def exp_failure():
    print("\n=== experiment 3: stop B, start B ===")
    stage("health-check")
    for i in ("http", "grpc"):
        measure("failure", i, "round robin + active health checks", "B stopped at 20 s, started at 45 s", failure=True)
        time.sleep(10)
    time.sleep(5)
    reports([("failure", i, None) for i in ("http", "grpc")])


def write_index():
    ms = lambda s: int(datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)  # noqa: E731
    L = ["# Part D evidence", "", f"Generated {datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d %H:%M} UTC by `scripts/run_experiments.py`.", "",
         "| Run | Policy | Fault | Sent | OK | Failed | Client p95 (ms) | Window (UTC) |", "|---|---|---|---|---|---|---|---|"]
    shots = []
    for e in registry():
        r = json.load(open(os.path.join(ROOT, e["run_json"]), encoding="utf-8"))
        L.append(f"| {e['id']} | {e['policy']} | {e['fault']} | {r['sent']} | {r['ok']} | {r['failed']} | {r['p95_ms']} | {r['started_utc']} - {r['ended_utc']} |")
        url = f"http://localhost:3000/d/inora-a3-load-balancing?orgId=1&from={ms(r['started_utc']) - 30000}&to={ms(r['ended_utc']) + 30000}"
        shots.append(f"`{e['id']}-dashboard.png` - {e['interface'].upper()} rows (and the Envoy row for the failure runs): {url}")
    L += ["", "## Screenshots to take (save in `evidence/part-d/screenshots/`)", ""] + [f"{n}. {x}" for n, x in enumerate(shots, 1)]
    os.makedirs(os.path.join(PD, "screenshots"), exist_ok=True)
    open(os.path.join(PD, "README.md"), "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("which", choices=["all", "weighted", "delay", "failure"])
    a = ap.parse_args()
    os.makedirs(PD, exist_ok=True)
    try:
        for name, fn in (("weighted", exp_weighted), ("delay", exp_delay), ("failure", exp_failure)):
            if a.which in ("all", name):
                fn()
    finally:
        print("\nRestoring normal behaviour ...")
        run(sc("fault.py", "clear"))
        run(["docker", "start", "filebeat", "inora-observability-part3-api-2", "inora-observability-part3-grpc-2"])
        run(sc("envoy_stage.py", "round-robin"), os.path.join(PD, "stage-round-robin-restore.txt"))
    write_index()
    print("Done. Open evidence/part-d/README.md for the screenshot list.")


if __name__ == "__main__":
    main()
