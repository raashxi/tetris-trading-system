#!/bin/bash
echo "╔══════════════════════════════════════╗"
echo "║   ⚡ TETRIS — Morning Startup        ║"
echo "║   $(date '+%Y-%m-%d %H:%M:%S IST')   ║"
echo "╚══════════════════════════════════════╝"

cd ~/trading_bot

if ! docker ps 2>/dev/null | grep -q trading_bot_main; then
    echo "Starting containers..."
    docker-compose up -d --no-build
    sleep 15
else
    echo "Containers already running"
fi

docker exec -u root trading_bot_main ln -sf /usr/share/zoneinfo/Asia/Kolkata /etc/localtime 2>/dev/null

# Check if token is already valid
echo "Checking Kite session..."
TOKEN_VALID=$(docker exec trading_bot_main python3 -c "
from src.auth.session import KiteSessionManager
mgr = KiteSessionManager()
token = mgr._get_stored_token()
print('VALID' if token and mgr._is_token_valid(token) else 'EXPIRED')
" 2>/dev/null)

if [ "$TOKEN_VALID" = "VALID" ]; then
    echo "✅ Kite session valid — skipping login"
else
    echo "🔐 Login required"
    docker exec -it trading_bot_main python /app/refresh_token.py
fi

echo "📊 Computing sentiment proxy..."
docker exec trading_bot_main python -c "
import sys; sys.path.insert(0, '/app')
from src.data.options_fetcher import compute_sentiment_from_quotes
compute_sentiment_from_quotes()
"

echo "Running EOD predictions..."
docker exec trading_bot_main python /app/src/scripts/run_eod_predictions.py

echo "Restarting bot..."
docker-compose restart bot

echo "TETRIS is live. Dashboard: http://localhost:8502"
