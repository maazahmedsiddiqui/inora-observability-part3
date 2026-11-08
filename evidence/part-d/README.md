# Part D evidence

Generated 2026-11-08 16:36 UTC by `scripts/run_experiments.py`.

| Run | Policy | Fault | Sent | OK | Failed | Client p95 (ms) | Window (UTC) |
|---|---|---|---|---|---|---|---|
| weighted-http | weighted round robin 2:1:1 | none | 2400 | 2400 | 0 | 23.17 | 2026-11-08T16:25:25Z - 2026-11-08T16:26:25Z |
| weighted-grpc | weighted round robin 2:1:1 | none | 2400 | 2400 | 0 | 16.01 | 2026-11-08T16:26:28Z - 2026-11-08T16:27:28Z |
| delay-rr-http | round robin | B +400 ms | 2400 | 2400 | 0 | 415.72 | 2026-11-08T16:27:48Z - 2026-11-08T16:28:48Z |
| delay-rr-grpc | round robin | B +400 ms | 2400 | 2400 | 0 | 412.29 | 2026-11-08T16:28:50Z - 2026-11-08T16:29:51Z |
| delay-lr-http | least request | B +400 ms | 2400 | 2400 | 0 | 412.39 | 2026-11-08T16:30:06Z - 2026-11-08T16:31:06Z |
| delay-lr-grpc | least request | B +400 ms | 2400 | 2400 | 0 | 410.19 | 2026-11-08T16:31:08Z - 2026-11-08T16:32:08Z |
| failure-http | round robin + active health checks | B stopped at 20 s, started at 45 s | 3600 | 3531 | 69 | 23.68 | 2026-11-08T16:32:23Z - 2026-11-08T16:33:53Z |
| failure-grpc | round robin + active health checks | B stopped at 20 s, started at 45 s | 3600 | 3535 | 65 | 20.72 | 2026-11-08T16:34:08Z - 2026-11-08T16:35:38Z |

## Screenshots to take (save in `evidence/part-d/screenshots/`)

1. `weighted-http-dashboard.png` - HTTP rows (and the Envoy row for the failure runs): http://localhost:3000/d/inora-a3-load-balancing?orgId=1&from=1794155095000&to=1794155215000
2. `weighted-grpc-dashboard.png` - GRPC rows (and the Envoy row for the failure runs): http://localhost:3000/d/inora-a3-load-balancing?orgId=1&from=1794155158000&to=1794155278000
3. `delay-rr-http-dashboard.png` - HTTP rows (and the Envoy row for the failure runs): http://localhost:3000/d/inora-a3-load-balancing?orgId=1&from=1794155238000&to=1794155358000
4. `delay-rr-grpc-dashboard.png` - GRPC rows (and the Envoy row for the failure runs): http://localhost:3000/d/inora-a3-load-balancing?orgId=1&from=1794155300000&to=1794155421000
5. `delay-lr-http-dashboard.png` - HTTP rows (and the Envoy row for the failure runs): http://localhost:3000/d/inora-a3-load-balancing?orgId=1&from=1794155376000&to=1794155496000
6. `delay-lr-grpc-dashboard.png` - GRPC rows (and the Envoy row for the failure runs): http://localhost:3000/d/inora-a3-load-balancing?orgId=1&from=1794155438000&to=1794155558000
7. `failure-http-dashboard.png` - HTTP rows (and the Envoy row for the failure runs): http://localhost:3000/d/inora-a3-load-balancing?orgId=1&from=1794155513000&to=1794155663000
8. `failure-grpc-dashboard.png` - GRPC rows (and the Envoy row for the failure runs): http://localhost:3000/d/inora-a3-load-balancing?orgId=1&from=1794155618000&to=1794155768000
