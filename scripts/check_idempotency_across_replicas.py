"""check_idempotency_across_replicas.py - prove duplicate prevention works ACROSS replicas and across both doors.

The replicas publish no host ports, so this script runs a tiny client INSIDE chosen replica containers with
`docker exec`. Using ONE Idempotency-Key:

  1. HTTP  POST /orders on api replica B      -> 201 Created (replayed = false)         creates the order
  2. HTTP  POST /orders on api replica C      -> 200 OK      (replayed = true)  same order id
  3. gRPC  PlaceOrder  on grpc replica A      -> OK          (replayed = true)  same order id

PASS means one order was created no matter which replica / door received the repeat: the idempotency
records live in the shared SQLite database, not in any replica's memory.

Run (project root, stack up):   python scripts/check_idempotency_across_replicas.py
"""
import argparse
import json
import subprocess
import sys
import uuid

HTTP_SNIPPET = r'''
import json, sys, urllib.request, urllib.error
url, key = sys.argv[1], sys.argv[2]
body = json.dumps({"product_id": "clover-pendant", "quantity": 1, "payment_token": "tok_visa"}).encode()
req = urllib.request.Request(url, data=body, method="POST",
                             headers={"Content-Type": "application/json", "Idempotency-Key": key})
try:
    r = urllib.request.urlopen(req, timeout=10)
    status, hdr, data = r.status, r.headers, json.load(r)
except urllib.error.HTTPError as e:
    status, hdr, data = e.code, e.headers, json.load(e)
print(json.dumps({"door": "http", "status": status, "replayed": hdr.get("Idempotent-Replayed"),
                  "replica": hdr.get("X-Replica"), "order_id": data.get("id")}))
'''

GRPC_SNIPPET = r'''
import json, sys, grpc
from inora.v1 import inora_pb2, inora_pb2_grpc
target, key = sys.argv[1], sys.argv[2]
with grpc.insecure_channel(target) as ch:
    stub = inora_pb2_grpc.OrderServiceStub(ch)
    resp, call = stub.PlaceOrder.with_call(
        inora_pb2.PlaceOrderRequest(product_id="clover-pendant", quantity=1, payment_token="tok_visa",
                                    idempotency_key=key), timeout=10)
    md = dict(call.initial_metadata())
    print(json.dumps({"door": "grpc", "status": "OK", "replayed": resp.replayed,
                      "replica": md.get("x-replica"), "order_id": resp.order.id}))
'''


def run_in(container, snippet, *args):
    out = subprocess.run(["docker", "exec", container, "python", "-c", snippet, *args],
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise SystemExit(f"docker exec {container} failed:\n{out.stderr or out.stdout}")
    return json.loads(out.stdout.strip().splitlines()[-1])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default="inora-observability-part3")
    a = ap.parse_args()
    key = f"p3-idem-{uuid.uuid4().hex[:10]}"
    steps = [
        ("1  HTTP  on replica B", f"{a.project}-api-2", HTTP_SNIPPET, "http://localhost:5000/orders"),
        ("2  HTTP  on replica C", f"{a.project}-api-3", HTTP_SNIPPET, "http://localhost:5000/orders"),
        ("3  gRPC  on replica A", f"{a.project}-grpc-1", GRPC_SNIPPET, "localhost:50051"),
    ]
    print(f"Idempotency-Key = {key}\n")
    results = []
    for label, container, snippet, target in steps:
        r = run_in(container, snippet, target, key)
        results.append(r)
        print(f"{label:24s} -> {r}")
    ids = {r["order_id"] for r in results}
    ok = (len(ids) == 1
          and str(results[0]["replayed"]).lower() in ("false",)
          and all(str(r["replayed"]).lower() == "true" for r in results[1:])
          and [r["replica"] for r in results] == ["B", "C", "A"])
    print()
    print(f"PASS: one order ({ids.pop()}) created, both repeats replayed" if ok else f"FAIL: results differ: {results}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
