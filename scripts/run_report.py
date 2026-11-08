"""run_report.py - compare each replica's share of one finished load run, from three sources, with the expected share.

  python scripts/run_report.py runs/c-http.json                      # expected 33.3 % each (round robin)
  python scripts/run_report.py runs/c-http.json --expect A=50,B=25,C=25

Sources, all for the run's own time window (taken from the loadgen JSON):
  prometheus : requests counted by each replica's own metrics (counter after the run minus before)
  envoy logs : Envoy access-log events in Elasticsearch, grouped by the replica Envoy recorded
  client     : which replica answered each request (X-Replica header / x-replica metadata)
Writes <json>.report.json next to the input. Run it after Filebeat has been started again.
"""
import argparse
import collections
import datetime
import json
import sys
import time

import requests

PROM = "http://localhost:9090"
ES = "http://localhost:9200"
REPLICAS = ["A", "B", "C"]


def ts(s):
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp()


def prom_counts(query, at):
    r = requests.get(f"{PROM}/api/v1/query", params={"query": query, "time": at}, timeout=30)
    r.raise_for_status()
    return {x["metric"].get("replica", "?"): float(x["value"][1]) for x in r.json()["data"]["result"]}


def prometheus_share(run):
    if run["interface"] == "http":
        q = f'sum by (replica) (app_requests_total{{endpoint="/products/<product_id>"}})'
    else:
        q = 'sum by (replica) (grpc_server_handled_total{grpc_method="GetProduct"})'
    start, end = ts(run["started_utc"]) - 1, ts(run["ended_utc"]) + 8
    wait = end - time.time()
    if wait > 0:
        print(f"waiting {wait:.0f} s for Prometheus to scrape the end of the run ...")
        time.sleep(wait)
    before, after = prom_counts(q, start), prom_counts(q, end)
    out = {}
    for rep in sorted(set(before) | set(after)):
        b, a = before.get(rep, 0.0), after.get(rep, 0.0)
        out[rep] = int(round(a - b if a >= b else a))          # a < b means the replica restarted: use what it has now
    return out


def envoy_log_counts(run):
    lo = datetime.datetime.fromtimestamp(ts(run["started_utc"]) - 1, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    hi = datetime.datetime.fromtimestamp(ts(run["ended_utc"]) + 8, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    body = {"size": 0, "track_total_hits": True,
            "query": {"bool": {"filter": [{"term": {"service_name": "envoy"}},
                                          {"term": {"api_kind": run["interface"]}},
                                          {"range": {"start_time": {"gte": lo, "lte": hi}}}]}},
            "aggs": {"by_replica": {"terms": {"field": "replica", "size": 20, "missing": "(none)"}}}}
    for _ in range(12):                                     # wait until Filebeat has shipped everything
        r = requests.post(f"{ES}/filebeat-*/_search", json=body, timeout=30)
        r.raise_for_status()
        j = r.json()
        total = j["hits"]["total"]["value"]
        if total >= run["sent"]:
            break
        time.sleep(5)
    return {b["key"]: b["doc_count"] for b in j["aggregations"]["by_replica"]["buckets"]}, total


def shares(counts):
    tot = sum(counts.values())
    return {k: round(100.0 * v / tot, 1) for k, v in sorted(counts.items())} if tot else {}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("json_file")
    ap.add_argument("--expect", default=None, help="e.g. A=50,B=25,C=25 (default: equal shares)")
    a = ap.parse_args()
    run = json.load(open(a.json_file, encoding="utf-8"))
    expect = ({k: float(v) for k, v in (p.split("=") for p in a.expect.split(","))} if a.expect
              else {r: round(100.0 / len(REPLICAS), 1) for r in REPLICAS})
    prom = prometheus_share(run)
    logs, log_total = envoy_log_counts(run)
    client = run.get("client_view_replicas", {})
    print(f"\nRun {run['name']} ({run['interface']})  {run['started_utc']} -> {run['ended_utc']}   "
          f"sent {run['sent']}  ok {run['ok']}  failed {run['failed']}  client p95 {run['p95_ms']} ms")
    print(f"{'':8}{'expected %':>11}{'prometheus':>12}{'%':>7}{'diff':>7}{'envoy log':>11}{'%':>7}{'diff':>7}{'client':>8}{'%':>7}")
    sp, sl, sc = shares(prom), shares(logs), shares(client)
    rows = {}
    for r in REPLICAS:
        e = expect.get(r, 0.0)
        rows[r] = {"expected_pct": e,
                   "prometheus": prom.get(r, 0), "prometheus_pct": sp.get(r, 0.0),
                   "envoy_log": logs.get(r, 0), "envoy_log_pct": sl.get(r, 0.0),
                   "client": client.get(r, 0), "client_pct": sc.get(r, 0.0)}
        d1, d2 = round(sp.get(r, 0.0) - e, 1), round(sl.get(r, 0.0) - e, 1)
        print(f"{r:<8}{e:>11}{prom.get(r, 0):>12}{sp.get(r, 0.0):>7}{d1:>+7}{logs.get(r, 0):>11}{sl.get(r, 0.0):>7}{d2:>+7}"
              f"{client.get(r, 0):>8}{sc.get(r, 0.0):>7}")
    print(f"{'total':<8}{'':>11}{sum(prom.values()):>12.0f}{'':>14}{log_total:>11}{'':>14}{sum(client.values()):>8}")
    ok = log_total == run["sent"] and sum(prom.values()) == run["sent"]
    print("\nCHECK: sent == prometheus total == envoy log total ->", "PASS" if ok else "DIFFERENT (see numbers above)")
    out = a.json_file.replace(".json", ".report.json")
    json.dump({"run": run["name"], "rows": rows, "envoy_log_total": log_total, "counts_match_sent": ok},
              open(out, "w", encoding="utf-8"), indent=2)
    print("written", out)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
