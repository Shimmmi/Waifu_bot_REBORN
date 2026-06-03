# Kubernetes (Stage 1 PR7 — skeleton only)

**No production cutover.** Use after [Docker Compose](../docs/DOCKER.md) is stable.

## Layout

```
k8s/
  README.md           (this file)
  base/
    kustomization.yaml
    api-deployment.yaml
    worker-deployment.yaml
    llm-worker-deployment.yaml
    scheduler-deployment.yaml
    services.yaml
  overlays/
    staging/kustomization.yaml
    prod/kustomization.yaml
```

## Prerequisites

- Postgres and Redis **outside** the cluster (managed or VPS) for v1 — same as Blueprint Phase 13
- PgBouncer DSN in Secret
- `BACKGROUND_MODE=worker` on API Deployment

## Apply (staging example)

```bash
kubectl apply -k k8s/overlays/staging
```

## Triggers to adopt K8s

See [STAGE2_GATE.md](../docs/STAGE2_GATE.md): multi-node, HPA, rolling deploy without downtime.

## Systemd alternative

For single VPS, prefer [infra/systemd/](../infra/systemd/) over K8s.
