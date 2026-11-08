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


@pytest.mark.parametrize("name", ["a-only", "round-robin"])
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
