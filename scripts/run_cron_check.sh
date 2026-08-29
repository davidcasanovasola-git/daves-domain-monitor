#!/usr/bin/env bash
# ==============================================================================
# Dave's Domain Monitor - Script de Escaneo Automático para Cron
# ==============================================================================
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] Iniciando escaneo periódico Dave's Domain Monitor ===" >> "$DIR/data/cron_check.log"
/usr/bin/python3 -m domain_monitor check >> "$DIR/data/cron_check.log" 2>&1
