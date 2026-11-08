"""envoy_stage.py - switch Envoy to one of the stage configs in envoy/stages/ and show who is in each cluster.

  python scripts/envoy_stage.py a-only          # Part A / B baseline: everything goes to replica A
  python scripts/envoy_stage.py round-robin     # Part C: A, B, C with equal weight
  python scripts/envoy_stage.py --list

It copies envoy/stages/<name>.yaml over envoy/envoy.yaml, restarts the envoy container, waits for the
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


def members():
    """{cluster: {host: (weight, health)}} from Envoy's /clusters."""
    out = {}
    for line in requests.get(f"{ADMIN}/clusters", timeout=5).text.splitlines():
        parts = line.split("::")
        if len(parts) >= 4 and parts[0] in ("http_backend", "grpc_backend"):
            host = out.setdefault(parts[0], {}).setdefault(parts[1], {})
            host[parts[2]] = "::".join(parts[3:])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", nargs="?")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list or not a.stage:
        print("stages:", ", ".join(stage_names()))
        return
    src = os.path.join(STAGES, a.stage + ".yaml")
    if not os.path.exists(src):
        sys.exit(f"unknown stage '{a.stage}'. Available: {', '.join(stage_names())}")
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
    for cluster in ("http_backend", "grpc_backend"):
        print(f"{cluster}:")
        for host, d in sorted(info.get(cluster, {}).items()):
            print(f"   {host:<22} weight={d.get('weight')}  health={d.get('health_flags')}")
    n = {c: len(h) for c, h in info.items()}
    print(f"members: {n}")


if __name__ == "__main__":
    main()
