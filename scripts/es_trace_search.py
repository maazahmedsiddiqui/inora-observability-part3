"""es_trace_search.py - show, from Elasticsearch, the Envoy event AND the replica event for one trace id.

  python scripts/es_trace_search.py --latest http          # newest HTTP request seen by Envoy
  python scripts/es_trace_search.py --latest grpc          # newest gRPC call seen by Envoy
  python scripts/es_trace_search.py --trace-id <32 hex>    # a specific request (e.g. from loadgen / a probe)

Same data as the Kibana search `trace_id : "<id>"`; use it for a text copy of the evidence.
Needs the stack up, Filebeat running and a few seconds since the request.
"""
import argparse
import json
import sys
import time

import requests

ES = "http://localhost:9200"


def search(body):
    r = requests.post(f"{ES}/filebeat-*/_search", json=body, timeout=30)
    r.raise_for_status()
    return [h["_source"] for h in r.json()["hits"]["hits"]]


def latest_trace(interface):
    hits = search({"size": 1, "sort": [{"@timestamp": "desc"}],
                   "query": {"bool": {"filter": [{"term": {"service_name": "envoy"}},
                                                 {"term": {"api_kind": interface}},
                                                 {"exists": {"field": "trace_id"}}]}}})
    if not hits:
        sys.exit(f"no Envoy {interface} event with a trace_id in Elasticsearch yet "
                 "(send a request, wait ~5 s, and check that filebeat was restarted after the config change)")
    return hits[0]["trace_id"]


def show(trace_id, raw):
    for _ in range(8):                      # Filebeat can be a few seconds behind: wait for both events
        events = search({"size": 20, "sort": [{"@timestamp": "asc"}],
                         "query": {"match_phrase": {"trace_id": trace_id}}})
        if {e.get("service_name") == "envoy" for e in events} == {True, False}:
            break
        time.sleep(2)
    print(f"trace_id {trace_id}: {len(events)} event(s)\n")
    for e in events:
        who = e.get("service_name")
        if who == "envoy":
            print(f"  ENVOY    replica={e.get('replica')}  {e.get('api_kind')} {e.get('method')} {e.get('path')}  "
                  f"response_code={e.get('response_code')} grpc_status={e.get('grpc_status')}  "
                  f"duration={e.get('duration_ms')} ms  upstream={e.get('upstream_cluster')} {e.get('upstream_host')}")
        else:
            print(f"  REPLICA  replica={e.get('replica')}  service={who}  endpoint={e.get('endpoint')}  "
                  f"severity={e.get('severity')}  message={e.get('message')!r}")
        if raw:
            print("           " + json.dumps(e))
    kinds = {e.get("service_name") == "envoy" for e in events}
    print("\n" + ("PASS: the search returns the Envoy event together with the replica's event"
                  if kinds == {True, False} else "FAIL: expected one Envoy event and one replica event"))
    return 0 if kinds == {True, False} else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--latest", choices=["http", "grpc"])
    g.add_argument("--trace-id")
    ap.add_argument("--raw", action="store_true", help="also print each event as JSON")
    a = ap.parse_args()
    trace_id = a.trace_id or latest_trace(a.latest)
    sys.exit(show(trace_id, a.raw))


if __name__ == "__main__":
    main()
