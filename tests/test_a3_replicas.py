"""Assignment 3 tests: replica identity (logs, header, metric) and the read-only gRPC GetProduct call."""
import json
import logging
import socket

import grpc
import pytest

import grpc_metrics as m
import grpc_server
from app import create_app
from grpc_client import get_product
from inora_core import Store
from inora_obs import REPLICA, JsonFormatter, make_traceparent, resolve_replica_id, setup_file_logging


# ---------------- replica identity ----------------
def test_explicit_replica_id_wins():
    assert resolve_replica_id({"REPLICA_ID": "Z", "REPLICA_BASE": "x"}) == "Z"


def test_replica_found_by_dns_lookup():
    table = {"abc123": "10.0.0.3", "proj-api-1": "10.0.0.2", "proj-api-2": "10.0.0.3", "proj-api-3": "10.0.0.4"}

    def resolver(name):
        if name not in table:
            raise socket.gaierror(name)
        return table[name]

    assert resolve_replica_id({"REPLICA_BASE": "proj-api"}, resolver, lambda: "abc123") == "B"
    table["abc123"] = "10.0.0.4"
    assert resolve_replica_id({"REPLICA_BASE": "proj-api"}, resolver, lambda: "abc123") == "C"


def test_replica_falls_back_to_hostname():
    def resolver(name):
        raise socket.gaierror(name)

    assert resolve_replica_id({"REPLICA_BASE": "proj-api"}, resolver, lambda: "0123456789abcdef") == "0123456789ab"
    assert resolve_replica_id({}, resolver, lambda: "box") == "box"


def test_log_line_carries_replica():
    rec = logging.LogRecord("t", logging.INFO, __file__, 1, "hello", None, None)
    line = json.loads(JsonFormatter("svc").format(rec))
    assert line["replica"] == REPLICA and line["service_name"] == "svc"


def test_log_file_name_contains_replica(tmp_path):
    root = logging.getLogger()
    saved = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
    for h in saved:
        root.removeHandler(h)
    try:
        setup_file_logging("svc", str(tmp_path / "x-{replica}.log"))
        added = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert added and added[0].baseFilename.endswith(f"x-{REPLICA}.log")
        root.removeHandler(added[0])
        added[0].close()
    finally:
        for h in saved:
            root.addHandler(h)


# ---------------- HTTP ----------------
@pytest.fixture
def client(tmp_path):
    app = create_app(db_path=str(tmp_path / "a3.db"), rate_limit=5, rate_window=10)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_every_http_response_names_its_replica(client):
    assert client.get("/products/clover-pendant").headers["X-Replica"] == REPLICA
    assert client.get("/products/nope").headers["X-Replica"] == REPLICA        # errors too
    assert client.get("/no-such-route").headers["X-Replica"] == REPLICA


def test_http_metrics_report_replica_identity(client):
    body = client.get("/metrics").get_data(as_text=True)
    assert f'inora_replica_info{{reported_replica="{REPLICA}"}} 1.0' in body


# ---------------- gRPC GetProduct ----------------
@pytest.fixture
def target(tmp_path):
    server, port = grpc_server.build_server(Store(str(tmp_path / "g.db")), port=0)
    server.start()
    yield f"127.0.0.1:{port}"
    server.stop(0)


def handled(code):
    return m.GRPC_REGISTRY.get_sample_value(
        "grpc_server_handled_total",
        {"grpc_service": "inora.v1.CatalogService", "grpc_method": "GetProduct", "grpc_code": code}) or 0.0


def test_get_product_ok_and_names_replica(target):
    before = handled("OK")
    resp, err, tp, replica = get_product(target, "clover-pendant")
    assert err is None and replica == REPLICA
    assert resp.product.id == "clover-pendant" and resp.product.price_pkr == 4500 and resp.product.stock > 0
    assert handled("OK") == before + 1


def test_get_product_unknown_is_not_found(target):
    before = handled("NOT_FOUND")
    resp, err, tp, replica = get_product(target, "nope")
    assert resp is None and err.code() == grpc.StatusCode.NOT_FOUND
    assert dict(err.trailing_metadata())["error-code"] == "not_found"
    assert replica == REPLICA
    assert handled("NOT_FOUND") == before + 1


def test_get_product_keeps_the_callers_trace_id(target):
    tp = make_traceparent()
    _, err, used, _ = get_product(target, "clover-pendant", traceparent=tp)
    assert err is None and used == tp


def test_get_product_shares_the_channel(target):
    with grpc.insecure_channel(target) as ch:
        results = [get_product(target, "clover-pendant", channel=ch) for _ in range(5)]
    assert all(r[1] is None for r in results)


def test_replica_info_metric_is_exposed():
    assert m.GRPC_REGISTRY.get_sample_value("inora_replica_info", {"reported_replica": REPLICA}) == 1.0
