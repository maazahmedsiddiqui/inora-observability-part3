# What is shared between replicas, and what is not (Assignment 3, Part A)

The HTTP API and the gRPC service each run as three identical copies (A, B, C). Envoy may send any request to
any copy, so for every piece of state we must know: **is it shared by all replicas, or does each replica have
its own?** If it is per replica, what goes wrong?

*Audited against the code on 2026-11-08; the last column says where each statement can be checked.*

| State | Where it lives | Shared or per replica? | What happens with several replicas | Checked in |
|---|---|---|---|---|
| Products, stock, orders | One SQLite file on the Docker volume `inora-data`, mounted into every API and gRPC replica | **Shared** | Correct. Every write runs inside `BEGIN IMMEDIATE`, so only one replica writes at a time. Stock cannot go negative: the update only succeeds `WHERE stock >= quantity`, and the table also has `CHECK (stock >= 0)`. Limits: SQLite allows one writer at a time, so concurrent writes queue (a writer waits up to 10 s for the lock, then fails with "database is locked"); the database uses the default journal mode, so a read can briefly wait while a write commits. Our test traffic is read-only, so this does not affect the experiments. | `inora_core/service.py` (`place_order`, `_conn`, `SCHEMA`); `docker-compose.yml` volumes |
| Idempotency records (`Idempotency-Key` to order id) | Table `idempotency_keys` in the same SQLite file | **Shared** | Correct. The key and the order are written in the same transaction. A retry that lands on another replica, or on the other interface (HTTP vs gRPC), finds the stored key and returns the same order instead of creating a duplicate. The same key with a different request is rejected as a conflict. | `place_order`; `scripts/check_idempotency_across_replicas.py` (B creates, C and A replay: PASS) |
| Rate-limit counters (5 requests / 10 s per client address) | A Python dict inside each **HTTP API** process (`FixedWindowRateLimiter`); applies to `POST /orders` only. **gRPC has no rate limit.** | **Per replica** | The limit is no longer exact. With A only, a client gets 5 accepted and the rest `429`. With round robin over three replicas each replica counts separately, so about 15 requests are accepted in 10 s (about 3x the intended limit), and which requests are rejected depends on routing. Measured in Part C: 15 `POST /orders` in a row through round robin gave 15 accepted, 5 on each replica, none rejected. Counters also vanish when a replica restarts. A shared counter store, or a limit enforced at Envoy, would fix it. The client key is the address in `X-Forwarded-For` (set by Envoy), so everything coming from one machine counts as one client. | `app.py` (`FixedWindowRateLimiter`, `place_order`); `scripts/ratelimit_demo.py` (A only: 5 accepted, 10 rejected; round robin: 15 accepted, 5 per replica) |
| Prometheus metrics: request counts, latency histograms, active requests, order and rate-limit counters | In the memory of each process, exposed at that replica's own `/metrics` | **Per replica** | Intended. Prometheus scrapes every replica separately and the `replica` label (A/B/C) tells the series apart, so dashboards can show each replica and the total (`sum`). A restart resets that replica's counters (`rate()` handles this). | `app.py`, `grpc_metrics.py`; `prometheus.yml` |
| Product stock gauge (`inora_product_stock`) | **gRPC replicas only.** Read from the shared database at scrape time | **Shared data**, reported by each gRPC replica | All three gRPC replicas report the same value, so for a total use `max` (or one replica), never `sum`. The HTTP API does not export this gauge. | `grpc_metrics.py` (`StockCollector`); registered in `grpc_server.py` |
| Log files | One file per replica in `./logs` (`api-A.log`, `grpc-B.log`, ...) plus Envoy's `envoy-access.log` | **Per replica** | Intended. Separate files stop replicas interleaving lines in one file. Every replica line carries `replica`, `trace_id` and `service_name`, and Envoy's line carries `replica` and the trace headers, so Kibana can join the Envoy event with the replica event for the same request. | `inora_obs/logs.py`; `ls logs`; `scripts/check_trace_propagation.py` |
| Trace context (`traceparent`) | Travels in the request (HTTP header / gRPC metadata) and is echoed back by the replica | **Stateless** | Nothing to share. Envoy forwards the header unchanged. | `scripts/check_trace_propagation.py` (HTTP and gRPC: PASS) |
| Replica identity (A/B/C) | Computed at start-up from the container name (`REPLICA_BASE` DNS lookup) | **Per replica** | Written to every log line, the `X-Replica` header, gRPC `x-replica` metadata and `inora_replica_info`. | `inora_obs/replica.py`; `docker exec ... REPLICA` (A, B, C) |
| HTTP connections / gRPC channels | Client to Envoy, and Envoy to each replica | **Per connection** | A gRPC client keeps one long-lived HTTP/2 connection to Envoy. Envoy's gRPC listener understands HTTP/2 and chooses a replica **per call**, not per connection. Verified in Part C: one client connection, 2400 calls, 800 on each replica. | `envoy/envoy.yaml` (`grpc_listener`, `http2_protocol_options`) |

## Summary
* **Business data and duplicate prevention are shared**, so any replica can serve any request and a retry on a
  different replica is safe.
* **The rate limiter is the one piece of behaviour that breaks** (per replica counters, HTTP only). We keep it
  per replica on purpose, measure the effect and explain it in the report.
* **Metrics and logs are per replica by design** and are made comparable with the `replica` label / field.

## Diagram notes
`architecture.png` shows the request path, the shared database, logging and monitoring. It does not draw
`node-exporter` (host metrics, scraped by Prometheus) or `swagger-ui` (API documentation page, calls the API
through Envoy), which play no part in the load-balancing experiments.
