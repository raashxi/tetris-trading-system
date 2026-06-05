#!/bin/bash
echo "🚨 EMERGENCY SQUARE-OFF INITIATED 🚨"
echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"

cd "$(dirname "$0")/.."

# Create STOP file
touch STOP
echo "✅ STOP file created"

# Stop the bot
docker stop trading_bot_main 2>/dev/null || true

echo ""
echo "⚠️  MANUAL ACTION REQUIRED ⚠️"
echo "1. Log into Kite and close all positions manually"
echo "2. Check your positions at: https://kite.zerodha.com/positions"
echo ""
echo "The STOP file prevents the bot from restarting."
echo "Remove STOP file when ready to resume: rm STOP"
