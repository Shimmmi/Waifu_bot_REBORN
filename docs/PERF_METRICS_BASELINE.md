# Baseline P95: PERF_METRICS

Stage 1 requires 1–2 weeks of in-process latency samples before worker/microservice decisions.

## Enable

```env
PERF_METRICS_ENABLED=true
```

Restart API. Every ~60s logs emit:

```
perf_metric summary | group_message_damage_ms:n=... p50=...ms p95=...ms max=...ms | llm_post_chat_completions_ms:...
```

## Collect baseline

```bash
# After 1–2 weeks of production traffic
./scripts/collect_perf_baseline.sh /var/log/waifu-bot/app.log
# → info/perf_metrics_baseline.json
```

## Worker gate

```bash
./scripts/check_worker_gate.sh
# Exit 1 + recommendation if p95 exceeds thresholds (see STAGE1_WORKERS_DECISION.md)
```

## Disable

After baseline is saved to `info/perf_metrics_baseline.json`, set `PERF_METRICS_ENABLED=false` to reduce log volume.
