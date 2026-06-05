#!/bin/bash
echo "📚 Starting daily retraining at $(date)"
cd "$(dirname "$0")/.."
docker-compose run --rm bot python -c "
from src.models.trainer import retrain_all_models
retrain_all_models()
"
echo "✅ Retraining completed at $(date)"
