
# WAIFU BOT REBORN
# IMPLEMENTATION BLUEPRINT
## Enterprise Migration Plan from Modular Monolith to Scalable Service Platform

Version: 1.0

---

# 1. OBJECTIVES

## Business Goals

- Support 50,000+ DAU
- Support 10,000+ concurrent WebApp users
- Support high-volume Telegram group activity
- Reduce response latency
- Isolate failures
- Enable independent scaling

## Technical Goals

- Event-driven architecture
- Horizontal scalability
- Dedicated worker platform
- Service isolation
- Observability-first approach
- Zero-downtime deployments

---

# 2. CURRENT STATE

Current architecture:

Telegram
→ Aiogram
→ FastAPI
→ Services
→ PostgreSQL
→ Redis

Problems:

- Single process handles everything
- LLM calls block gameplay workflows
- Background jobs run inside application process
- Tight coupling between domains
- Direct service-to-service calls
- PostgreSQL is becoming central bottleneck

---

# 3. TARGET ARCHITECTURE

Telegram
│
Bot Service
│
Event Bus
│
├── Combat Service
├── Guild Service
├── Expedition Service
├── Rewards Service
├── Notification Service
├── LLM Service
│
PostgreSQL Cluster
│
DragonflyDB

---

# 4. TARGET REPOSITORY STRUCTURE

repository/

services/
    api-service/
    bot-service/
    combat-service/
    guild-service/
    expedition-service/
    rewards-service/
    notification-service/
    llm-service/

shared/
    contracts/
    events/
    schemas/
    auth/
    telemetry/

infra/
    docker/
    k8s/
    terraform/

monitoring/
    grafana/
    prometheus/
    loki/

docs/

---

# 5. DOMAIN DECOMPOSITION

## API Service

Responsibilities:

- Telegram WebApp
- Armory
- Public APIs
- Authentication

No game calculations.

---

## Bot Service

Responsibilities:

- Telegram updates
- Commands
- Callbacks

Publishes events only.

---

## Combat Service

Responsibilities:

- Dungeon combat
- Raid combat
- Abyss combat
- Damage calculations

Owns:

combat_* tables

---

## Guild Service

Responsibilities:

- Guild management
- Guild raids
- Guild wars
- Guild progression

Owns:

guild_* tables

---

## Expedition Service

Responsibilities:

- Expedition lifecycle
- Expedition rewards
- Expedition ticks

Owns:

expedition_* tables

---

## Rewards Service

Responsibilities:

- Chat rewards
- Daily rewards
- Reward distribution

---

## Notification Service

Responsibilities:

- Telegram DMs
- Push notifications
- Mail

---

## LLM Service

Responsibilities:

- Narratives
- Portrait generation
- Event generation

---

# 6. EVENT BUS DESIGN

Stage 1:

Redis Streams

Stage 2:

RabbitMQ

Optional Future:

Kafka

---

## Event Envelope

{
  "event_id": "uuid",
  "event_type": "PlayerMessageEvent",
  "version": 1,
  "timestamp": "...",
  "payload": {}
}

---

## Core Events

PlayerMessageEvent

DungeonAttackEvent

DungeonCompletedEvent

GuildRaidAttackEvent

GuildWarStartedEvent

PlayerRewardGrantedEvent

ExpeditionStartedEvent

ExpeditionCompletedEvent

NarrativeRequestedEvent

NarrativeGeneratedEvent

---

# 7. DATABASE STRATEGY

## Phase A

Single PostgreSQL

PgBouncer

---

## Phase B

Primary
Replica

---

## Phase C

Dedicated schemas

combat
guild
expedition
rewards

---

## Phase D

Possible future:

Citus

---

# 8. REDIS / DRAGONFLY STRATEGY

Current Redis Keys

spam:*

gd_v1_buf:*

chat_reward:*

sse:*

armory:*

---

Migration Plan

1. Deploy Dragonfly
2. Replicate traffic
3. Verify metrics
4. Switch traffic
5. Remove Redis

---

# 9. OBSERVABILITY

## Metrics

Prometheus

Metrics:

http_requests_total

telegram_updates_total

combat_duration_ms

guild_duration_ms

llm_duration_ms

redis_latency_ms

postgres_latency_ms

---

## Logging

JSON logs

Fields:

request_id

player_id

chat_id

event_id

service_name

---

## Tracing

OpenTelemetry

Trace Flow:

Telegram Update
→ Bot
→ Event Bus
→ Combat
→ PostgreSQL

---

# 10. API CONTRACTS

## Combat API

POST /combat/attack

Request:

{
  "player_id": 123,
  "message_type": "text"
}

Response:

{
  "damage": 250,
  "critical": false
}

---

## Guild API

POST /guild/raid/attack

---

## Expedition API

POST /expedition/start

POST /expedition/claim

---

## LLM API

POST /narrative/generate

POST /portrait/generate

---

# 11. WORKER PLATFORM

Technology:

Dramatiq

Broker:

Redis Streams

---

Queues

combat

guild

expedition

notifications

llm

---

Workers

combat-worker

guild-worker

expedition-worker

notification-worker

llm-worker

---

# 12. MIGRATION ROADMAP

## Sprint 1

Observability

Deliverables:

- Prometheus
- Grafana
- Structured Logging
- OpenTelemetry

Success Criteria:

Full visibility

---

## Sprint 2

Database Hardening

Deliverables:

- PgBouncer
- Index Audit
- Slow Query Analysis

Success Criteria:

P95 SQL reduced

---

## Sprint 3

Worker Platform

Deliverables:

- Dramatiq
- Queue Infrastructure

Success Criteria:

No asyncio loops

---

## Sprint 4

LLM Service

Deliverables:

- Dedicated service
- Queue integration

Success Criteria:

No direct OpenRouter calls from gameplay

---

## Sprint 5

Event Bus

Deliverables:

- Event contracts
- Redis Streams

Success Criteria:

Gameplay events routed through bus

---

## Sprint 6

Combat Service Extraction

Deliverables:

- New service
- API contracts

Success Criteria:

Combat separated from monolith

---

## Sprint 7

Guild Service Extraction

Deliverables:

- Guild service

---

## Sprint 8

Expedition Service Extraction

Deliverables:

- Expedition service

---

## Sprint 9

CQRS Layer

Deliverables:

- Read Models
- Materialized Views

---

## Sprint 10

Read Replica

Deliverables:

- PostgreSQL replica

---

## Sprint 11

Dragonfly Migration

Deliverables:

- Redis replacement

---

## Sprint 12

Kubernetes

Deliverables:

- Production cluster

---

# 13. ZERO-DOWNTIME STRATEGY

Pattern:

Strangler Fig

For every extraction:

1. Introduce abstraction
2. Dual execution
3. Shadow traffic
4. Validation
5. Traffic switch
6. Legacy removal

---

# 14. RISK MANAGEMENT

Combat Extraction

Risk: High

Mitigation:

Shadow mode

---

Guild Extraction

Risk: Medium

Mitigation:

Dual writes

---

Database Split

Risk: High

Mitigation:

Read-only validation stage

---

# 15. KUBERNETES TARGET

Namespaces

production

staging

monitoring

---

Deployments

api

bot

combat

guild

expedition

llm

notifications

---

StatefulSets

postgres

dragonfly

---

Autoscaling

CPU

Memory

Queue Depth

---

# 16. CI/CD

GitHub Actions

Pipeline

1. Lint
2. Unit Tests
3. Integration Tests
4. Security Scan
5. Build Image
6. Push Registry
7. Deploy Staging
8. Smoke Tests
9. Deploy Production

---

# 17. DEFINITION OF SUCCESS

P95 API < 200ms

P95 Telegram Update < 500ms

99.9% Availability

Independent Service Scaling

No Gameplay Loss

No Blocking LLM Operations

50x Capacity Growth Compared To Current Architecture
