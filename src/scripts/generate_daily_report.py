"""Ultimate daily PDF-ready HTML report — all metrics, charts, and tables."""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from loguru import logger

LOG_DIR = Path("/app/logs")
EOD_DIR = LOG_DIR / "eod"
REPORT_DIR = LOG_DIR / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> dict:
    try:
        if path.exists():
            with open(path) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def load_csv(path: Path) -> list:
    try:
        if path.exists():
            with open(path) as f:
                return list(csv.DictReader(f))
    except Exception:
        pass
    return []


def generate_report() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    today_display = datetime.now().strftime("%d %B %Y")

    # Load data
    accuracy_data = load_json(LOG_DIR / "eod_accuracy.json")  # list of daily summaries
    pred_log = load_csv(LOG_DIR / "eod_prediction_log.csv")    # all-time prediction log
    today_preds = load_json(EOD_DIR / "predictions.json")      # today's predictions dict or list
    trades = load_csv(LOG_DIR / "trades.csv")                  # intraday trades
    regime = load_json(LOG_DIR / "regime.json")                # market regime
    perf = load_json(LOG_DIR / "performance_log.json")         # full performance history
    alerts = load_json(LOG_DIR / "alerts.json")                # scanner alerts

    # Normalise predictions
    if isinstance(today_preds, dict):
        today_preds = list(today_preds.values())
    if isinstance(accuracy_data, dict):
        accuracy_data = [accuracy_data]  # single day case
    if isinstance(alerts, dict):
        alerts = alerts.get("alerts", [])

    # Compute core metrics
    total_preds = len(today_preds)
    # Today's accuracy from accuracy_data
    today_acc = next((d for d in accuracy_data if d.get("date") == today), None)
    correct_preds = today_acc.get("correct", 0) if today_acc else 0
    win_rate_eod = today_acc.get("win_rate", 0) if today_acc else 0
    buy_signals = today_acc.get("buy_signals", 0) if today_acc else 0
    sell_signals = today_acc.get("sell_signals", 0) if today_acc else 0

    # Trades
    today_trades = [t for t in trades if t.get("exit_time", "").startswith(today)]
    total_trades = len(today_trades)
    total_pnl = sum(float(t.get("pnl", 0)) for t in today_trades)
    winning_trades = sum(1 for t in today_trades if float(t.get("pnl", 0)) > 0)
    losing_trades = total_trades - winning_trades
    win_rate_trades = winning_trades / total_trades if total_trades > 0 else 0

    # All-time EOD accuracy
    all_time_correct = sum(d.get("correct", 0) for d in accuracy_data)
    all_time_total = sum(d.get("total", 0) for d in accuracy_data)
    all_time_wr = all_time_correct / all_time_total if all_time_total > 0 else 0

    # Per-symbol stats from pred_log
    sym_stats: Dict[str, dict] = {}
    for entry in pred_log:
        sym = entry.get("symbol", "?")
        if sym not in sym_stats:
            sym_stats[sym] = {"total": 0, "correct": 0}
        sym_stats[sym]["total"] += 1
        if entry.get("correct", "").lower() == "true":
            sym_stats[sym]["correct"] += 1

    # Top signals today
    top_signals = sorted(today_preds, key=lambda x: x.get("confidence", 0), reverse=True)[:10]

    # Charts data
    cum_pnl = 0
    pnl_series, date_series, wr_series = [], [], []
    for entry in accuracy_data:
        date_series.append(entry.get("date", ""))
        daily_correct = entry.get("correct", 0)
        daily_total = entry.get("total", 0)
        daily_wr = entry.get("win_rate", 0)
        wr_series.append(round(daily_wr * 100, 1))
        pnl = (daily_correct * 1000) - ((daily_total - daily_correct) * 1000)
        cum_pnl += pnl
        pnl_series.append(cum_pnl)

    # Build HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>TETRIS Daily Report — {today_display}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #0a0e17;
    --surface: rgba(10,16,30,0.8);
    --border: #1e2d42;
    --accent: #00d4ff;
    --green: #00e676;
    --red: #ff3d6b;
    --yellow: #ffd166;
    --text: #c8d8e8;
    --text-dim: #5a7a96;
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    padding: 32px 40px;
    font-size: 13px;
    line-height: 1.6;
  }}
  h1 {{ font-size: 24px; color: var(--accent); border-bottom: 1px solid var(--border); padding-bottom: 12px; margin-bottom: 8px; }}
  h2 {{ font-size: 16px; color: var(--text); margin-top: 32px; margin-bottom: 12px; border-left: 3px solid var(--accent); padding-left: 10px; }}
  .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 16px 0; }}
  .metric {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 14px 16px;
    text-align: center;
  }}
  .metric-value {{ font-size: 26px; font-weight: 700; font-family: 'Courier New', monospace; }}
  .metric-label {{ font-size: 10px; text-transform: uppercase; letter-spacing: 2px; color: var(--text-dim); margin-top: 4px; }}
  .green {{ color: var(--green); }}
  .red {{ color: var(--red); }}
  .accent {{ color: var(--accent); }}
  .yellow {{ color: var(--yellow); }}
  table {{ width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 12px; }}
  th {{ text-align: left; padding: 10px 12px; background: rgba(0,212,255,0.06); color: var(--text-dim); font-size: 10px; text-transform: uppercase; letter-spacing: 1px; border-bottom: 1px solid var(--border); }}
  td {{ padding: 8px 12px; border-bottom: 1px solid rgba(255,255,255,0.04); font-family: 'Courier New', monospace; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 2px; font-size: 10px; font-weight: 700; }}
  .badge-buy {{ background: rgba(0,230,118,0.15); color: var(--green); }}
  .badge-sell {{ background: rgba(255,61,107,0.15); color: var(--red); }}
  .badge-hold {{ background: rgba(255,209,102,0.15); color: var(--yellow); }}
  .footer {{ margin-top: 32px; padding-top: 12px; border-top: 1px solid var(--border); font-size: 10px; color: var(--text-dim); text-align: center; }}
  .chart-box {{ background: var(--surface); border: 1px solid var(--border); border-radius: 4px; padding: 16px; margin: 12px 0; }}
  canvas {{ max-height: 250px; }}
  .section-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  @media print {{ body {{ -webkit-print-color-adjust: exact; }} }}
</style>
</head>
<body>

<h1>TETRIS - Daily Trading Report</h1>
<p style="color: var(--text-dim); margin-bottom:20px;">{today_display} · Generated {datetime.now().strftime('%H:%M IST')} · PAPER MODE</p>

<!-- 1. EXECUTIVE SUMMARY -->
<h2>📊 Executive Summary</h2>
<div class="metrics">
  <div class="metric">
    <div class="metric-value accent">{total_preds}</div>
    <div class="metric-label">EOD Predictions</div>
  </div>
  <div class="metric">
    <div class="metric-value green">{correct_preds}</div>
    <div class="metric-label">Correct Today</div>
  </div>
  <div class="metric">
    <div class="metric-value {'green' if win_rate_eod >= 0.50 else 'red'}">{win_rate_eod:.1%}</div>
    <div class="metric-label">EOD Win Rate</div>
  </div>
  <div class="metric">
    <div class="metric-value accent">{all_time_wr:.1%}</div>
    <div class="metric-label">All-Time EOD Win Rate</div>
  </div>
</div>

<!-- 2. INTRADAY TRADING SUMMARY -->
<h2>📈 Intraday Trading</h2>
<div class="metrics">
  <div class="metric">
    <div class="metric-value accent">{total_trades}</div>
    <div class="metric-label">Trades Today</div>
  </div>
  <div class="metric">
    <div class="metric-value green">{winning_trades}</div>
    <div class="metric-label">Winning Trades</div>
  </div>
  <div class="metric">
    <div class="metric-value {'green' if total_pnl >= 0 else 'red'}">₹{total_pnl:+,.0f}</div>
    <div class="metric-label">Net P&L</div>
  </div>
  <div class="metric">
    <div class="metric-value {'green' if win_rate_trades >= 0.50 else 'red'}">{win_rate_trades:.1%}</div>
    <div class="metric-label">Trade Win Rate</div>
  </div>
</div>
"""

    # Trade table
    if today_trades:
        html += """<h2>💼 Today's Trades</h2>
<table>
<tr><th>Time</th><th>Symbol</th><th>Side</th><th>Entry</th><th>Exit</th><th>Qty</th><th>P&L</th><th>Reason</th></tr>"""
        for t in today_trades[:20]:
            side = t.get("side", "")
            badge = "badge-buy" if side == "BUY" else "badge-sell"
            pnl_val = float(t.get("pnl", 0))
            html += f"""<tr>
  <td>{t.get('exit_time','')[-8:]}</td>
  <td>{t.get('symbol','')}</td>
  <td><span class="badge {badge}">{side}</span></td>
  <td>₹{t.get('entry_price','')}</td>
  <td>₹{t.get('exit_price','')}</td>
  <td>{t.get('qty','')}</td>
  <td class="{'green' if pnl_val >= 0 else 'red'}">₹{pnl_val:+,.0f}</td>
  <td style="font-size:10px;">{t.get('reason','')}</td>
</tr>"""
        html += "</table>"

    # 3. EOD SIGNALS
    html += f"""<h2>🔮 Top EOD Signals Today</h2>
<table>
<tr><th>Symbol</th><th>Direction</th><th>Confidence</th><th>Win Rate</th><th>Last Close</th></tr>"""
    for s in top_signals:
        direction = s.get("direction", "HOLD")
        badge = f"badge-{direction.lower()}" if direction in ("BUY","SELL") else "badge-hold"
        html += f"""<tr>
  <td>{s.get('symbol','?')}</td>
  <td><span class="badge {badge}">{direction}</span></td>
  <td>{s.get('confidence',0):.0%}</td>
  <td>{s.get('win_rate',0):.0%}</td>
  <td>₹{s.get('last_close',0):.2f}</td>
</tr>"""
    html += "</table>"

    # 4. PER-SYMBOL PERFORMANCE
    html += """<h2>🏆 Per-Symbol EOD Accuracy (All-Time)</h2>
<table>
<tr><th>Symbol</th><th>Predictions</th><th>Correct</th><th>Win Rate</th></tr>"""
    sorted_syms = sorted(sym_stats.items(), key=lambda x: x[1]["correct"]/max(x[1]["total"],1), reverse=True)[:15]
    for sym, st in sorted_syms:
        wr = st["correct"] / max(st["total"], 1)
        html += f"""<tr>
  <td>{sym}</td>
  <td>{st['total']}</td>
  <td>{st['correct']}</td>
  <td class="{'green' if wr >= 0.50 else 'red'}">{wr:.1%}</td>
</tr>"""
    html += "</table>"

    # 5. CHARTS
    html += """<h2>📉 Performance Trends</h2>"""
    if len(date_series) > 1:
        html += f"""<div class="chart-box">
  <canvas id="cumPnlChart"></canvas>
</div>
<div class="section-grid">
  <div class="chart-box">
    <canvas id="winRateChart"></canvas>
  </div>
  <div class="chart-box">
    <canvas id="dailyTradesChart"></canvas>
  </div>
</div>"""

    # 6. REGIME
    if regime:
        html += f"""<h2>🌍 Market Regime</h2>
<div class="metrics">
  <div class="metric"><div class="metric-value accent">{regime.get('trend','?')}</div><div class="metric-label">Trend</div></div>
  <div class="metric"><div class="metric-value accent">{regime.get('vol','?')}</div><div class="metric-label">Volatility</div></div>
  <div class="metric"><div class="metric-value accent">{regime.get('breadth','?')}</div><div class="metric-label">Breadth</div></div>
  <div class="metric"><div class="metric-value accent">{regime.get('liquidity','?')}</div><div class="metric-label">Liquidity</div></div>
</div>"""

    # 7. ALERTS
    if alerts:
        html += f"""<h2>🚨 Scanner Alerts ({len(alerts)} total)</h2>
<table>
<tr><th>Tier</th><th>Symbol</th><th>Message</th><th>Score</th></tr>"""
        for a in sorted(alerts, key=lambda x: x.get("score",0), reverse=True)[:10]:
            html += f"""<tr>
  <td><span class="badge badge-{'buy' if a.get('tier')==1 else 'badge-hold' if a.get('tier')==2 else 'badge-sell'}">T{a.get('tier','?')}</span></td>
  <td>{a.get('symbol','?')}</td>
  <td style="font-size:10px;">{a.get('message','')}</td>
  <td>{a.get('score',0)}</td>
</tr>"""
        html += "</table>"

    html += f"""
<div class="footer">
TETRIS Trading System · Paper Mode · All times IST · Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}
</div>"""

    # Inject Chart.js data if we have history
    if len(date_series) > 1:
        html += f"""
<script>
const dates = {json.dumps(date_series)};
const pnlData = {json.dumps(pnl_series)};
const wrData = {json.dumps(wr_series)};
new Chart(document.getElementById('cumPnlChart'), {{
  type: 'line',
  data: {{ labels: dates, datasets: [{{ label: 'Cumulative P&L (₹)', data: pnlData, borderColor: '#00d4ff', backgroundColor: 'rgba(0,212,255,0.1)', fill: true, tension: 0.3, pointRadius: 0 }}] }},
  options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ ticks: {{ maxTicksLimit: 8, color: '#5a7a96' }} }}, y: {{ ticks: {{ color: '#5a7a96' }} }} }} }}
}});
new Chart(document.getElementById('winRateChart'), {{
  type: 'line',
  data: {{ labels: dates, datasets: [{{ label: 'Win Rate %', data: wrData, borderColor: '#00e676', tension: 0.3, pointRadius: 0 }}] }},
  options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ ticks: {{ maxTicksLimit: 5, color: '#5a7a96' }} }}, y: {{ min: 30, max: 80, ticks: {{ color: '#5a7a96' }} }} }} }}
}});
new Chart(document.getElementById('dailyTradesChart'), {{
  type: 'bar',
  data: {{ labels: dates, datasets: [{{ label: 'Trades', data: {json.dumps([len(today_trades)]*len(date_series))}, backgroundColor: 'rgba(0,212,255,0.4)' }}] }},
  options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ ticks: {{ maxTicksLimit: 5, color: '#5a7a96' }} }}, y: {{ ticks: {{ color: '#5a7a96' }} }} }} }}
}});
</script>
"""

    html += "</body></html>"

    # Save report
    report_path = REPORT_DIR / f"report_{today}.html"
    report_path.write_text(html)
    logger.info(f"Ultimate report saved: {report_path}")
    return str(report_path)


if __name__ == "__main__":
    path = generate_report()
    print(f"Report: {path}")