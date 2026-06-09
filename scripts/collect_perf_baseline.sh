#!/usr/bin/env bash
# Parse perf_metric summary lines from app logs and write info/perf_metrics_baseline.json
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LOG="${1:-}"
OUT="${2:-$ROOT/info/perf_metrics_baseline.json}"

if [[ -z "$LOG" ]]; then
  for candidate in /var/log/waifu-bot/app.log ./logs/app.log; do
    if [[ -f "$candidate" ]]; then
      LOG="$candidate"
      break
    fi
  done
fi

if [[ -z "$LOG" || ! -f "$LOG" ]]; then
  echo "Usage: $0 <app.log> [output.json]" >&2
  echo "Or place logs at /var/log/waifu-bot/app.log or ./logs/app.log" >&2
  exit 1
fi

python3 - "$LOG" "$OUT" <<'PY'
import json
import re
import sys
from datetime import datetime, timezone

log_path, out_path = sys.argv[1], sys.argv[2]
pattern = re.compile(
    r"perf_metric summary \| (.+)$"
)
metric_re = re.compile(
    r"(?P<name>[a-zA-Z0-9_]+):n=(?P<n>\d+) p50=(?P<p50>[\d.]+)ms "
    r"p95=(?P<p95>[\d.]+)ms max=(?P<max>[\d.]+)ms"
)

samples: dict[str, dict] = {}
with open(log_path, encoding="utf-8", errors="replace") as f:
    for line in f:
        m = pattern.search(line)
        if not m:
            continue
        for part in m.group(1).split(" | "):
            mm = metric_re.match(part.strip())
            if not mm:
                continue
            d = mm.groupdict()
            name = d["name"]
            samples[name] = {
                "count": int(d["n"]),
                "p50_ms": float(d["p50"]),
                "p95_ms": float(d["p95"]),
                "max_ms": float(d["max"]),
            }

payload = {
    "collected_at": datetime.now(timezone.utc).isoformat(),
    "source_log": log_path,
    "metrics": samples,
    "notes": "Enable PERF_METRICS_ENABLED=true for 1–2 weeks; re-run this script before toggling off.",
}

with open(out_path, "w", encoding="utf-8") as out:
    json.dump(payload, out, indent=2, ensure_ascii=False)
    out.write("\n")

print(f"Wrote {out_path} ({len(samples)} metrics)")
for name, v in sorted(samples.items()):
    print(f"  {name}: p50={v['p50_ms']:.1f}ms p95={v['p95_ms']:.1f}ms n={v['count']}")
PY
