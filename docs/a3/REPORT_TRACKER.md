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

## 5. Baselines
- [ ] Part B baseline HTTP (A only) · [ ] Part B baseline gRPC (A only)
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
