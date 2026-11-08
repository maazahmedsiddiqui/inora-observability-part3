# Assignment 3 – Report Tracker

Everything we must be able to put in the final report (2–3 pages of explanation, excluding charts), collected as we go.
Fill each line the moment the evidence exists. Evidence files go in `evidence/` with the names shown.

## 1. Architecture and shared state (Phase 1)
| Item | Status | Evidence file |
|---|---|---|
| Architecture diagram (client → Envoy → A/B/C, Prometheus, Filebeat, Elasticsearch) | [ ] | `docs/architecture.png` |
| Table: data / rate-limit counters / idempotency records → shared or per-replica | [ ] | in report |
| What goes wrong for anything per-replica (explanation) | [ ] | in report |
| Duplicate-prevention proof across replicas | [ ] | `evidence/partA_idempotency_across_replicas.txt` |
| Replica ID visible in a log line and a metric | [ ] | `evidence/partA_replica_id_*.png` |

## 2. Health-check settings (Phase 4.3)
| Setting | Value |
|---|---|
| Interval | |
| Timeout | |
| Unhealthy threshold | |
| Healthy threshold | |
| Measured time to remove B | |
| Measured time to recover B | |

## 3. Metric and query details (Phase 2)
| Panel | PromQL (HTTP) | PromQL (gRPC) | Window |
|---|---|---|---|
| Request rate per replica | | | |
| Share of total traffic | | | |
| Active requests | | | |
| p50 | | | |
| p95 | | | |
| Errors by status | | | |
- [ ] Prometheus targets page screenshot showing A, B, C, Envoy scraped directly: `evidence/partB_targets.png`
- [ ] Label check: no unique IDs in labels

## 4. Run records (one block per run – copy this template)
```
Run name:            (e.g. B-baseline-HTTP)
Interface:           HTTP | gRPC
Policy / fault:      
Target rate (rps):   
Duration (s):        
Requests sent:       
Successes:           
Failures:            
Client p95 (ms):     
Shares A/B/C (%):    
Dashboard screenshot: evidence/...
Client output file:   evidence/...
Prediction (written BEFORE the run):
Observation:
Explanation:
```


### Recorded runs (pre-checkpoint; final evidence runs are repeated at the evidence checkpoint)

**B-baseline-http** (2026-11-08 00:14:42Z to 00:15:42Z UTC) - Envoy routes to A only
- Target 40 req/s x 60 s; sent 2400, ok 2400, failed 0 (0 %); actual send rate 40.0 req/s (max schedule lag 112 ms, p95 lag 0.9 ms)
- Client p50 8.45 ms, p95 16.96 ms, p99 93.45 ms, max 213 ms; client view of replicas: A 100 %
- Dashboard: A 40 req/s, share A 100 % / B 0 % / C 0 %; server p50 about 2.5 ms; server p95 peaked at 67 ms in the first window then about 5 ms; errors 0
- Prediction was: A handles all traffic, B and C idle. Observation matches.

**B-baseline-grpc** (2026-11-08 00:16:32Z to 00:17:32Z UTC) - Envoy routes to A only
- Target 40 req/s x 60 s; sent 2400, ok 2400, failed 0 (0 %); actual send rate 40.0 req/s (max schedule lag 172 ms, p95 lag 8.6 ms)
- Client p50 6.93 ms, p95 222.76 ms, p99 502.86 ms, max 827.66 ms; client view of replicas: A 100 %
- Dashboard: A 41 req/s max, share A 100 %; server p50 about 3.5 ms; **server p95 peaked at 169 ms**; active requests peaked at 5; errors 0
- A second gRPC run (B-baseline-grpc-2, about 05:25 local) showed the same pattern: server p95 rising to 169 ms near the start of the run, p50 about 3.3 ms, Envoy grpc_in in-flight peaking at 14.

**Observations to explain in the report**
1. The gRPC p95 tail is INSIDE the replica (server-side p95 169 ms is consistent with client p95 223 ms), concentrated at the start of each run; p50 stays about 3 ms. HTTP shows the same shape but milder (67 ms). Candidate causes (not yet tested): warm-up / CPU contention on the laptop's Docker VM (Elasticsearch, Kibana, Filebeat, 6 replicas), gRPC server thread pool (10 workers) queueing, log shipping at run start. Planned: add an unmeasured warm-up phase to loadgen and re-measure; check `docker stats` during a run.
2. `Active requests` is sampled at each 5 s scrape, so with 2-3 ms requests it reads 0 for HTTP even under load. It only becomes visible when requests are slow (Part D delay on B). Say so in the report.
3. gRPC all through ONE client channel, all answered by A, Envoy sees http_backend and grpc_backend healthy members = 1 each (A only).

## 5. Baselines
- [x] Part B baseline HTTP (A only, recorded above) · [x] Part B baseline gRPC (A only, recorded above; tail latency to explain)
- [ ] Part C round-robin HTTP · [ ] Part C round-robin gRPC
- [ ] Comparison of each share with 33 % and explanation of differences

## 6. Part D experiments
| # | Experiment | HTTP | gRPC |
|---|---|---|---|
| 1 | Weighted RR 2:1:1 | [ ] | [ ] |
| 2a | Delay on B, round robin | [ ] | [ ] |
| 2b | Delay on B, least request | [ ] | [ ] |
| 3 | Stop B / restart B (health checks) | [ ] | [ ] |

## 7. Summary table (Phase 4.4)
| Run / interface | Policy and fault | Target / actual rps | A/B/C shares | Client p95 | Error rate | Explanation |
|---|---|---|---|---|---|---|

## 8. Log examples (two required, Phase 2.7 and 4.5)
- [ ] HTTP: Envoy event + replica event for the same trace ID (screenshot + query text)
- [ ] gRPC: Envoy event + replica event for the same trace ID (screenshot + query text)
- [ ] Distribution cross-check: Envoy access-log counts per replica vs dashboard shares, same time range

## 9. Conclusions
- [ ] Strategy for HTTP + reasons from results
- [ ] Strategy for gRPC + reasons from results
- [ ] One workload where we would choose differently
- [ ] Envoy stops: what happens + one improvement
- [ ] Optional: consistent hashing with a 4th replica

## 10. Submission checklist
- [ ] Code/config · [ ] fixed-rate client · [ ] exported dashboard JSON · [ ] README (setup, experiment, recovery commands)
- [ ] Report PDF + Markdown · [ ] reused work cited (A1, A2) · [ ] academic-integrity policy followed
- [ ] No dependencies/data volumes in repo · [ ] Part 1/2 hashes unchanged

## 11. Decisions and notes (running log)
| Date | Decision / note |
|---|---|
| 2026-11-07 | Part 3 started. Baseline = Part 2 code at commit `14d9c40` (copied without git history; Part 1 `546748f`, Part 2 `14d9c40` verified unchanged). |
| 2026-11-07 | Baseline stack verified on the student machine: 95 tests pass, containers up, HTTP + gRPC smoke test OK. |
| 2026-11-07 | Decisions D1–D6 (see MASTER_PLAN.md): per-replica rate limit kept + explained; read-only gRPC `GetProduct` added; replicas A/B/C = containers 1/2/3; Envoy v1.39.1; fault injection via shared fault file (Phase 4). |
| 2026-11-07 | Reused work to cite: Assignment 1 (observability stack), Assignment 2 (HTTP API, gRPC, metrics). |


## Added 2026-11-08 (measurement rule and clean baselines)
- **Measurement rule:** Filebeat is stopped during every measured load run and started again afterwards (it then ships the logs). Reason: on this 4-core laptop Filebeat reading logs during a run raised gRPC client p95 from about 12 ms to 49-223 ms (p99 28 ms -> 337 ms). Mention in the report (method / limitations).
- Clean baselines (Filebeat stopped, A only, 40 rps x 60 s, 2400 sent, 0 failures):
  - HTTP  `GET /products/clover-pendant`: client p50 9.69 / p95 18.1 / p99 100.18 ms, 100 % to A (window 08:44:57-08:45:57 UTC, runs/b-http.json)
  - gRPC `GetProduct`: client p50 7.45 / p95 13.35 / p99 24.26 ms, 100 % to A (window 08:45:58-08:46:58 UTC, runs/b-grpc.json)
  - The earlier gRPC p95 of 223 ms (Filebeat running) is explained by Filebeat load, not by the application.
- Log correlation proved for both interfaces (scripts/es_trace_search.py PASS; Kibana saved search `inora-a3-correlation` shows 2 rows). Envoy log field is `api_kind` (`interface` clashed with Filebeat's index template).
- Part C tools: `envoy/stages/{a-only,round-robin}.yaml`, `scripts/envoy_stage.py` (switch + show cluster members), `scripts/run_report.py` (share per replica from Prometheus, Envoy logs in Elasticsearch, and the client; compares with expected share).
