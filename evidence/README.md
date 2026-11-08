# Evidence (Assignment 3, Parts A-C)

Generated 2026-11-08 15:40 UTC by `scripts/collect_evidence.py`. Workload: 40 requests/s for 60 s, open loop, no retries, Filebeat stopped during each run.

## Results

| Stage | Interface | Sent | OK | Failed | Client p95 (ms) | Window (UTC) |
|---|---|---|---|---|---|---|
| a-only | http | 2400 | 2400 | 0 | 38.94 | 2026-11-08T15:34:50Z - 2026-11-08T15:35:50Z |
| a-only | grpc | 2400 | 2400 | 0 | 32.4 | 2026-11-08T15:35:54Z - 2026-11-08T15:36:55Z |
| round-robin | http | 2400 | 2400 | 0 | 31.49 | 2026-11-08T15:37:47Z - 2026-11-08T15:38:47Z |
| round-robin | grpc | 2400 | 2400 | 0 | 31.38 | 2026-11-08T15:38:52Z - 2026-11-08T15:39:52Z |

Share tables: `<stage>/<iface>-shares.txt`. Trace searches: `<stage>/<iface>-trace-search.txt`. Rate limit: `<stage>/ratelimit-demo.txt`. Envoy members: `<stage>/cluster-members.txt`.

## Screenshots to take (save in `evidence/screenshots/`, exact file names)

Open each Grafana link, wait for the panels to load, scroll so the whole HTTP or gRPC section is visible, take the screenshot.

1. `a-only-http-dashboard.png` - a-only, HTTP rows: http://localhost:3000/d/inora-a3-load-balancing?orgId=1&from=1794152060000&to=1794152180000
2. `a-only-grpc-dashboard.png` - a-only, GRPC rows: http://localhost:3000/d/inora-a3-load-balancing?orgId=1&from=1794152124000&to=1794152245000
3. `round-robin-http-dashboard.png` - round-robin, HTTP rows: http://localhost:3000/d/inora-a3-load-balancing?orgId=1&from=1794152237000&to=1794152357000
4. `round-robin-grpc-dashboard.png` - round-robin, GRPC rows: http://localhost:3000/d/inora-a3-load-balancing?orgId=1&from=1794152302000&to=1794152422000
5. `envoy-panels.png` - Envoy row (members, responses, in-flight), round-robin: http://localhost:3000/d/inora-a3-load-balancing?orgId=1&from=1794152302000&to=1794152422000
6. `prometheus-targets.png` - http://localhost:9090/targets (all UP)
7. `kibana-http-correlation.png` - saved search http://localhost:5601/app/discover#/view/inora-a3-correlation , time range last 1 hour, query `trace_id : "5deb2dffac99be7aa712c13f7d9002c8"` (2 rows)
8. `kibana-grpc-correlation.png` - same page, query `trace_id : "312b100f218d843ace4e1931da9fc501"` (2 rows)
