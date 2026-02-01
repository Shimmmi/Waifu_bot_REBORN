#!/bin/bash
# Скрипт для анализа логов бота на подозрительную активность
# Использование: bash scripts/analyze_logs.sh

echo "🔍 Анализ логов бота на подозрительную активность"
echo "=================================================="
echo ""

# Цвета
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

DAYS=7
SINCE="${DAYS} days ago"

echo "📅 Период анализа: последние $DAYS дней"
echo ""

# 1. Проверка на неудачные попытки авторизации (401)
echo "1️⃣  Неудачные попытки авторизации (401 Unauthorized):"
echo "---------------------------------------------------"
UNAUTHORIZED=$(journalctl --since "$SINCE" 2>/dev/null | grep "401 Unauthorized" | grep -v sshd | wc -l)
if [ "$UNAUTHORIZED" -gt 0 ]; then
    echo -e "${RED}⚠️  Найдено $UNAUTHORIZED попыток неавторизованного доступа${NC}"
    echo ""
    echo "Топ IP адресов с 401 ошибками:"
    journalctl --since "$SINCE" 2>/dev/null | grep "401 Unauthorized" | grep -v sshd | \
        awk '{print $6}' | sort | uniq -c | sort -rn | head -5 | \
        while read count ip; do
            echo "  $count попыток от $ip"
        done
    echo ""
    echo "Последние попытки:"
    journalctl --since "$SINCE" 2>/dev/null | grep "401 Unauthorized" | grep -v sshd | tail -5 | \
        awk '{print $1, $2, $3, $6, $NF}' | sed 's/^/  /'
else
    echo -e "${GREEN}✅ Неудачных попыток авторизации не найдено${NC}"
fi
echo ""

# 2. Проверка на запрещенные запросы (403)
echo "2️⃣  Запрещенные запросы (403 Forbidden):"
echo "---------------------------------------------------"
FORBIDDEN=$(journalctl --since "$SINCE" 2>/dev/null | grep "403 Forbidden" | grep -v sshd | wc -l)
if [ "$FORBIDDEN" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Найдено $FORBIDDEN запрещенных запросов${NC}"
    journalctl --since "$SINCE" 2>/dev/null | grep "403 Forbidden" | grep -v sshd | tail -5 | \
        awk '{print $1, $2, $3, $6, $NF}' | sed 's/^/  /'
else
    echo -e "${GREEN}✅ Запрещенных запросов не найдено${NC}"
fi
echo ""

# 3. Проверка на невалидные HTTP запросы
echo "3️⃣  Невалидные HTTP запросы:"
echo "---------------------------------------------------"
INVALID=$(journalctl --since "$SINCE" 2>/dev/null | grep -i "Invalid HTTP request" | wc -l)
if [ "$INVALID" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Найдено $INVALID невалидных HTTP запросов${NC}"
    journalctl --since "$SINCE" 2>/dev/null | grep -i "Invalid HTTP request" | tail -5 | \
        sed 's/^/  /'
else
    echo -e "${GREEN}✅ Невалидных HTTP запросов не найдено${NC}"
fi
echo ""

# 4. Проверка на подозрительные эндпоинты (сканирование)
echo "4️⃣  Подозрительные эндпоинты (попытки сканирования):"
echo "---------------------------------------------------"
SUSPICIOUS_ENDPOINTS=$(journalctl --since "$SINCE" 2>/dev/null | \
    grep -E "(404 Not Found|/admin|/www\.tar|/backup|/\.env|/config|/api/action)" | \
    grep -v sshd | wc -l)

if [ "$SUSPICIOUS_ENDPOINTS" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Найдено $SUSPICIOUS_ENDPOINTS подозрительных запросов${NC}"
    echo ""
    echo "Топ подозрительных путей:"
    journalctl --since "$SINCE" 2>/dev/null | \
        grep -E "(404 Not Found|/admin|/www\.tar|/backup|/\.env|/config)" | \
        grep -v sshd | \
        grep -oE '"[A-Z]+ [^"]+"' | sort | uniq -c | sort -rn | head -10 | \
        sed 's/^/  /'
    echo ""
    echo "Топ IP адресов с подозрительными запросами:"
    journalctl --since "$SINCE" 2>/dev/null | \
        grep -E "(404 Not Found|/admin|/www\.tar|/backup|/\.env|/config)" | \
        grep -v sshd | \
        awk '{print $6}' | sort | uniq -c | sort -rn | head -5 | \
        while read count ip; do
            echo "  $count запросов от $ip"
        done
else
    echo -e "${GREEN}✅ Подозрительных эндпоинтов не найдено${NC}"
fi
echo ""

# 5. Проверка webhook запросов
echo "5️⃣  Webhook запросы:"
echo "---------------------------------------------------"
WEBHOOK_REQUESTS=$(journalctl --since "$SINCE" 2>/dev/null | grep "/api/webhook" | wc -l)
if [ "$WEBHOOK_REQUESTS" -gt 0 ]; then
    echo -e "${GREEN}✅ Найдено $WEBHOOK_REQUESTS webhook запросов${NC}"
    echo ""
    echo "Последние webhook запросы:"
    journalctl --since "$SINCE" 2>/dev/null | grep "/api/webhook" | tail -5 | \
        awk '{print $1, $2, $3, $6, $7}' | sed 's/^/  /'
else
    echo -e "${YELLOW}ℹ️  Webhook запросы не найдены${NC}"
fi
echo ""

# 6. Проверка на ошибки обработки обновлений
echo "6️⃣  Ошибки обработки обновлений:"
echo "---------------------------------------------------"
UPDATE_ERRORS=$(journalctl --since "$SINCE" 2>/dev/null | grep -iE "(Failed to parse update|Failed to process update|webhook.*error)" | wc -l)
if [ "$UPDATE_ERRORS" -gt 0 ]; then
    echo -e "${RED}⚠️  Найдено $UPDATE_ERRORS ошибок обработки${NC}"
    journalctl --since "$SINCE" 2>/dev/null | \
        grep -iE "(Failed to parse update|Failed to process update|webhook.*error)" | \
        tail -5 | sed 's/^/  /'
else
    echo -e "${GREEN}✅ Ошибок обработки обновлений не найдено${NC}"
fi
echo ""

# 7. Итоговая статистика
echo "=================================================="
echo "📊 ИТОГОВАЯ СТАТИСТИКА"
echo "=================================================="
echo ""

TOTAL_REQUESTS=$(journalctl --since "$SINCE" 2>/dev/null | grep -E "(GET|POST|PUT|DELETE|HEAD)" | grep -v sshd | wc -l)
echo "Всего HTTP запросов: $TOTAL_REQUESTS"

SUCCESS_REQUESTS=$(journalctl --since "$SINCE" 2>/dev/null | grep "200 OK" | wc -l)
echo "Успешных запросов (200): $SUCCESS_REQUESTS"

NOT_FOUND_REQUESTS=$(journalctl --since "$SINCE" 2>/dev/null | grep "404 Not Found" | wc -l)
echo "Запросов не найдено (404): $NOT_FOUND_REQUESTS"

echo ""
echo "Топ 10 IP адресов по количеству запросов:"
journalctl --since "$SINCE" 2>/dev/null | \
    grep -E "(GET|POST|PUT|DELETE|HEAD)" | \
    grep -v sshd | \
    awk '{print $6}' | sort | uniq -c | sort -rn | head -10 | \
    while read count ip; do
        echo "  $count запросов от $ip"
    done

echo ""
echo "=================================================="
echo "💡 РЕКОМЕНДАЦИИ"
echo "=================================================="

if [ "$UNAUTHORIZED" -gt 10 ]; then
    echo -e "${RED}⚠️  КРИТИЧНО: Много неудачных попыток авторизации!${NC}"
    echo "  - Проверьте, не была ли утечка токена"
    echo "  - Убедитесь, что токен был изменен"
    echo "  - Рассмотрите возможность блокировки подозрительных IP"
fi

if [ "$SUSPICIOUS_ENDPOINTS" -gt 50 ]; then
    echo -e "${YELLOW}⚠️  Обнаружено активное сканирование сервера${NC}"
    echo "  - Это нормально для публичных серверов"
    echo "  - Рекомендуется настроить fail2ban или подобную защиту"
    echo "  - Убедитесь, что все чувствительные эндпоинты защищены"
fi

echo ""
echo -e "${GREEN}✅ Анализ завершен${NC}"

