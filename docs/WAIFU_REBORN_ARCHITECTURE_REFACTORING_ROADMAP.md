
# WAIFU BOT REBORN
# Architecture Refactoring Roadmap (Enterprise Edition)

Version: 1.0
Target Horizon: 6–18 months
Audience:
- Technical Lead
- Backend Developers
- DevOps Engineers
- Solution Architects
- AI/LLM Engineers

---

# Executive Summary

Текущая система представляет собой модульный монолит:

- FastAPI
- Aiogram
- PostgreSQL
- Redis
- Background asyncio loops
- Telegram WebApp
- Armory SPA
- LLM integrations

Основная проблема заключается не в выборе технологий, а в высокой связанности компонентов и выполнении критичных операций внутри одного процесса.

Целевая архитектура должна обеспечивать:

- 50 000+ DAU
- десятки тысяч сообщений в час
- горизонтальное масштабирование
- независимое масштабирование сервисов
- отказоустойчивость
- безопасную интеграцию LLM

---

# Phase 0 — Discovery & Baseline

Duration: 1 week

## Deliverables

### Architecture Inventory

Создать:

docs/architecture/

Содержимое:

- Context Diagram
- Container Diagram
- Component Diagram
- Data Flow Diagram
- Sequence Diagrams

---

### Runtime Profiling

Инструменты:

- PySpy
- Scalene
- OpenTelemetry

Метрики:

- P50
- P95
- P99

Для:

- group_message_damage
- process_message_damage
- expedition_tick
- gd_v1_round

---

### Database Audit

Собрать:

- Top SQL
- Deadlocks
- Locks
- Missing indexes

---

### Redis Audit

Собрать:

- Memory usage
- Key growth
- PubSub load

---

# Phase 1 — Observability First

Duration: 1–2 weeks

## Goal

Нельзя масштабировать систему без наблюдаемости.

---

## Logging

Внедрить:

- Structured Logging
- JSON logs

Инструменты:

- structlog
- loguru

---

## Metrics

Prometheus

Метрики:

- HTTP requests
- Telegram updates
- Redis latency
- SQL latency
- LLM latency

---

## Tracing

OpenTelemetry

Трассировка:

Telegram Update
→ API
→ Service
→ DB
→ Redis
→ LLM

---

## Dashboards

Grafana

Отдельные дашборды:

- Combat
- Guild
- LLM
- PostgreSQL
- Redis

---

# Phase 2 — Infrastructure Hardening

Duration: 1 week

## PostgreSQL

Внедрить:

PgBouncer

pool_mode=transaction

---

## Backups

Автоматизировать:

- Daily backup
- WAL archive

---

## Redis

Включить:

Persistence

AOF + RDB

---

## Nginx

Добавить:

- rate limits
- gzip
- brotli
- cache headers

---

# Phase 3 — Background Worker Platform

Duration: 2 weeks

## Problem

Сейчас задачи работают внутри FastAPI процесса.

---

## New Architecture

API

Bot

Workers

---

## Recommended Stack

Dramatiq

Redis Broker

---

## Worker Groups

### Gameplay Workers

- GD
- Expedition
- Abyss

### Notification Workers

- Telegram DM
- Mail

### AI Workers

- Narratives
- Portraits

---

## Migration Strategy

Шаг 1

Дублирование выполнения.

Шаг 2

Shadow Mode.

Шаг 3

Отключение asyncio loop.

---

# Phase 4 — LLM Platform Extraction

Duration: 2 weeks

## Goal

Изолировать AI.

---

## New Service

llm-service

---

Responsibilities

- narratives
- guild wars
- expeditions
- portraits

---

## API

POST /narrative/gd
POST /narrative/war
POST /expedition/event

---

## Cache Layer

Redis

24h TTL

---

## Circuit Breaker

При отказе:

Fallback Templates

---

# Phase 5 — Event Driven Foundation

Duration: 3 weeks

## Current

Direct Calls

---

## Future

Event Bus

---

## Technology

Redis Streams

Stage 1

RabbitMQ

Stage 2

Kafka

Optional

---

## Events

PlayerMessageEvent

DungeonAttackEvent

GuildRaidAttackEvent

PlayerRewardEvent

PlayerLevelUpEvent

ExpeditionFinishedEvent

---

## Event Contract

Каждое событие:

- event_id
- timestamp
- player_id
- payload
- version

---

# Phase 6 — Combat Service Extraction

Duration: 3–4 weeks

## Goal

Вынести главный hot path.

---

## New Service

combat-service

---

Responsibilities

- damage calculation
- spam control
- combat logs
- drops

---

## API

POST /combat/attack

POST /combat/simulate

---

## Database

Собственная схема:

combat_*

---

## Scaling

Horizontal

N replicas

---

# Phase 7 — Guild Domain Extraction

Duration: 2–3 weeks

## New Service

guild-service

---

Responsibilities

- guilds
- raids
- wars
- contributions

---

## Events

GuildWarStarted

GuildRaidStarted

GuildLevelUp

---

# Phase 8 — Read Model Layer

Duration: 2 weeks

## Problem

Armory выполняет тяжёлые запросы.

---

## Solution

CQRS

---

Write Side

Gameplay DB

---

Read Side

Materialized Views

Replica

---

## Armory Reads

Только через:

read-api

---

# Phase 9 — Data Platform

Duration: 2 weeks

## PostgreSQL Replica

Primary

Replica

---

## Routing

Writes

Primary

Reads

Replica

---

## Future

Citus

Optional

---

# Phase 10 — Redis Replacement

Duration: 1 week

## Replace

Redis

→

DragonflyDB

---

Expected Gains

2x–5x

---

Migration

Blue/Green

---

# Phase 11 — API Gateway

Duration: 1 week

## Introduce

Gateway

---

Candidates

Traefik

Kong

NGINX

---

Responsibilities

- auth
- routing
- rate limits
- observability

---

# Phase 12 — Container Platform

Duration: 2 weeks

## Dockerization

Services

- api
- bot
- workers
- llm
- gateway

---

## CI/CD

GitHub Actions

Stages

- Test
- Build
- Scan
- Deploy

---

# Phase 13 — Kubernetes

Duration: 3 weeks

## Namespace Layout

production

staging

monitoring

---

## Deployments

api

bot

workers

llm

---

## StatefulSets

postgres

dragonfly

---

## HPA

Metrics

- CPU
- Memory
- Queue Depth

---

# Phase 14 — Multi Region Strategy

Optional

Trigger:

50k+ DAU

---

Regions

EU

US

APAC

---

Architecture

Global Gateway

Regional Services

Shared Event Backbone

---

# Repository Refactoring Plan

Current

src/waifu_bot/

Future

services/

api-service/

bot-service/

combat-service/

guild-service/

llm-service/

shared/

contracts/

events/

libs/

infra/

terraform/

k8s/

monitoring/

---

# Risk Register

## High Risk

Combat extraction

Mitigation:

Shadow execution

---

## Medium Risk

Event Bus migration

Mitigation:

Dual write

---

## Medium Risk

Read Replica lag

Mitigation:

Read-after-write routing

---

# Success Metrics

P95 API < 200 ms

P95 Telegram update < 500 ms

LLM latency isolated

99.9% uptime

Zero gameplay loss

Horizontal scaling supported

---

# Recommended Implementation Order

1. Observability
2. PgBouncer
3. Workers
4. LLM Service
5. Event Bus
6. Combat Service
7. Guild Service
8. CQRS
9. Replica
10. Dragonfly
11. Gateway
12. Kubernetes

Expected capacity increase:

Current Architecture:
1x

After Phase 6:
5x–10x

After Phase 10:
10x–20x

After Kubernetes:
20x–50x
