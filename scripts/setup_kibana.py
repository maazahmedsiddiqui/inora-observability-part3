"""setup_kibana.py - create the Kibana data view and one saved search for the Envoy + replica log correlation.

Kibana in this stack keeps no data between `docker compose down` runs, so run this once after the stack is up:
    python scripts/setup_kibana.py

Creates:
  * data view  "Inora logs (filebeat-*)"  on filebeat-*  (time field @timestamp)
  * saved search "A3 - Envoy + replica events by trace_id"  (columns: service_name, replica, interface, endpoint ...)
Then open  http://localhost:5601/app/discover#/view/inora-a3-correlation  and type, in the search bar (KQL):
    trace_id : "<32-hex trace id>"
The result has one Envoy event (service_name: envoy) and one replica event (service_name: inora-api / inora-grpc).
If the saved-search step fails, the data view is still usable: pick it in Discover and add the columns by hand.
"""
import json
import sys
import time

import requests

KIBANA = "http://localhost:5601"
HEADERS = {"kbn-xsrf": "true", "Content-Type": "application/json"}
COLUMNS = ["service_name", "replica", "interface", "endpoint", "path", "status_code", "response_code",
           "grpc_status", "severity", "message", "trace_id"]


def wait_for_kibana(seconds=180):
    end = time.time() + seconds
    while time.time() < end:
        try:
            r = requests.get(f"{KIBANA}/api/status", timeout=5)
            if r.status_code == 200 and r.json().get("status", {}).get("overall", {}).get("level") == "available":
                return True
        except requests.RequestException:
            pass
        print("waiting for Kibana ...")
        time.sleep(5)
    return False


def get_or_create_data_view():
    body = {"data_view": {"title": "filebeat-*", "name": "Inora logs (filebeat-*)", "timeFieldName": "@timestamp"}}
    r = requests.post(f"{KIBANA}/api/data_views/data_view", headers=HEADERS, data=json.dumps(body), timeout=30)
    if r.status_code == 200:
        return r.json()["data_view"]["id"]
    listing = requests.get(f"{KIBANA}/api/data_views", headers=HEADERS, timeout=30).json()
    for dv in listing.get("data_view", []):
        if dv.get("title") == "filebeat-*":
            return dv["id"]
    raise SystemExit(f"could not create the data view: HTTP {r.status_code} {r.text[:300]}")


def create_saved_search(data_view_id):
    body = {
        "attributes": {
            "title": "A3 - Envoy + replica events by trace_id",
            "description": "Type trace_id : \"<id>\" in the search bar: returns the Envoy access-log event and the replica's event.",
            "columns": COLUMNS,
            "sort": [["@timestamp", "asc"]],
            "kibanaSavedObjectMeta": {"searchSourceJSON": json.dumps({
                "query": {"query": "", "language": "kuery"}, "filter": [],
                "indexRefName": "kibanaSavedObjectMeta.searchSourceJSON.index"})},
        },
        "references": [{"name": "kibanaSavedObjectMeta.searchSourceJSON.index", "type": "index-pattern",
                        "id": data_view_id}],
    }
    return requests.post(f"{KIBANA}/api/saved_objects/search/inora-a3-correlation?overwrite=true",
                         headers=HEADERS, data=json.dumps(body), timeout=30)


def main():
    if not wait_for_kibana():
        sys.exit("Kibana did not become available at http://localhost:5601 (is the stack up?)")
    dv = get_or_create_data_view()
    print(f"data view ready: id {dv}")
    r = create_saved_search(dv)
    if r.status_code == 200:
        print("saved search ready: http://localhost:5601/app/discover#/view/inora-a3-correlation")
    else:
        print(f"saved search NOT created (HTTP {r.status_code}): {r.text[:300]}")
        print("The data view works; open Discover, choose it, and add the columns by hand.")


if __name__ == "__main__":
    main()
