"""probe_replicas.py - send a few read-only calls THROUGH ENVOY and show which replica answered each one.

Examples (project root, venv active, stack up):
  python scripts/probe_replicas.py                    # 30 HTTP calls + 30 gRPC calls
  python scripts/probe_replicas.py --count 90 --only grpc

HTTP:  GET  /products/{id}                  -> the replica name is in the X-Replica response header
gRPC:  CatalogService/GetProduct (unary)    -> the replica name is in the x-replica initial metadata
All gRPC calls use ONE channel (one connection to Envoy), like a real client does.
"""
import argparse
import collections
import os
import sys

import grpc
import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from grpc_client import get_product  # noqa: E402


def probe_http(base, product, count):
    seen = collections.Counter()
    errors = 0
    with requests.Session() as s:
        for _ in range(count):
            try:
                r = s.get(f"{base}/products/{product}", timeout=5)
                if r.status_code == 200:
                    seen[r.headers.get("X-Replica", "?")] += 1
                else:
                    errors += 1
            except requests.RequestException:
                errors += 1
    return seen, errors


def probe_grpc(target, product, count):
    seen = collections.Counter()
    errors = 0
    with grpc.insecure_channel(target) as channel:
        for _ in range(count):
            resp, err, _tp, replica = get_product(target, product, deadline_s=5.0, channel=channel)
            if resp is not None:
                seen[replica or "?"] += 1
            else:
                errors += 1
    return seen, errors


def show(name, seen, errors, count):
    print(f"{name}: {count} calls, {errors} errors")
    for replica in sorted(seen):
        print(f"   replica {replica}: {seen[replica]:4d}  ({100.0 * seen[replica] / count:5.1f} %)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--http", default=os.environ.get("INORA_HTTP_BASE", "http://127.0.0.1:10000"))
    ap.add_argument("--grpc", default=os.environ.get("INORA_GRPC_TARGET", "127.0.0.1:10001"))
    ap.add_argument("--product", default="clover-pendant")
    ap.add_argument("--count", type=int, default=30)
    ap.add_argument("--only", choices=["http", "grpc"], default=None)
    a = ap.parse_args()
    if a.only != "grpc":
        show("HTTP", *probe_http(a.http, a.product, a.count), a.count)
    if a.only != "http":
        show("gRPC", *probe_grpc(a.grpc, a.product, a.count), a.count)


if __name__ == "__main__":
    main()
