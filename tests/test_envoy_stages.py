"""The Envoy stage configs must differ only in who is in the clusters."""
import os

import pytest
import yaml

STAGES = os.path.join(os.path.dirname(__file__), "..", "envoy", "stages")


def load(name):
    with open(os.path.join(STAGES, name + ".yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def hosts(cfg, cluster):
    c = next(c for c in cfg["static_resources"]["clusters"] if c["name"] == cluster)
    return [e["endpoint"]["address"]["socket_address"]["address"]
            for ep in c["load_assignment"]["endpoints"] for e in ep["lb_endpoints"]], c


def test_a_only_has_one_member_per_cluster():
    cfg = load("a-only")
    assert hosts(cfg, "http_backend")[0] == ["inora-observability-part3-api-1"]
    assert hosts(cfg, "grpc_backend")[0] == ["inora-observability-part3-grpc-1"]


def test_round_robin_has_a_b_c_equal_weight_both_clusters():
    cfg = load("round-robin")
    for cluster, kind in (("http_backend", "api"), ("grpc_backend", "grpc")):
        names, c = hosts(cfg, cluster)
        assert names == [f"inora-observability-part3-{kind}-{n}" for n in (1, 2, 3)]
        assert c["lb_policy"] == "ROUND_ROBIN"
        for ep in c["load_assignment"]["endpoints"]:
            assert all("load_balancing_weight" not in e for e in ep["lb_endpoints"])


@pytest.mark.parametrize("name", ["a-only", "round-robin", "weighted-2-1-1", "least-request", "health-check"])
def test_no_retries_and_grpc_is_http2(name):
    cfg = load(name)
    text = open(os.path.join(STAGES, name + ".yaml"), encoding="utf-8").read()
    code = "\n".join(l.split("#")[0] for l in text.splitlines())      # ignore comments
    assert "retry_policy" not in code
    grpc = next(c for c in cfg["static_resources"]["clusters"] if c["name"] == "grpc_backend")
    assert "http2_protocol_options" in str(grpc["typed_extension_protocol_options"])
    listener = next(l for l in cfg["static_resources"]["listeners"] if l["name"] == "grpc_listener")
    assert "http_connection_manager" in listener["filter_chains"][0]["filters"][0]["name"]


def test_stages_differ_only_in_cluster_members():
    a, rr = load("a-only"), load("round-robin")
    for cfg in (a, rr):
        for c in cfg["static_resources"]["clusters"]:
            c["load_assignment"]["endpoints"] = None
    assert a == rr


def weights(cfg, cluster):
    c = next(c for c in cfg["static_resources"]["clusters"] if c["name"] == cluster)
    return [e.get("load_balancing_weight") for ep in c["load_assignment"]["endpoints"] for e in ep["lb_endpoints"]]


def strip_to_members(cfg):
    for c in cfg["static_resources"]["clusters"]:
        c["load_assignment"]["endpoints"] = None
    return cfg


def test_weighted_2_1_1_only_changes_weights():
    cfg = load("weighted-2-1-1")
    assert weights(cfg, "http_backend") == [2, 1, 1] and weights(cfg, "grpc_backend") == [2, 1, 1]
    assert hosts(cfg, "http_backend")[0] == hosts(load("round-robin"), "http_backend")[0]
    assert strip_to_members(cfg) == strip_to_members(load("round-robin"))


def test_least_request_only_changes_policy():
    cfg = load("least-request")
    for cluster in ("http_backend", "grpc_backend"):
        assert hosts(cfg, cluster)[1]["lb_policy"] == "LEAST_REQUEST"
        assert weights(cfg, cluster) == [None, None, None]
    ref = load("round-robin")
    for c in list(cfg["static_resources"]["clusters"]) + list(ref["static_resources"]["clusters"]):
        c.pop("lb_policy"), c.pop("least_request_lb_config", None)
    assert strip_to_members(cfg) == strip_to_members(ref)


def test_health_check_stage_settings():
    cfg = load("health-check")
    _, http = hosts(cfg, "http_backend")
    _, grpc = hosts(cfg, "grpc_backend")
    for c in (http, grpc):
        hc = c["health_checks"][0]
        assert (hc["interval"], hc["timeout"], hc["unhealthy_threshold"], hc["healthy_threshold"]) == ("2s", "1s", 2, 2)
        assert c["dns_refresh_rate"] == "600s"          # so removal is done by the health check, not by DNS
        assert c["lb_policy"] == "ROUND_ROBIN"
    assert http["health_checks"][0]["http_health_check"]["path"] == "/health"
    assert "tcp_health_check" in grpc["health_checks"][0]
