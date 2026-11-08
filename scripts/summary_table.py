"""summary_table.py - build the one-table summary of all runs (Part D) as Markdown: evidence/summary-table.md

  python scripts/summary_table.py

Reads the Part B/C runs in evidence/a-only and evidence/round-robin and every run in evidence/part-d/runs.json.
The Explanation column comes from docs/a3/explanations.json ({"<run id>": "text"}) when it exists.
"""
import json
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def load(path):
    p = os.path.join(ROOT, path)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def main():
    runs = []
    for stage, pol in (("a-only", "all traffic to A"), ("round-robin", "round robin A,B,C")):
        for i in ("http", "grpc"):
            runs.append({"id": f"{stage}-{i}", "interface": i, "policy": pol, "fault": "none",
                         "run_json": f"evidence/{stage}/{i}-run.json"})
    runs += load("evidence/part-d/runs.json") or []
    expl = load("docs/a3/explanations.json") or {}
    L = ["| Run / interface | Policy and fault | Target / actual rps | A / B / C shares (Envoy log) | Client p95 | Error rate | Explanation |",
         "|---|---|---|---|---|---|---|"]
    for e in runs:
        r = load(e["run_json"])
        if not r:
            continue
        rep = load(e["run_json"].replace(".json", ".report.json")) or load(os.path.join(os.path.dirname(e["run_json"]), "run.report.json")) or {}
        rows = rep.get("rows", {})
        sh = " / ".join(f"{rows[k]['envoy_log_pct']:.1f}" for k in "ABC") + " %" if rows else "n/a"
        fault = e["fault"] if e["fault"] != "none" else "no fault"
        L.append(f"| {e['id']} ({e['interface']}) | {e['policy']}; {fault} | {r['target_rps']:g} / {r['actual_send_rps']} | {sh} | "
                 f"{r['p95_ms']} ms | {r['error_rate_pct']} % | {expl.get(e['id'], '')} |")
    out = os.path.join(ROOT, "evidence", "summary-table.md")
    open(out, "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
    print("\n".join(L))
    print("\nwritten", out)


if __name__ == "__main__":
    main()
