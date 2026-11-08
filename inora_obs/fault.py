"""Fault injection for the Part D experiments: a fixed delay on chosen replicas.

faults/delay.json (shared with every replica, mounted read-only) maps a replica letter to seconds, e.g. {"B": 0.4}.
Empty file / no entry = no delay. The file is re-read at most every 0.25 s, so changing it takes effect at once
without restarting anything. Only the test operations (GET /products/<id>, gRPC GetProduct) call apply_delay().
"""
import json
import os
import time

FAULT_FILE = os.environ.get("FAULT_FILE", "/app/faults/delay.json")
_cache = {"at": 0.0, "data": {}}


def _load(path):
    now = time.monotonic()
    if now - _cache["at"] < 0.25:
        return _cache["data"]
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        data = {}
    _cache.update(at=now, data=data)
    return data


def delay_for(replica, path=None):
    try:
        return max(0.0, float(_load(path or FAULT_FILE).get(replica, 0) or 0))
    except (TypeError, ValueError):
        return 0.0


def apply_delay(replica, path=None):
    d = delay_for(replica, path)
    if d:
        time.sleep(d)
    return d
