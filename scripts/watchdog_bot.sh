#!/usr/bin/env bash
# ==============================================================================
# Dave's Domain Monitor - Watchdog y Auto-reinicio del Bot de Telegram
# ==============================================================================
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

if ! pgrep -f "domain_monitor telegram-bot" > /dev/null 2>&1; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️ Bot caído detectado. Reiniciando proceso..." >> "$DIR/data/watchdog.log"
    nohup /usr/bin/python3 -m domain_monitor telegram-bot >> "$DIR/data/bot.log" 2>&1 &
fi
