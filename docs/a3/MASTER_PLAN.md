# Assignment 3 – Master Plan and Completion Checklist

Enterprise Software Development, Fall 2026 · Load Balancing and Observability (Envoy)
Repo: `inora-observability-part3` (new). Part 1 and Part 2 repos are **read-only references**.

**Rule of the road:** we do not start a phase until the previous phase's "Exit gate" is fully ticked.

Legend: `[ ]` open · `[~]` delivered, awaiting check · `[x]` done · **GATE** = must pass before moving on

---

## Protected baselines (must never change)

| Repo | HEAD commit when Part 3 started (2026-11-07) |
|---|---|
| Part 1 `inora-observability` | `546748fac8fd287a13b5ec4b774f36818a1832a0` |
| Part 2 `inora-observability-part2` | `14d9c40d8c4ed3c92ae21a4007041f7a5b898e19` |

Check at any time (and at the very end):
```powershell
git ls-remote https://github.com/maazahmedsiddiqui/inora-observability.git HEAD
git ls-remote https://github.com/maazahmedsiddiqui/inora-observability-part2.git HEAD
```
Both hashes must match the table.

---

## Phase 0 – Safe repo setup
- [x] 0.1 New empty GitHub repo `inora-observability-part3` (no README/.gitignore/license)
- [x] 0.2 Fresh clone of Part 2 into a NEW folder, `.git` removed, `git init`, remote = Part 3 only
- [x] 0.3 Remove Part 2-only files (old report PDF, `Video` link file, old evidence) – keep code
- [x] 0.4 First commit "Baseline: Part 2 code (reused work)" pushed to Part 3
- [x] 0.5 Part 1/Part 2 hashes re-checked, unchanged
- [x] 0.6 `docker compose up -d --build` works on the untouched baseline and `python -m pytest` shows 95 passed
- **GATE 0 (PASSED 2026-11-07):** Part 3 repo has the baseline, Part 2 untouched, baseline stack runs.

## Phase 1 – Part A: replicas and routing (Envoy → A only)
Split in two: **1a** = infrastructure (compose scaling, replica id, Envoy A-only, Prometheus targets); **1b** = proof + documents (shared-state table, architecture diagram, rate-limit baseline, idempotency evidence).
- [x] 1.1 Decisions D1–D4 settled (see Decision log)
- [x] 1.2 Compose rewritten for scaling (`api` and `grpc` replicas x3, no `container_name`, no fixed host ports on replicas, fixed project `name:`)
- [x] 1.3 Replica identifier in **logs** (new `replica` field) and **metrics** (`replica` label via Prometheus relabeling)
- [x] 1.4 Per-replica log files so three replicas never write the same file
- [x] 1.5 Envoy added: HTTP listener → cluster A only
- [x] 1.6 Envoy gRPC listener → cluster A only (HTTP/2 from the start, so Part C is a one-line change)
- [x] 1.7 B and C running but absent from Envoy clusters
- [x] 1.8 `traceparent` still reaches the replica through Envoy (HTTP header and gRPC metadata)
- [x] 1.9 Shared-state table written: data / rate-limit counters / idempotency records – shared or per-replica, and what breaks
- [x] 1.10 Architecture diagram drawn
- [x] 1.11 Duplicate prevention proven across replicas (same Idempotency-Key sent to two different replicas → one order)
- **GATE 1 (PASSED 2026-11-08):** one HTTP call and one gRPC call through Envoy reach only A; B and C healthy and idle; diagram + shared-state table done.

## Phase 2 – Part B: observe the baseline
- [~] 2.1 Prometheus scrapes A, B, C and Envoy **directly** (not through Envoy's balanced route)
- [x] 2.2 One Grafana dashboard, HTTP and gRPC, **per replica**: request rate + share of total, active requests, p50/p95 (state window), errors by status
- [x] 2.3 Fixed-rate, open-loop test client (does not wait for each response before sending the next); records rate, requests sent, successes, failures, client p95
- [~] 2.4 Baseline run HTTP and gRPC: A = 100 %, B/C idle
- [~] 2.5 Envoy JSON access logs include selected replica + trace ID
- [~] 2.6 Filebeat ships Envoy logs to Elasticsearch
- [~] 2.7 One Kibana search per interface returning Envoy event **and** replica event together (screenshots)
- [x] 2.8 No unique IDs in metric labels (verify)
- [~] 2.9 Dashboard JSON exported
- **GATE 2:** baseline numbers recorded, dashboard shows A-only, both log searches work.

## Phase 3 – Part C: enable load balancing
- [ ] 3.1 B and C added to Envoy HTTP cluster, equal-weight round robin
- [ ] 3.2 B and C added to Envoy gRPC cluster, round robin
- [ ] 3.3 gRPC listener confirmed as HTTP/2 (per-call routing, not per-connection TCP)
- [ ] 3.4 Same workload repeated for HTTP and gRPC
- [ ] 3.5 Each replica ≈ 33 %; compare with 33 % and explain differences vs the A-only baseline
- [ ] 3.6 Screenshots + client results saved = **round-robin baseline for Part D**
- **GATE 3:** ~1/3 each for both interfaces, recorded.

## Phase 4 – Part D: experiments (HTTP and gRPC reported separately)
Common rules: start each from healthy Part C setup · same workload · restore normal afterwards · client retries and circuit breakers **off** (client and Envoy) · for each: prediction → observation → explanation + charts + client results.
- [ ] 4.1 Weighted round robin A:B:C = 2:1:1 (expect 50/25/25), explain latency and active requests
- [ ] 4.2 Least request: equal weights, fixed delay on B; run with round robin, then with least request (same delay, same workload); compare B's share, active requests, client p95
- [ ] 4.3 Failure and recovery: round robin, no delay; configure active health checks (record interval, timeout, unhealthy/healthy thresholds); stop B during traffic, then restart; show redistribution + client errors; relate removal/recovery time to settings
- [ ] 4.4 Summary table of all runs (Run/interface, policy and fault, target/actual rps, A/B/C shares, client p95, error rate, explanation)
- [ ] 4.5 One distribution result cross-checked against Envoy access logs for the same time range
- [ ] 4.6 Note the two hints: higher weight ≠ more capacity; slow replica can still pass health checks
- **GATE 4:** all runs in the table, normal behaviour restored, log cross-check done.

## Phase 5 – Conclusions (and optional)
- [ ] 5.1 Chosen strategy for HTTP and for gRPC, justified with our results
- [ ] 5.2 One workload where we would choose differently
- [ ] 5.3 What happens if Envoy stops + one improvement (no implementation needed)
- [ ] 5.4 Optional: consistent hashing + 4th replica, show which product IDs change destination

## Evidence checkpoint (agreed 2026-11-08)
After GATE 3 (round robin working for HTTP and gRPC) we STOP and collect all Part A to C evidence into `evidence/` with one script plus a screenshot list, before starting Part D. Part D evidence is collected per run.

## Phase 6 – Submission package
- [ ] 6.1 Code/configuration (excluding dependencies and data volumes)
- [ ] 6.2 Fixed-rate test client
- [ ] 6.3 Exported Grafana dashboard JSON
- [ ] 6.4 README: setup, experiment commands, recovery commands
- [ ] 6.5 Report (2–3 pages of explanation, excluding charts): architecture + shared state, health-check settings, metric/query details, baselines, results table, two proxy/backend log examples, conclusions
- [ ] 6.6 Report delivered as Markdown **and** PDF
- [ ] 6.7 Reused work cited (A1, A2); academic-integrity policy followed (note: A2 skipped this "for now" – A3 explicitly requires it; decide wording with the course manual)
- [ ] 6.8 Final check: Part 1/2 hashes unchanged, fresh clone of Part 3 builds and runs

---

## Decision log

| ID | Question | Decision (2026-11-07) |
|---|---|---|
| D1 | Rate-limit counters: per replica or shared? | **Keep per replica (in memory)**; explain in report what goes wrong (effective limit ≈ 5 × replicas, depends on routing, resets on restart); show with `scripts/ratelimit_demo.py` (A-only now, round robin in Phase 3). Better fix = shared store; mentioned as improvement. |
| D2 | gRPC test operation | **Added read-only unary `inora.v1.CatalogService/GetProduct`.** `PlaceOrder` unchanged. |
| D3 | HTTP test operation | `GET /products/{product_id}` (read-only, not rate limited). |
| D4 | Replica names | Compose containers `inora-observability-part3-<service>-<n>`; **1 = A, 2 = B, 3 = C**. Found by DNS lookup (`REPLICA_BASE`); also sent as `X-Replica` header / `x-replica` gRPC metadata. |
| D5 | Envoy image | `envoyproxy/envoy:v1.39.1` (pinned; latest stable line found on the Envoy releases page, 2026-11-07). |
| D6 | Fault injection for Phase 4 (delay on B only) | Scaled replicas share identical env, so the delay cannot come from env vars. Plan: a small fault file on the shared data volume read per request, keyed by replica name. Implement in Phase 4. |

### Risks to handle later
- **R1 – DNS vs health checks (Phase 4.3).** Envoy cluster type is `STRICT_DNS` with `dns_refresh_rate: 5s`. When replica B is stopped, Docker DNS drops its name and Envoy may remove B because of DNS, not because of the health check. Before measuring removal/recovery time we must separate the two (e.g. long DNS refresh, or compare with the health-check events in Envoy stats) and report honestly what was measured.
- **R2 – Envoy config not testable in the sandbox.** Validate on the student machine with `--mode validate` before each stage.
- **R3 – Slow internet.** Build images one at a time; rerun on timeout.

## Known gaps in the Part 2 code that Part 3 must fix (found by reading the repo) — all addressed in Phase 1a

1. `docker-compose.yml` uses `container_name` and fixed host ports (`5000`, `50051`, `9102`) on `api`/`grpc` → these block `--scale`.
2. Logs: all replicas would append to the same `app.log`/`grpc.log` → need per-replica files.
3. `prometheus.yml` scrapes `api:5000` / `grpc:9102` by service name → with replicas this hits one random replica; needs one target per replica plus Envoy's admin port.
4. No replica identifier anywhere (`inora_obs/logs.py` has no `replica` field; no `replica` label).
5. Rate limiter is in memory per process (`app.py`) and keyed on `X-Forwarded-For`; behind Envoy the client address changes.
6. Existing `caller.py` has retries + circuit breaker → the new load client must have neither.
7. Envoy has to be added (HTTP listener, gRPC HTTP/2 listener, admin, JSON access log, health checks later).

---

## SESSION HANDOFF (written 2026-11-08, end of day 2)

**Where we are:** Gate 0 and Gate 1 passed. Part B built and working on the student machine: dashboard `inora-a3-load-balancing` shows A = 100 %, B and C idle for HTTP and gRPC; `scripts/loadgen.py` baseline runs recorded in REPORT_TRACKER.md (section 4). Envoy still routes to A only (`envoy/envoy.yaml`).

**Still open for Gate 2 (do first tomorrow):**
1. Run `python scripts/es_trace_search.py --latest http` and `--latest grpc`: each must print one ENVOY and one REPLICA line and PASS. Then the same search in Kibana (`trace_id : "<id>"`, saved search `inora-a3-correlation`, created by `scripts/setup_kibana.py`; its last output line was not seen). Screenshots later at the evidence checkpoint.
2. Understand the gRPC p95 tail (see REPORT_TRACKER observations). Plan: add `--warmup` seconds (sent but not counted) to loadgen; re-run both baselines; look at `docker stats`.
3. Commit Part B (`git add . ; git commit -m "Part B: ..." ; git push`).

**Next build (Part C):** keep Envoy stage configs as separate files in `envoy/stages/` (a-only, round-robin, weighted-2-1-1, least-request, health-check variants) with a small switch script that copies one to `envoy/envoy.yaml` and restarts Envoy; B and C added to both clusters, equal weights, gRPC listener already HTTP/2. Then run both workloads, compare each share with 33 %, rerun `scripts/ratelimit_demo.py --count 15` (expect about 15 accepted instead of 5).

**Evidence checkpoint (agreed):** after Gate 3, one script re-runs A-only baseline and round robin for both interfaces and saves everything into `evidence/`, plus a screenshot list with file names.

**Known notes:** Envoy `dns_refresh_rate` deprecation warning (harmless in v1.39.1); Envoy access log flushed every 1 s via `--file-flush-interval-msec`; after recreating containers wait about 10 s for Envoy's DNS; PowerShell needs `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` per window; internet is slow so build images one at a time; Grafana dashboard changes may need `docker compose restart grafana`.
