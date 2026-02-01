#!/bin/bash
# Скрипт для проверки истории git на наличие токенов и секретов
# Использование: bash scripts/check_git_history.sh

set -e

echo "🔍 Проверка истории git на наличие токенов и секретов..."
echo "------------------------------------------------------------"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

FOUND_ISSUES=0

# Проверка на токены Telegram ботов (формат: 8+ цифр:35+ символов)
echo "Проверка на токены Telegram ботов..."
BOT_TOKENS=$(git log --all --full-history -p --source --all 2>/dev/null | \
    grep -oE '[0-9]{8,}:[A-Za-z0-9_-]{35,}' | sort -u)

if [ -n "$BOT_TOKENS" ]; then
    echo -e "${RED}⚠️  Найдены потенциальные токены ботов в истории:${NC}"
    echo "$BOT_TOKENS" | while read -r token; do
        # Проверяем, не является ли это примером
        if echo "$token" | grep -qiE "your_|example|placeholder"; then
            continue
        fi
        echo -e "${RED}  $token${NC}"
        FOUND_ISSUES=$((FOUND_ISSUES + 1))
    done
fi

# Проверка на хардкод BOT_TOKEN
echo ""
echo "Проверка на хардкод BOT_TOKEN..."
BOT_TOKEN_MATCHES=$(git log --all --full-history -p --source --all 2>/dev/null | \
    grep -iE 'BOT_TOKEN\s*[=:]\s*["\''][0-9]{8,}:' | grep -vE 'your_|example|placeholder' | sort -u)

if [ -n "$BOT_TOKEN_MATCHES" ]; then
    echo -e "${RED}⚠️  Найден хардкод BOT_TOKEN в истории:${NC}"
    echo "$BOT_TOKEN_MATCHES" | head -5
    FOUND_ISSUES=$((FOUND_ISSUES + 1))
fi

# Проверка на пароли в DSN
echo ""
echo "Проверка на пароли в строках подключения..."
PASSWORD_MATCHES=$(git log --all --full-history -p --source --all 2>/dev/null | \
    grep -iE 'postgres.*://[^:]+:[^@]+@|redis://[^:]+:[^@]+@' | \
    grep -vE 'user:pass|example|placeholder|your_' | sort -u)

if [ -n "$PASSWORD_MATCHES" ]; then
    echo -e "${YELLOW}⚠️  Найдены строки подключения с паролями в истории:${NC}"
    echo "$PASSWORD_MATCHES" | head -5 | sed 's/:[^:@]*@/:***@/g'  # Маскируем пароли
    FOUND_ISSUES=$((FOUND_ISSUES + 1))
fi

echo ""
echo "------------------------------------------------------------"

if [ $FOUND_ISSUES -eq 0 ]; then
    echo -e "${GREEN}✅ В истории git не найдено явных токенов или секретов.${NC}"
    echo "   Однако, если вы подозреваете утечку:"
    echo "   1. Используйте git-filter-repo для очистки истории"
    echo "   2. Или создайте новый репозиторий без истории"
    exit 0
else
    echo -e "${RED}❌ Обнаружены проблемы в истории git!${NC}"
    echo "   Рекомендуется:"
    echo "   1. Немедленно смените все токены/пароли"
    echo "   2. Очистите историю git (git-filter-repo или новый репозиторий)"
    exit 1
fi

