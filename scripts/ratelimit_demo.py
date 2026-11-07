"""ratelimit_demo.py - show what the PER-REPLICA rate limiter does when requests are spread across replicas.

Sends N `POST /orders` (a different Idempotency-Key each) through Envoy as fast as possible from this machine
and counts 201 / 429 per replica. The limit is 5 requests per 10 s per client address, counted in each
replica's own memory:
  Envoy -> replica A only :  5 accepted, N-5 rejected
  round robin over A,B,C  :  up to 15 accepted (about 5 per replica) - the limit is effectively 3x

Wait at least 10 s between runs so the windows reset.   Run:  python scripts/ratelimit_demo.py --count 15
"""
import argparse
import collections
import os
import uuid

import requests


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--http", default=os.environ.get("INORA_HTTP_BASE", "http://127.0.0.1:10000"))
    ap.add_argument("--count", type=int, default=15)
    a = ap.parse_args()
    per = collections.defaultdict(collections.Counter)
    with requests.Session() as s:
        for _ in range(a.count):
            r = s.post(f"{a.http}/orders", timeout=10,
                       json={"product_id": "clover-pendant", "quantity": 1, "payment_token": "tok_visa"},
                       headers={"Idempotency-Key": f"rl-{uuid.uuid4().hex[:12]}"})
            per[r.headers.get("X-Replica", "?")][r.status_code] += 1
    total = collections.Counter()
    for replica in sorted(per):
        print(f"replica {replica}: {dict(per[replica])}")
        total.update(per[replica])
    print(f"total: {dict(total)}   (201 = accepted, 429 = rate limited)")


if __name__ == "__main__":
    main()
