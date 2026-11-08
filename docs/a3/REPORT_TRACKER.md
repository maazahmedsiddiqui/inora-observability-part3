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

## Part C results (round robin A/B/C, equal weight, 40 rps x 60 s, Filebeat stopped, 2400 sent each)
- HTTP: 2400 ok, 0 failed. Client p50 9.56 / p95 17.77 / p99 54.49 ms. Shares A 800 / B 801 / C 799 (33.3 / 33.4 / 33.3 %). Prometheus, Envoy access logs and client agree exactly (window 08:50:51-08:51:51 UTC, runs/c-http.json).
- gRPC: 2400 ok, 0 failed. Client p50 6.89 / p95 12.5 / p99 41.18 ms. Shares 800 / 800 / 800 (33.3 % each) (window 08:51:52-08:52:52 UTC, runs/c-grpc.json). Per-call routing works because the gRPC listener is an HTTP/2-aware HTTP connection manager; the client still uses one connection.
- Difference from A-only baseline: A went 100 % -> 33.3 %, B and C 0 % -> 33.3 %. Client p95 stayed about the same (HTTP 18.1 -> 17.8 ms, gRPC 13.35 -> 12.5 ms) because 40 rps is far below what one replica can handle, so spreading the load does not make anything faster. Round robin gives exactly 1/3 because requests are handed out in turn.
- Rate limit through round robin: 15 POST /orders in a row -> 15 accepted (5 on each replica), 0 rejected. A-only stage allows only 5. The limit is per replica (in memory), so the effective limit is 5 x number of replicas. This is the "what goes wrong" example for the shared-state section.

## Part D: predictions (written BEFORE the runs, 2026-11-08)
Common setup: Part C round robin as the starting point, 40 req/s x 60 s, no retries, no circuit breaker, Filebeat stopped while measuring, delay = fixed +400 ms on replica B for GET /products/<id> and gRPC GetProduct (`scripts/fault.py set B 0.4`, read from faults/delay.json).
1. **Weighted 2:1:1** - shares 50 / 25 / 25 %. A higher weight sends A more requests but adds no capacity. At 40 req/s every replica is far from busy, so client p95 should stay about the same as the round-robin baseline. A's request rate doubles to about 20 req/s; its active-request value stays near 0 because each request takes only a few ms.
2a. **Round robin, B +400 ms** - round robin ignores slowness: still 33 / 33 / 33 %. B holds about 13.3 req/s x 0.4 s = ~5 requests at once, A and C about 0. About one third of requests take 400 ms or more, so client p95 is about 400 ms or higher (p50 stays normal).
2b. **Least request, B +400 ms** - Envoy picks 2 replicas at random and gives the call to the one with fewer active requests (default choice count 2), so a busy B loses most comparisons. B's share falls well below 33 % (my guess 5-11 %), its active requests fall, client p95 drops compared with 2a (it may stay above normal while B still gets more than 5 % of requests).
3. **Failure and recovery** (health checks: interval 2 s, timeout 1 s, 2 failures to remove, 2 passes to restore; HTTP /health, gRPC TCP connect; DNS refresh slowed to 600 s so the health check, not DNS, removes B) - after B is stopped Envoy marks it unhealthy after about 2-4 s (2 failed checks at 2 s spacing); requests sent to B in that time fail (no retries): about 13 req/s x 2-4 s = 25-55 client errors, then A and C take 50 % each. After B is started it needs a moment to boot, then 2 passed checks: recovery about 4-8 s; afterwards shares return to 33 % each and errors stop. HTTP and gRPC should behave alike. A slow replica would still pass these health checks (experiment 2 shows that: B is slow but healthy).

Notes for the report: active-request gauge is sampled every 5 s by Prometheus, so it only shows values for slow requests (experiment 2). Health-check settings for the report: interval 2 s, timeout 1 s, unhealthy_threshold 2, healthy_threshold 2, no_traffic_interval 2 s.

## Part D: observations (run 2026-11-08 ~22:00-22:40 local, all 2400 sent per run, 3600 for failure runs)
All runs: 40 req/s, no retries, Filebeat stopped while measuring. Envoy log total == requests sent in every run (distribution cross-check PASS for all 12 runs, see evidence/part-d/*/*/shares.txt).
| Run | A / B / C (Envoy log) | Client p95 | Errors |
|---|---|---|---|
| weighted HTTP | 1201 / 600 / 599 = 50.0 / 25.0 / 25.0 % | 23.17 ms | 0 |
| weighted gRPC | 1200 / 600 / 600 = 50 / 25 / 25 % | 16.01 ms | 0 |
| delay B +400 ms, round robin HTTP | 800 / 800 / 800 | 415.72 ms | 0 |
| delay B +400 ms, round robin gRPC | 800 / 800 / 800 | 412.29 ms | 0 |
| delay B +400 ms, least request HTTP | 1052 / 304 / 1044 = 43.8 / 12.7 / 43.5 % | 412.39 ms | 0 |
| delay B +400 ms, least request gRPC | 1065 / 316 / 1019 = 44.4 / 13.2 / 42.5 % | 410.19 ms | 0 |
| failure HTTP (3600 sent) | 1366 / 800 / 1365 = 37.9 / 22.2 / 37.9 %, 69 requests no replica | 23.68 ms | 69 x HTTP 503 (1.92 %) |
| failure gRPC (3600 sent) | 1367 / 801 / 1367 = 38.0 / 22.2 / 38.0 %, 65 calls no replica | 20.72 ms | 65 x UNAVAILABLE (1.81 %) |
- **Prediction vs result:** weighted exactly as predicted. Round robin + delay exactly as predicted. Least request: B share fell to 12.7-13.2 % (predicted 5-11 %, a bit higher); p95 did NOT drop (predicted it might stay high): B still receives > 5 % of requests, so p95 stays at the delay; the share of slow requests fell from 33 % to 13 %. Why about 1/9-1/8: Envoy picks 2 hosts at random and B only wins when both picks are B (1/9 = 11 %) or the other pick is equally busy.
- **Failure test (health check: interval 2 s, timeout 1 s, unhealthy 2, healthy 2, no_traffic_interval 2 s; HTTP GET /health, gRPC TCP connect):** HTTP: B stopped 16:32:44.8, marked unhealthy 16:32:49.98 -> removal 5.15 s; started 16:33:10.2, healthy again 16:33:15.0 -> recovery 4.8 s. gRPC: stopped 16:34:29.1, unhealthy 16:34:33.8 -> removal 4.71 s; started 16:34:54.5, healthy 16:34:58.8 -> recovery 4.3 s. Failed checks were timeouts (flag active_hc_timeout): the stopped container does not answer, so each failed check lasts the 1 s timeout. Removal about = wait for next check (0-2 s) + 1 s timeout + 2 s + 1 s timeout = 4-6 s (predicted 2-4 s: I forgot the timeouts). Recovery = container start-up (about 1-2 s) + 2 passed checks 2 s apart = 4-5 s (predicted 4-8 s). Errors = B's share (13.3 req/s) x removal time: 13.3 x 5.15 = 69 (HTTP), 13.3 x 4.71 = 63 (+2 in flight = 65, gRPC). B kept the same IP after restart (172.19.0.3 / .10), so the slowed DNS refresh (600 s) did not matter. Client p95 (successes only) stayed 21-24 ms: failures are fast 503/UNAVAILABLE and are not in p95; they show in the error rate.
- **Measurement caveat:** in the failure runs Prometheus shows B = 832 / 818 (counter reset on restart + increase() extrapolation) while Envoy log and client both show 801 / 800. Envoy access logs are the exact figure. The errors-by-status panels of the replicas show nothing for the failure runs because the 503s are produced by Envoy, not by a replica: use the Envoy row (responses by class) for the failure screenshots.
- **Hints from the assignment:** (1) higher weight is not more capacity: weighted runs shifted load to A but latency did not improve (no replica was near its limit; the real effect would only appear when A is the bottleneck). (2) A slow replica still passes health checks: /health and the TCP check do not call the delayed operation, so B (+400 ms) stays healthy; only latency-aware policy (least request) reduced its share, and only partly.
- Run-to-run noise on this laptop: identical A-only runs gave client p95 13-39 ms on the same day; compare runs of one session only.
