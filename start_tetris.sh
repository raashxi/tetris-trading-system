#!/bin/bash
set -e
cd ~/trading_bot

LOG_DIR="logs/cron"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/start_$(date +%Y-%m-%d).log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S IST')] $1" | tee -a "$LOG"; }

log "══════════════════════════════════════"
log "  TETRIS — Morning Startup"
log "══════════════════════════════════════"

# 1. Kill switch check
if [ -f "STOP" ]; then
    log "STOP file found. Aborting startup."
    exit 1
fi

# 2. Docker must be running
if ! docker ps > /dev/null 2>&1; then
    log "Docker is not running. Attempting to start Docker Desktop..."
    open -a Docker
    sleep 30
    if ! docker ps > /dev/null 2>&1; then
        log "Docker failed to start. Aborting."
        exit 1
    fi
fi
log "Docker is running."

# 3. Start containers
log "Starting containers..."
docker-compose up -d --no-build
sleep 15

# 4. Fix timezone
docker exec -u root trading_bot_main ln -sf /usr/share/zoneinfo/Asia/Kolkata /etc/localtime 2>/dev/null || true
log "Timezone set to IST."

# 5. Check Kite token (semi-auto)
TOKEN_VALID=$(docker exec trading_bot_main python3 -c "
from src.auth.session import KiteSessionManager
m = KiteSessionManager()
t = m._get_stored_token()
print('VALID' if t and m._is_token_valid(t) else 'EXPIRED')
" 2>/dev/null || echo "EXPIRED")

if [ "$TOKEN_VALID" = "VALID" ]; then
    log "Kite token valid. Skipping login."
else
    log "Kite token expired. Starting interactive login..."
    docker exec -it trading_bot_main python /app/refresh_token.py
    log "Login complete."
fi

# 6. Run EOD predictions
log "Running EOD predictions..."
docker exec trading_bot_main python /app/src/scripts/run_eod_predictions.py 2>&1 | tee -a "$LOG"

# 7. Restart bot with fresh state
log "Restarting bot..."
docker-compose restart bot
sleep 5

log "══════════════════════════════════════"
log "  TETRIS is LIVE"
log "  Dashboard: http://localhost:8502"
log "  Monitor:   ./watch_tetris.sh"
log "══════════════════════════════════════"
