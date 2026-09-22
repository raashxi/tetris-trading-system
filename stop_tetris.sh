#!/bin/bash
cd ~/trading_bot

LOG_DIR="logs/cron"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/stop_$(date +%Y-%m-%d).log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S IST')] $1" | tee -a "$LOG"; }

log "══════════════════════════════════════"
log "  TETRIS — Evening Shutdown"
log "══════════════════════════════════════"

# 1. Verify market is closed
HOUR=$(date +%H)
if [ "$HOUR" -lt 15 ]; then
    log "Market still open (before 3:30 PM). Aborting shutdown."
    exit 1
fi

# 2. Track EOD outcomes
if [ -f "src/scripts/track_eod_outcomes.py" ]; then
    log "Tracking EOD outcomes..."
    docker exec trading_bot_main python /app/src/scripts/track_eod_outcomes.py 2>&1 | tee -a "$LOG" || log "Outcome tracking failed (non-fatal)."
fi

# 3. Generate daily report
if [ -f "src/scripts/generate_daily_report.py" ]; then
    log "Generating daily report..."
    docker exec trading_bot_main python /app/src/scripts/generate_daily_report.py 2>&1 | tee -a "$LOG" || log "Report generation failed (non-fatal)."
fi

# 4. Backup logs and models
BACKUP_DIR="$HOME/tetris_backups/$(date +%Y-%m-%d)"
log "Backing up to $BACKUP_DIR..."
mkdir -p "$BACKUP_DIR"
cp -r logs "$BACKUP_DIR/" 2>/dev/null || true
cp -r models "$BACKUP_DIR/" 2>/dev/null || true

# 5. Retrain EOD models (daily)
if [ -f "scripts/daily_retrain.sh" ]; then
    log "Running daily EOD retrain..."
    bash scripts/daily_retrain.sh 2>&1 | tee -a "$LOG" || log "Retrain failed (non-fatal)."
else
    log "Retraining EOD models..."
    docker exec trading_bot_main python -c "
from src.models.daily_trainer import train_all_eod
results = train_all_eod(max_symbols=100)
print('Passed:', sum(1 for v in results.values() if v))
print('Failed:', sum(1 for v in results.values() if not v))
" 2>&1 | tee -a "$LOG" || log "Retrain failed (non-fatal)."
fi

# 6. Stop bot, keep dashboard/api/redis running overnight? No — stop everything.
log "Stopping bot container..."
docker-compose stop bot

log "══════════════════════════════════════"
log "  Shutdown complete"
log "══════════════════════════════════════"
