#!/usr/bin/env python3
"""
Скрипт для проверки логов и базы данных на подозрительную активность.
Использование: python3 scripts/check_suspicious_activity.py
"""
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from sqlalchemy import select, func
    from waifu_bot.db.session import init_engine, SessionLocal
    from waifu_bot.db.models.player import Player
    from waifu_bot.core.config import settings
    DB_AVAILABLE = True
except Exception as e:
    print(f"⚠️  База данных недоступна: {e}")
    DB_AVAILABLE = False


def check_system_logs():
    """Проверка системных логов."""
    print("=" * 60)
    print("📋 Проверка системных логов")
    print("=" * 60)
    
    import subprocess
    
    checks = [
        ("journalctl (последние 24 часа)", 
         ["journalctl", "--since", "24 hours ago", "--no-pager", "-n", "100"]),
    ]
    
    found_issues = []
    
    for name, cmd in checks:
        try:
            result = subprocess.run(
                cmd + ["|", "grep", "-iE", "(telegram|bot|waifu|webhook|error|fail)"],
                capture_output=True,
                text=True,
                shell=True,
                timeout=5
            )
            if result.stdout.strip():
                print(f"\n🔍 {name}:")
                lines = result.stdout.strip().split('\n')[-20:]  # Последние 20 строк
                for line in lines:
                    if any(keyword in line.lower() for keyword in ['error', 'fail', 'unauthorized', '403', '401']):
                        found_issues.append(f"{name}: {line}")
                        print(f"  ⚠️  {line[:100]}")
        except Exception as e:
            print(f"  ⚠️  Не удалось проверить {name}: {e}")
    
    return found_issues


async def check_database_activity():
    """Проверка активности в базе данных."""
    if not DB_AVAILABLE:
        return []
    
    print("\n" + "=" * 60)
    print("📊 Проверка базы данных")
    print("=" * 60)
    
    found_issues = []
    
    try:
        init_engine()
        async with SessionLocal() as session:
            # Проверяем количество пользователей
            result = await session.execute(select(func.count(Player.id)))
            total_players = result.scalar()
            print(f"\n📈 Всего пользователей: {total_players}")
            
            # Проверяем недавно созданных пользователей
            week_ago = datetime.utcnow() - timedelta(days=7)
            result = await session.execute(
                select(func.count(Player.id))
                .where(Player.created_at >= week_ago)
            )
            recent_players = result.scalar()
            print(f"📈 Новых пользователей за неделю: {recent_players}")
            
            if recent_players > 1000:
                found_issues.append(f"Подозрительно много новых пользователей: {recent_players}")
                print(f"  ⚠️  Подозрительно много новых пользователей за неделю!")
            
            # Проверяем пользователей с подозрительными ID (слишком маленькие или слишком большие)
            # Telegram user IDs обычно начинаются с 5-6 цифр и выше
            result = await session.execute(
                select(Player)
                .where(Player.id < 100000)
                .order_by(Player.id.desc())
                .limit(10)
            )
            suspicious_ids = result.scalars().all()
            
            if suspicious_ids:
                print(f"\n⚠️  Найдены пользователи с подозрительными ID (< 100000):")
                for player in suspicious_ids[:5]:
                    print(f"  - ID: {player.id}, создан: {player.created_at}")
            
    except Exception as e:
        print(f"  ⚠️  Ошибка при проверке БД: {e}")
    
    return found_issues


def check_webhook_logs():
    """Проверка логов webhook (если есть файловые логи)."""
    print("\n" + "=" * 60)
    print("🔗 Проверка webhook логов")
    print("=" * 60)
    
    # Ищем файлы логов
    log_paths = [
        Path("/var/log/waifu-bot"),
        Path("/opt/waifu-bot-REBORN/logs"),
        Path.home() / ".waifu-bot" / "logs",
    ]
    
    found_issues = []
    
    for log_dir in log_paths:
        if log_dir.exists():
            print(f"\n📁 Найдена директория логов: {log_dir}")
            log_files = list(log_dir.glob("*.log"))
            for log_file in log_files[:5]:  # Проверяем первые 5 файлов
                try:
                    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                        # Ищем подозрительные паттерны в последних 100 строках
                        for line in lines[-100:]:
                            if any(keyword in line.lower() for keyword in [
                                '401', '403', 'unauthorized', 'forbidden',
                                'invalid secret', 'webhook secret', 'token'
                            ]):
                                found_issues.append(f"{log_file.name}: {line.strip()[:100]}")
                                print(f"  ⚠️  {line.strip()[:100]}")
                except Exception as e:
                    print(f"  ⚠️  Не удалось прочитать {log_file}: {e}")
        else:
            print(f"  ℹ️  Директория {log_dir} не найдена")
    
    if not any(p.exists() for p in log_paths):
        print("  ℹ️  Файловые логи не найдены. Логи выводятся только в консоль.")
        print("  💡 Рекомендуется настроить файловое логирование для безопасности.")
    
    return found_issues


def check_configuration():
    """Проверка конфигурации на возможные проблемы безопасности."""
    print("\n" + "=" * 60)
    print("⚙️  Проверка конфигурации")
    print("=" * 60)
    
    found_issues = []
    
    try:
        # Проверяем настройки
        print(f"\n📋 Текущие настройки:")
        print(f"  - Environment: {settings.environment}")
        print(f"  - Public URL: {settings.public_base_url}")
        print(f"  - Admin IDs: {settings.admin_ids}")
        
        # Проверяем, есть ли админы
        if not settings.admin_ids:
            found_issues.append("Не настроены ADMIN_IDS - нет админов бота")
            print("  ⚠️  Не настроены ADMIN_IDS!")
        
        # Проверяем URL на безопасность
        if "localhost" in str(settings.public_base_url) and settings.environment == "prod":
            found_issues.append("Public URL указывает на localhost в production")
            print("  ⚠️  Public URL указывает на localhost в production!")
        
    except Exception as e:
        print(f"  ⚠️  Ошибка при проверке конфигурации: {e}")
    
    return found_issues


async def main():
    """Основная функция."""
    print("🔍 Проверка бота на подозрительную активность")
    print("=" * 60)
    
    all_issues = []
    
    # Проверка системных логов
    all_issues.extend(check_system_logs())
    
    # Проверка базы данных
    if DB_AVAILABLE:
        all_issues.extend(await check_database_activity())
    
    # Проверка webhook логов
    all_issues.extend(check_webhook_logs())
    
    # Проверка конфигурации
    all_issues.extend(check_configuration())
    
    # Итоговый отчет
    print("\n" + "=" * 60)
    print("📊 ИТОГОВЫЙ ОТЧЕТ")
    print("=" * 60)
    
    if all_issues:
        print(f"\n⚠️  Найдено {len(all_issues)} потенциальных проблем:")
        for i, issue in enumerate(all_issues, 1):
            print(f"  {i}. {issue}")
        print("\n💡 Рекомендации:")
        print("  1. Проверьте логи приложения за последние дни")
        print("  2. Убедитесь, что токен был изменен")
        print("  3. Проверьте активность в Telegram через @BotFather")
        print("  4. Рассмотрите возможность настроить файловое логирование")
        return 1
    else:
        print("\n✅ Подозрительная активность не обнаружена.")
        print("\n💡 Рекомендации:")
        print("  1. Убедитесь, что токен был изменен через @BotFather")
        print("  2. Проверьте логи приложения (если они сохраняются)")
        print("  3. Настройте файловое логирование для будущих проверок")
        return 0


if __name__ == '__main__':
    if DB_AVAILABLE:
        exit_code = asyncio.run(main())
    else:
        exit_code = main()
    sys.exit(exit_code)

