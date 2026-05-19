#!/usr/bin/env python3
"""Запуск импорта шаблонов монстров в БД по ТЗ (285 монстров, тиры 1–5, все семейства и теги).

Порядок выполнения (строго):
  1. info/monster_templates_migration.sql — добавляет колонки tier, slug, has_image, image_updated_at
     в monster_templates и колонку tags в dungeons, заполняет теги данжей из location_type.
  2. info/monster_templates_import.sql — вставляет 285 записей в monster_templates.

Использование:
  Из корня репозитория (должны быть заданы POSTGRES_DSN или DATABASE_URL):
    python scripts/import_monster_templates.py
    python scripts/import_monster_templates.py --truncate   # сначала очистить monster_templates

Требуется: psql в PATH (клиент PostgreSQL).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def get_sync_dsn() -> str:
    """Возвращает sync DSN для psql (postgresql://...)."""
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_DSN")
    if not dsn:
        print("Ошибка: задайте DATABASE_URL или POSTGRES_DSN.", file=sys.stderr)
        sys.exit(1)
    # psql не понимает postgresql+asyncpg
    if "postgresql+asyncpg://" in dsn:
        dsn = dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
    return dsn


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    info = repo_root / "info"
    migration_sql = info / "monster_templates_migration.sql"
    import_sql = info / "monster_templates_import.sql"

    for p in (migration_sql, import_sql):
        if not p.exists():
            print(f"Ошибка: файл не найден: {p}", file=sys.stderr)
            return 1

    dsn = get_sync_dsn()
    truncate = "--truncate" in sys.argv or "-t" in sys.argv

    # Шаг 1: миграция (колонки + backfill тегов данжей)
    print("Шаг 1/2: выполнение monster_templates_migration.sql ...")
    r1 = subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-f", str(migration_sql)],
        cwd=str(repo_root),
    )
    if r1.returncode != 0:
        print("Миграция завершилась с ошибкой.", file=sys.stderr)
        return r1.returncode

    if truncate:
        print("Очистка monster_templates (TRUNCATE RESTART IDENTITY CASCADE) ...")
        r0 = subprocess.run(
            ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-c", "TRUNCATE monster_templates RESTART IDENTITY CASCADE;"],
            cwd=str(repo_root),
        )
        if r0.returncode != 0:
            print("TRUNCATE завершился с ошибкой.", file=sys.stderr)
            return r0.returncode

    # Шаг 2: импорт 285 монстров
    print("Шаг 2/2: выполнение monster_templates_import.sql ...")
    r2 = subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-f", str(import_sql)],
        cwd=str(repo_root),
    )
    if r2.returncode != 0:
        print("Импорт завершился с ошибкой.", file=sys.stderr)
        return r2.returncode

    print("Готово: миграция и импорт шаблонов монстров выполнены успешно.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
