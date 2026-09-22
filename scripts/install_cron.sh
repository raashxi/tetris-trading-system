#!/bin/bash
# Installs TETRIS daily cron jobs for evening retraining.
# Run once: bash scripts/install_cron.sh

CRON_LINES="
# TETRIS — Evening retrain + shutdown (weekdays, 4:00 PM IST)
0 16 * * 1-5 cd \$HOME/trading_bot && ./stop_tetris.sh >> \$HOME/trading_bot/logs/cron/cron.log 2>&1
"

# Remove any previous TETRIS cron entries
crontab -l 2>/dev/null | grep -v "TETRIS" | grep -v "stop_tetris.sh" | grep -v "start_tetris.sh" > /tmp/cron_clean

# Install new cron
( cat /tmp/cron_clean; echo "$CRON_LINES" ) | crontab -

# Show result
echo "Cron installed. Current schedule:"
crontab -l
