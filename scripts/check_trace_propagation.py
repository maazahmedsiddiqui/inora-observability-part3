"""check_trace_propagation.py - prove the trace ID survives client -> Envoy -> replica, for HTTP and for gRPC.

For each interface it sends ONE call through Envoy with a traceparent chosen here, then looks for that trace ID in
  * the response (the replica echoes traceparent back),
  * logs/envoy-access.log   (Envoy's request_traceparent / traceparent fields),
  * the replica's own log   (logs/api-<X>.log or logs/grpc-<X>.log, field trace_id).
PASS = the same trace ID is in all three places, and the Envoy event and the replica event name the same replica.

Run (project root, stack up, venv active):   python scripts/check_trace_propagation.py
"""
import glob
import json
import os
import sys
import time

import requests

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
from grpc_client import get_product  # noqa: E402
from inora_obs import make_traceparent  # noqa: E402


def find_lines(pattern, trace_id):
    hits = []
    for path in glob.glob(os.path.join(ROOT, "logs", pattern)):
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if trace_id in line:
                    try:
                        hits.append((os.path.basename(path), json.loads(line)))
                    except ValueError:
                        pass
    return hits


def report(name, trace_id, replica_header, envoy_hits, replica_hits):
    envoy_ok = [h for _, h in envoy_hits if trace_id in (h.get("request_traceparent") or "")]
    print(f"\n{name}: trace_id {trace_id}")
    print(f"   answered by replica (response header): {replica_header}")
    for f, h in envoy_hits:
        print(f"   envoy log   : replica={h.get('replica')} path={h.get('path')} status={h.get('response_code') or h.get('grpc_status')} "
              f"request_traceparent_seen={'yes' if trace_id in (h.get('request_traceparent') or '') else 'no'}")
    for f, h in replica_hits:
        print(f"   replica log : {f}  replica={h.get('replica')} endpoint={h.get('endpoint')} message={h.get('message')!r}")
    ok = bool(envoy_ok) and bool(replica_hits) and all(h.get("replica") == replica_header for _, h in replica_hits) \
        and all(h.get("replica") == replica_header for _, h in envoy_hits)
    print(f"   -> {'PASS' if ok else 'FAIL'}")
    return ok


def main():
    results = []
    # ---- HTTP
    tp = make_traceparent()
    trace_id = tp.split("-")[1]
    r = requests.get("http://127.0.0.1:10000/products/clover-pendant", headers={"traceparent": tp}, timeout=5)
    echoed = (r.headers.get("traceparent") or "")
    assert trace_id in echoed, f"replica did not echo the trace id: {echoed}"
    # ---- gRPC
    tp2 = make_traceparent()
    trace_id2 = tp2.split("-")[1]
    resp, err, used, replica2 = get_product("127.0.0.1:10001", "clover-pendant", traceparent=tp2)
    assert err is None, err
    # Envoy buffers its access log (flushed every 1 s with the compose setting, 10 s by default): wait for it.
    deadline = time.time() + 20
    while time.time() < deadline and not (find_lines("envoy-access.log", trace_id)
                                           and find_lines("envoy-access.log", trace_id2)):
        time.sleep(1)
    time.sleep(0.5)
    results.append(report("HTTP", trace_id, r.headers.get("X-Replica"),
                          find_lines("envoy-access.log", trace_id), find_lines("api-*.log", trace_id)))
    results.append(report("gRPC", trace_id2, replica2,
                          find_lines("envoy-access.log", trace_id2), find_lines("grpc-*.log", trace_id2)))
    print("\nOVERALL:", "PASS" if all(results) else "FAIL")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
