# What is shared between replicas, and what is not (Assignment 3, Part A)

The HTTP API and the gRPC service each run as three identical copies (A, B, C). Envoy may send any request to
any copy, so for every piece of state we must know: **is it shared by all replicas, or does each replica have
its own?** If it is per replica, what goes wrong?

| State | Where it lives | Shared or per replica? | What happens with several replicas |
|---|---|---|---|
| Products, stock, orders | One SQLite file on the Docker volume `inora-data`, mounted into every replica | **Shared** | Correct. Writes use `BEGIN IMMEDIATE`, so only one replica writes at a time and stock can never go negative. Limit: SQLite allows one writer at a time, so writes queue under load (not a problem for the read-only test traffic). |
| Idempotency records (`Idempotency-Key` to order id) | Table `idempotency_keys` in the same SQLite file | **Shared** | Correct. A retry that lands on another replica, or on the other interface (HTTP vs gRPC), finds the stored key and returns the same order instead of creating a duplicate. Proven by `scripts/check_idempotency_across_replicas.py` (B creates, C and A replay). |
| Rate-limit counters (5 requests / 10 s per client address on `POST /orders`) | A Python dict inside each API process (`FixedWindowRateLimiter`) | **Per replica** | The limit is no longer exact. With A only, a client gets 5 accepted + the rest `429`. With round robin over three replicas each replica counts separately, so about 15 requests are accepted in 10 s (about 3x the intended limit) and which requests are rejected depends on routing. Counters also vanish when a replica restarts. Shown by `scripts/ratelimit_demo.py` (A only now, round robin later). A shared counter store (for example in the database or Redis) or a limit enforced at Envoy would fix it. |
| Prometheus metrics (counters, histograms, active requests) | In the memory of each process, exposed at its own `/metrics` | **Per replica** | Intended. Prometheus scrapes every replica separately and the `replica` label (A/B/C) tells the series apart, so dashboards can show each replica and the total (`sum`). A restart resets that replica's counters (Prometheus handles this in `rate()`). |
| Product stock gauge (`inora_product_stock`) | Read from the shared database at scrape time | **Shared** (read by every replica) | All replicas report the same value; for totals use `max` or one replica, not `sum`. |
| Log files | One file per replica in `./logs` (`api-A.log`, `grpc-B.log`, ...) plus Envoy's `envoy-access.log` | **Per replica** | Intended. Separate files stop replicas interleaving lines in one file. Every line carries `replica`, `trace_id` and `service_name`, so Elasticsearch/Kibana can join the Envoy event with the replica event for the same request. |
| Trace context (`traceparent`) | Travels in the request (HTTP header / gRPC metadata) and is echoed back by the replica | **Stateless** | Nothing to share. Envoy forwards the header unchanged. Proven by `scripts/check_trace_propagation.py`. |
| Replica identity (A/B/C) | Computed at start-up from the container name (`REPLICA_BASE` DNS lookup) | **Per replica** | Written to every log line, the `X-Replica` header, gRPC `x-replica` metadata and `inora_replica_info`. |
| HTTP connections / gRPC channels | Between client and Envoy, and Envoy and replica | **Per connection** | A gRPC client keeps one long-lived HTTP/2 connection to Envoy. Because Envoy's gRPC listener understands HTTP/2 it can pick a replica **per call**, not per connection (this matters in Part C). |

## Summary
* **Business data and duplicate prevention are shared**, so any replica can serve any request and a retry on a
  different replica is safe.
* **The rate limiter is the one piece of behaviour that breaks** (per replica counters). We keep it per replica on
  purpose, measure the effect and explain it in the report.
* **Metrics and logs are per replica by design** and are made comparable with the `replica` label / field.
