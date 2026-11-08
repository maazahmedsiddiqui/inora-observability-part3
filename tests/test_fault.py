import json
import time

from app import create_app
from inora_obs import fault


def test_delay_read_from_file_per_replica(tmp_path):
    f = tmp_path / "delay.json"
    f.write_text(json.dumps({"B": 0.3}))
    fault._cache["at"] = 0.0
    assert fault.delay_for("B", str(f)) == 0.3
    assert fault.delay_for("A", str(f)) == 0.0


def test_bad_or_missing_file_means_no_delay(tmp_path):
    fault._cache["at"] = 0.0
    assert fault.delay_for("B", str(tmp_path / "missing.json")) == 0.0
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    fault._cache["at"] = 0.0
    assert fault.delay_for("B", str(bad)) == 0.0


def test_apply_delay_sleeps(tmp_path):
    f = tmp_path / "d.json"
    f.write_text(json.dumps({"X": 0.2}))
    fault._cache["at"] = 0.0
    t = time.perf_counter()
    assert fault.apply_delay("X", str(f)) == 0.2
    assert time.perf_counter() - t >= 0.19


def test_health_endpoint_is_not_counted_in_metrics(tmp_path):
    client = create_app(db_path=str(tmp_path / "h.db")).test_client()
    r = client.get("/health")
    assert r.status_code == 200 and r.get_json()["status"] == "ok"
    assert b'endpoint="/health"' not in client.get("/metrics").data
