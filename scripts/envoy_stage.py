"""envoy_stage.py - switch Envoy to one of the stage configs in envoy/stages/ and show who is in each cluster.

  python scripts/envoy_stage.py a-only          # Part A / B baseline: everything goes to replica A
  python scripts/envoy_stage.py round-robin     # Part C: A, B, C with equal weight
  python scripts/envoy_stage.py weighted-2-1-1  # Part D: weights 2:1:1
  python scripts/envoy_stage.py least-request   # Part D: least request
  python scripts/envoy_stage.py health-check    # Part D: round robin + active health checks
  python scripts/envoy_stage.py --list

It first checks the stage file with Envoy's own validator (nothing changes if it is invalid), then
copies envoy/stages/<name>.yaml over envoy/envoy.yaml, restarts the envoy container, waits for the
replica addresses to resolve and prints the members of http_backend and grpc_backend (from Envoy's admin port).
"""
import argparse
import os
import subprocess
import sys
import time

import requests

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
STAGES = os.path.join(ROOT, "envoy", "stages")
ACTIVE = os.path.join(ROOT, "envoy", "envoy.yaml")
ADMIN = "http://127.0.0.1:9901"


def stage_names():
    return sorted(f[:-5] for f in os.listdir(STAGES) if f.endswith(".yaml"))


def validate(src):
    """Run Envoy's config validator on the stage file in a throw-away container. True if valid."""
    cmd = ["docker", "run", "--rm", "-e", "ENVOY_UID=0",
           "--mount", f"type=bind,source={os.path.abspath(src)},target=/etc/envoy/envoy.yaml,readonly",
           "--mount", f"type=bind,source={os.path.abspath(os.path.join(ROOT, 'logs'))},target=/logs",
           "envoyproxy/envoy:v1.39.1", "--mode", "validate", "-c", "/etc/envoy/envoy.yaml"]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    text = (p.stdout or "") + (p.stderr or "")
    ok = p.returncode == 0 and "OK" in text
    print("config check:", "OK" if ok else "FAILED")
    if not ok:
        print(text[-1500:])
    return ok


def members():
    """{cluster: {host: (weight, health)}} from Envoy's /clusters."""
    out = {}
    for line in requests.get(f"{ADMIN}/clusters", timeout=5).text.splitlines():
        parts = line.split("::")
        if len(parts) >= 4 and parts[0] in ("http_backend", "grpc_backend") and ":" in parts[1]:   # real hosts only
            host = out.setdefault(parts[0], {}).setdefault(parts[1], {})
            host[parts[2]] = "::".join(parts[3:])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", nargs="?")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--no-validate", action="store_true", help="skip the config check")
    a = ap.parse_args()
    if a.list or not a.stage:
        print("stages:", ", ".join(stage_names()))
        return
    src = os.path.join(STAGES, a.stage + ".yaml")
    if not os.path.exists(src):
        sys.exit(f"unknown stage '{a.stage}'. Available: {', '.join(stage_names())}")
    if not a.no_validate and not validate(src):
        sys.exit("stage file is not valid - Envoy was NOT changed")
    with open(src, "rb") as f, open(ACTIVE, "wb") as g:       # written in place so the container sees the new file
        g.write(f.read())
    print(f"envoy/envoy.yaml  <-  envoy/stages/{a.stage}.yaml")
    subprocess.run(["docker", "compose", "restart", "envoy"], cwd=ROOT, check=True)
    print("waiting for Envoy ...")
    info = {}
    for _ in range(30):
        time.sleep(2)
        try:
            info = members()
        except requests.RequestException:
            continue
        if info and all(any(k == "health_flags" and v == "healthy" for h in c.values() for k, v in h.items())
                        for c in info.values()):
            break
    if not info:
        subprocess.run(["docker", "logs", "envoy", "--tail", "20"])
        sys.exit("Envoy did not come up (see its log above)")
    for cluster in ("http_backend", "grpc_backend"):
        print(f"{cluster}:")
        for host, d in sorted(info.get(cluster, {}).items()):
            print(f"   {host:<22} weight={d.get('weight')}  health={d.get('health_flags')}")
    n = {c: len(h) for c, h in info.items()}
    print(f"members: {n}")


if __name__ == "__main__":
    main()
