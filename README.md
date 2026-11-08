# Inora - Assignment 3: Load Balancing and Observability

Enterprise Software Development, Fall 2026. Maaz Ahmed Siddiqui (HUID ms09980). Extends Assignment 2 (`inora-observability-part2`) and Assignment 1
(`inora-observability`); both are unchanged. The HTTP API, gRPC service, shared business code and observability
stack come from those assignments (reused work, see the end of this file).

Three replicas (A, B, C) of the HTTP API and of the gRPC service run behind **Envoy**. Prometheus scrapes A, B, C and
Envoy directly; Filebeat ships replica and Envoy logs to Elasticsearch/Kibana; one Grafana dashboard shows every
replica. Test traffic: `GET /products/{id}` (HTTP) and `inora.v1.CatalogService/GetProduct` (unary gRPC), both read-only.

* **Report:** `report/REPORT.pdf` (and `report/REPORT.md`)
* **Results of every run:** `evidence/summary-table.md`, screenshots and raw outputs in `evidence/`
* **Architecture and shared state:** `docs/a3/architecture.png`, `docs/a3/SHARED_STATE.md`
* **Dashboard (exported JSON):** `grafana/dashboards/inora-a3-load-balancing.json` (uid `inora-a3-load-balancing`)

## 1. Setup (Windows PowerShell; Docker Desktop and Python 3.12 installed)

```powershell
git clone https://github.com/maazahmedsiddiqui/inora-observability-part3.git
cd inora-observability-part3
python -m venv venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-grpc.txt -r requirements-dev.txt
python -m pytest -q                      # expect: 127 passed
docker compose build api                 # build one at a time on a slow connection
docker compose build grpc
docker compose up -d                     # 14 containers
Start-Sleep -Seconds 20
python scripts/envoy_stage.py round-robin    # checks the Envoy config, shows the members of both clusters
python scripts/probe_replicas.py             # quick check that A, B, C all answer
python scripts/setup_kibana.py               # once, after the first requests: Kibana data view + saved search
```

| What | Where |
|---|---|
| Envoy HTTP / gRPC (send test traffic here) | `http://localhost:10000` / `localhost:10001` |
| Envoy admin and metrics | `http://localhost:9901` |
| Prometheus (targets page) | `http://localhost:9090/targets` |
| Grafana (login admin / admin) | `http://localhost:3000/d/inora-a3-load-balancing` |
| Kibana (saved search `inora-a3-correlation`) | `http://localhost:5601/app/discover#/view/inora-a3-correlation` |

Replica names: A = container `inora-observability-part3-api-1` / `-grpc-1`, B = `-2`, C = `-3`.
Every replica puts its letter in its logs (`replica`), the `X-Replica` response header / gRPC `x-replica` metadata and
the `replica` metric label.

## 2. The fixed-rate test client

`scripts/loadgen.py` sends request *i* at `t0 + i / rate` **without waiting for earlier responses** (open loop), with
no retries. It records target rate, requests sent, successes, failures (by cause), client p50/p95/p99, the replica that
answered each request and a per-second timeline.

```powershell
python scripts/loadgen.py --interface http --rate 40 --duration 60 --name my-run --json-out runs/my-run.json
python scripts/loadgen.py --interface grpc --rate 40 --duration 60 --name my-run --json-out runs/my-run-grpc.json
python scripts/run_report.py runs/my-run.json                 # shares per replica: Prometheus vs Envoy log vs client
python scripts/run_report.py runs/my-run.json --expect A=50,B=25,C=25
```

**Rule for every measured run: stop Filebeat while the load runs, start it again afterwards** (it then ships the logs).
On a small laptop, log shipping during a run raised the gRPC client p95 from about 12 ms to 49-223 ms.

## 3. Experiments (commands)

Envoy configurations live in `envoy/stages/`; `scripts/envoy_stage.py <stage>` checks one with Envoy's own validator,
copies it to `envoy/envoy.yaml` and restarts Envoy. Stages: `a-only`, `round-robin`, `weighted-2-1-1`,
`least-request`, `health-check`. Retries are not configured anywhere and the circuit-breaker limits are set so high
they can never trigger.

**Baseline (Part B) and round robin (Part C)**
```powershell
python scripts/envoy_stage.py a-only            # or: round-robin
docker stop filebeat
python scripts/loadgen.py --interface http --rate 40 --duration 60 --name base-http --json-out runs/base-http.json
python scripts/loadgen.py --interface grpc --rate 40 --duration 60 --name base-grpc --json-out runs/base-grpc.json
docker start filebeat
python scripts/run_report.py runs/base-http.json --expect A=100,B=0,C=0     # for round-robin: no --expect
python scripts/run_report.py runs/base-grpc.json --expect A=100,B=0,C=0
python scripts/ratelimit_demo.py --count 15      # per-replica rate limit: 5 accepted on a-only, 15 on round-robin
```

**Experiment 1: weighted round robin 2:1:1**
```powershell
python scripts/envoy_stage.py weighted-2-1-1
# same two load runs as above, then:  python scripts/run_report.py <run.json> --expect A=50,B=25,C=25
```

**Experiment 2: fixed delay on B, round robin vs least request**
```powershell
python scripts/fault.py set B 0.4               # +400 ms on replica B (HTTP GET /products/<id> and gRPC GetProduct)
python scripts/envoy_stage.py round-robin       # run both loads, then:
python scripts/envoy_stage.py least-request     # run both loads again (same delay, same workload)
python scripts/fault.py clear                   # remove the delay
```

**Experiment 3: failure and recovery (active health checks)**
```powershell
python scripts/envoy_stage.py health-check
docker stop filebeat
python scripts/failure_test.py --interface http --json-out runs/fail-http.json
python scripts/failure_test.py --interface grpc --json-out runs/fail-grpc.json
docker start filebeat
```
`failure_test.py` runs 90 s at 40 req/s, stops B (`docker stop -t 1`) after 20 s, starts it after 45 s and prints how
long Envoy took to mark B unhealthy (removal) and healthy again (recovery).

| Health-check setting (stage `health-check`) | HTTP cluster | gRPC cluster |
|---|---|---|
| Check | `GET /health` | TCP connect |
| Interval / timeout | 2 s / 1 s | 2 s / 1 s |
| Unhealthy / healthy threshold | 2 failed / 2 passed checks | 2 failed / 2 passed checks |
| No-traffic interval | 2 s | 2 s |
| DNS refresh | 600 s (slowed on purpose so the health check, not DNS, removes B) | 600 s |

**Everything at once**
```powershell
python scripts/run_experiments.py all           # about 20 minutes: experiments 1-3, results in evidence/part-d/
python scripts/collect_evidence.py              # about 12 minutes: A-only and round-robin baselines into evidence/
python scripts/summary_table.py                 # summary table -> evidence/summary-table.md
```

## 4. Recovery commands (back to normal)

```powershell
python scripts/fault.py clear                                  # remove the delay on B
python scripts/envoy_stage.py round-robin                      # normal Envoy setup
docker start filebeat inora-observability-part3-api-2 inora-observability-part3-grpc-2   # anything left stopped
docker compose start envoy                                     # if Envoy itself was stopped
python scripts/envoy_stage.py health-check                     # if a restarted replica got a new address (re-resolves names)
docker compose restart grafana                                 # if the dashboard does not show up after a file change
docker compose down ; docker compose up -d                     # full restart, data kept
docker compose down -v                                         # full reset: ALSO deletes the database and log index
```
After recreating containers wait about 10 s before sending traffic (Envoy re-resolves replica names every 5 s).

## 5. Checks

```powershell
python scripts/check_idempotency_across_replicas.py   # same Idempotency-Key on B, C, A (HTTP and gRPC): one order
python scripts/check_trace_propagation.py             # traceparent reaches the replica through Envoy
python scripts/es_trace_search.py --latest http       # Envoy event + replica event for one trace id (same for grpc)
python -m pytest -q                                   # 127 tests
```

## 6. Layout

| Path | Purpose |
|---|---|
| `app.py`, `grpc_server.py`, `inora_core/`, `inora_obs/`, `proto/`, `inora/` | HTTP API, gRPC service, shared business rules, logging/trace/replica/fault helpers (from A2, extended) |
| `envoy/envoy.yaml`, `envoy/stages/` | active Envoy config and the five stage configs |
| `docker-compose.yml`, `prometheus.yml`, `filebeat.yml`, `grafana/` | stack, scrape targets, log shipping, dashboard |
| `scripts/` | load client, experiment runners, checks (see above) |
| `faults/delay.json` | per-replica delay read by the replicas (`scripts/fault.py`) |
| `evidence/` | outputs, screenshots and summary table for every run |
| `docs/a3/` | plan, report tracker, architecture, shared-state table |
| `report/` | the report (`REPORT.md`, `REPORT.pdf`) |
| `docs/README_assignment2_original.md` | the Assignment 2 README (reused work) |

## 7. Reused work, tools and limits

* **Reused:** Assignment 1 (observability stack: Prometheus, Grafana, Filebeat, Elasticsearch, Kibana) and Assignment 2
  (HTTP API, gRPC service, metrics, tests), copied as the starting point of this repository.
  New in this assignment: replicas and replica identity, Envoy configuration and stages, `GetProduct` operations,
  per-replica dashboard, load client, experiment and evidence scripts, fault injection, health endpoint.
* **Tools:** Envoy v1.39.1, Prometheus, Grafana, Filebeat/Elasticsearch/Kibana 8.12 (see `docker-compose.yml`);
  Envoy documentation on load balancers and health checking.
* **Limits:** one laptop, so latency varies from run to run (identical A-only runs gave client p95 between 13 and
  39 ms); compare runs from the same session. Optional consistent hashing was not done.
* Dependencies, virtual environment, Docker volumes and log files are not part of the repository (`.gitignore`).
