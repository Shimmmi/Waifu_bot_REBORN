#!/usr/bin/env bash
# Recommend BACKGROUND_MODE=worker when Stage 1 worker gate criteria are met (STAGE1_WORKERS_DECISION.md).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BASELINE="${1:-$ROOT/info/perf_metrics_baseline.json}"
HANDLER_P95_LIMIT="${HANDLER_P95_LIMIT:-500}"
LLM_P95_LIMIT="${LLM_P95_LIMIT:-10000}"

if [[ ! -f "$BASELINE" ]]; then
  echo "No baseline at $BASELINE — run scripts/collect_perf_baseline.sh after PERF_METRICS_ENABLED=true"
  exit 0
fi

python3 - "$BASELINE" "$HANDLER_P95_LIMIT" "$LLM_P95_LIMIT" <<'PY'
import json
import sys

path, handler_limit, llm_limit = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
with open(path, encoding="utf-8") as f:
    data = json.load(f)
metrics = data.get("metrics") or {}

triggers = []
handler = metrics.get("group_message_damage_ms")
if handler and handler.get("p95_ms", 0) > handler_limit:
    triggers.append(
        f"group_message_damage_ms p95={handler['p95_ms']:.1f}ms > {handler_limit}ms"
    )

llm = metrics.get("llm_post_chat_completions_ms")
if llm and llm.get("p95_ms", 0) > llm_limit:
    triggers.append(
        f"llm_post_chat_completions_ms p95={llm['p95_ms']:.1f}ms > {llm_limit}ms"
    )

if triggers:
    print("WORKER_GATE: CONSIDER enabling BACKGROUND_MODE=worker + LLM worker")
    print("See docs/STAGE1_WORKERS_DECISION.md")
    for t in triggers:
        print(f"  - {t}")
    print("")
    print("Suggested .env:")
    print("  BACKGROUND_MODE=worker")
    print("  LLM_WORKER_ENABLED=true")
    sys.exit(1)

print("WORKER_GATE: OK — inline mode acceptable per baseline metrics")
PY
