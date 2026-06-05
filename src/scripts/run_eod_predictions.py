"""Run EOD predictions and save results for the dashboard."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from datetime import datetime
from loguru import logger
from src.models.daily_predictor import run_daily_predictions, get_morning_brief
from src.scanner.watchlist import build_watchlist
from src.scanner.patterns import scan_patterns
from src.auth.session import get_kite_session

OUTPUT_DIR = Path("/app/logs/eod")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def main():
    kite = get_kite_session()
    if not kite:
        logger.error("No Kite session – EOD predictions aborted")
        return

    # 1. Predictions
    preds = run_daily_predictions(max_symbols=50)
    with open(OUTPUT_DIR / "predictions.json", "w") as f:
        json.dump(preds, f, indent=2)

    # 2. Watchlist
    watchlist = build_watchlist(kite, max_stocks=100)
    symbols = list(watchlist.keys())
    with open(OUTPUT_DIR / "watchlist.json", "w") as f:
        json.dump(watchlist, f, indent=2)

    # 3. Patterns
    patterns = scan_patterns(kite, symbols[:75])
    with open(OUTPUT_DIR / "patterns.json", "w") as f:
        json.dump(patterns, f, indent=2)

    # 4. Morning brief (Telegram)
    brief = get_morning_brief()
    logger.info(brief)

    logger.info("EOD predictions saved to logs/eod/")

if __name__ == "__main__":
    main()