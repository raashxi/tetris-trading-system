#!/bin/bash
cd ~/trading_bot

echo "📊 Tracking EOD outcomes..."
docker exec trading_bot_main python /app/src/scripts/track_eod_outcomes.py

echo "📄 Generating daily report..."
docker exec trading_bot_main python /app/src/scripts/generate_daily_report.py

echo "💾 Backing up logs and models..."
mkdir -p ~/tetris_backups/$(date +%Y-%m-%d)
cp -r ~/trading_bot/logs ~/tetris_backups/$(date +%Y-%m-%d)/
cp -r ~/trading_bot/models ~/tetris_backups/$(date +%Y-%m-%d)/

echo "📚 Retraining EOD models..."
./scripts/retrain_eod.sh

echo "🛑 Stopping bot..."
docker-compose stop bot
docker-compose down

echo "✅ TETRIS shut down. Backup saved to ~/tetris_backups/$(date +%Y-%m-%d)/"
