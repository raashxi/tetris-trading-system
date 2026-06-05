#!/bin/bash
echo "📚 EOD Model Retraining — $(date '+%Y-%m-%d %H:%M:%S')"
cd ~/trading_bot
docker exec trading_bot_main python -c "
import sys
sys.path.insert(0, '/app')
from src.models.daily_trainer import train_all_eod
results = train_all_eod(max_symbols=50)
passed = sum(1 for v in results.values() if v)
print(f'EOD Retraining: {passed}/50 models passed')
"
echo "✅ EOD retraining complete — $(date '+%Y-%m-%d %H:%M:%S')"
