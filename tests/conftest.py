"""Pytest: минимальные env для импорта waifu_bot без .env."""
from __future__ import annotations

import os

_TEST_ENV = {
    "BOT_TOKEN": "test-bot-token",
    "WEBHOOK_SECRET": "test-webhook-secret",
    "PUBLIC_BASE_URL": "https://test.example",
    "POSTGRES_DSN": "postgresql+asyncpg://user:pass@localhost:5432/waifu_test",
    "REDIS_URL": "redis://localhost:6379/0",
}

for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)
