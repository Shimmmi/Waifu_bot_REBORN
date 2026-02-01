#!/usr/bin/env python3
"""Скрипт для обновления webhook после смены токена."""
import asyncio
import sys
from pathlib import Path

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from waifu_bot.services.webhook import setup_webhook


async def main():
    """Обновить webhook."""
    try:
        print("🔄 Обновление webhook...")
        await setup_webhook()
        print("✅ Webhook успешно обновлен!")
        return 0
    except Exception as e:
        print(f"❌ Ошибка при обновлении webhook: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

