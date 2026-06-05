"""
╔══════════════════════════════════════════════════════════════╗
║         QUANT TERMINAL — Production Trading Dashboard        ║
║         Multi-tab · Live P&L · EOD · Regime · Scanner        ║
╚══════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import pandas as pd
import numpy as np
import json
import pickle
import os
from datetime import datetime, timedelta
from pathlib import Path as P
import random  # used only for demo sparklines — remove in production

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Quant Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:ital,wght@0,400;0,700;1,400&family=Syne:wght@400;600;700;800&display=swap');

/* ── Root variables ── */
:root {
    --bg:          #080c14;
    --bg2:         #0d1420;
    --bg3:         #111926;
    --border:      #1e2d42;
    --border2:     #243448;
    --text:        #c8d8e8;
    --text-dim:    #5a7a96;
    --accent:      #00d4ff;
    --accent2:     #0088bb;
    --green:       #00e676;
    --green-dim:   #003d20;
    --red:         #ff3d6b;
    --red-dim:     #3d0018;
    --yellow:      #ffd600;
    --yellow-dim:  #3d3000;
    --purple:      #b967ff;
    --orange:      #ff6b35;
    --mono:        'Space Mono', monospace;
    --sans:        'Syne', sans-serif;
}

/* ── Base overrides ── */
html, body, [class*="css"] {
    background-color: var(--bg) !important;
    color: var(--text) !important;
    font-family: var(--mono) !important;
}

.stApp { background: var(--bg) !important; }

/* Scanline overlay */
.stApp::before {
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: repeating-linear-gradient(
        0deg,
        transparent,
        transparent 2px,
        rgba(0,212,255,0.012) 2px,
        rgba(0,212,255,0.012) 4px
    );
    pointer-events: none;
    z-index: 9999;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: var(--bg2) !important;
    border-right: 1px solid var(--border) !important;
}
section[data-testid="stSidebar"] * { font-family: var(--mono) !important; }

/* ── Metrics ── */
[data-testid="metric-container"] {
    background: var(--bg2) !important;
    border: 1px solid var(--border) !important;
    border-radius: 4px !important;
    padding: 12px 16px !important;
    position: relative;
    overflow: hidden;
}
[data-testid="metric-container"]::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--accent), transparent);
}
[data-testid="metric-container"] label {
    color: var(--text-dim) !important;
    font-size: 10px !important;
    letter-spacing: 2px !important;
    text-transform: uppercase !important;
    font-family: var(--mono) !important;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    color: var(--accent) !important;
    font-size: 22px !important;
    font-weight: 700 !important;
    font-family: var(--mono) !important;
}
[data-testid="metric-container"] [data-testid="stMetricDelta"] {
    font-size: 11px !important;
    font-family: var(--mono) !important;
}

/* ── Dataframe ── */
[data-testid="stDataFrame"] {
    border: 1px solid var(--border) !important;
    border-radius: 4px !important;
}
.dvn-scroller { background: var(--bg2) !important; }

/* ── Tabs ── */
[data-testid="stTabs"] [role="tab"] {
    background: transparent !important;
    color: var(--text-dim) !important;
    border: none !important;
    font-family: var(--mono) !important;
    font-size: 11px !important;
    letter-spacing: 1px !important;
    text-transform: uppercase !important;
    padding: 8px 20px !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: var(--accent) !important;
    border-bottom: 2px solid var(--accent) !important;
    background: transparent !important;
}
[data-testid="stTabs"] [role="tablist"] {
    border-bottom: 1px solid var(--border) !important;
    gap: 0 !important;
}

/* ── Dividers ── */
hr { border-color: var(--border) !important; }

/* ── Radio buttons (sidebar nav) ── */
[role="radiogroup"] label {
    font-family: var(--mono) !important;
    font-size: 11px !important;
    letter-spacing: 1px !important;
    color: var(--text-dim) !important;
}
[role="radiogroup"] [aria-checked="true"] + span {
    color: var(--accent) !important;
}

/* ── Info / warning boxes ── */
.stInfo { background: rgba(0,212,255,0.06) !important; border-color: var(--accent2) !important; }
.stWarning { background: rgba(255,214,0,0.06) !important; border-color: var(--yellow) !important; }
.stSuccess { background: rgba(0,230,118,0.06) !important; border-color: var(--green) !important; }
.stError { background: rgba(255,61,107,0.06) !important; border-color: var(--red) !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 2px; }

/* ── Captions ── */
small, .stCaption { color: var(--text-dim) !important; font-size: 10px !important; }
</style>
""", unsafe_allow_html=True)

# ── Helpers ────────────────────────────────────────────────────────────────────
def load_json(path_str: str) -> dict:
    path = P(path_str)
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}

def load_model_meta(pkl_path) -> dict:
    try:
        with open(pkl_path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return {}

def sparkline_html(values: list[float], color: str = "#00d4ff", height: int = 32) -> str:
    """Render a tiny inline SVG sparkline."""
    if not values or len(values) < 2:
        return ""
    mn, mx = min(values), max(values)
    rng = mx - mn or 1
    w, h = 80, height
    pts = " ".join(
        f"{i * w / (len(values)-1):.1f},{h - (v - mn) / rng * h:.1f}"
        for i, v in enumerate(values)
    )
    return (
        f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg">'
        f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.5"/>'
        f'</svg>'
    )

def signal_badge(sig: str) -> str:
    MAP = {
        "BUY":  ('<span style="background:#003d20;color:#00e676;padding:2px 10px;'
                 'border:1px solid #00e676;border-radius:2px;font-size:11px;'
                 'letter-spacing:1px;font-family:var(--mono)">▲ BUY</span>'),
        "SELL": ('<span style="background:#3d0018;color:#ff3d6b;padding:2px 10px;'
                 'border:1px solid #ff3d6b;border-radius:2px;font-size:11px;'
                 'letter-spacing:1px;font-family:var(--mono)">▼ SELL</span>'),
        "HOLD": ('<span style="background:#1a1a00;color:#ffd600;padding:2px 10px;'
                 'border:1px solid #ffd600;border-radius:2px;font-size:11px;'
                 'letter-spacing:1px;font-family:var(--mono)">◆ HOLD</span>'),
    }
    return MAP.get(sig.upper(), sig)

def regime_badge(regime: str) -> str:
    MAP = {
        "BULL":     "🟢", "BEAR": "🔴",
        "SIDEWAYS": "🟡", "CHOP": "🟠",
    }
    return f"{MAP.get(regime, '⚪')} {regime}"

def pnl_color(val: float) -> str:
    return "color:#00e676" if val >= 0 else "color:#ff3d6b"

def tier_badge(tier: str) -> str:
    MAP = {
        "HIGH CONVICTION": '<span style="color:#00e676;font-size:10px">◉ HIGH</span>',
        "MODERATE":        '<span style="color:#ffd600;font-size:10px">◎ MOD</span>',
        "SPECULATIVE":     '<span style="color:#ff6b35;font-size:10px">○ SPEC</span>',
        "AUTO-REJECT":     '<span style="color:#ff3d6b;font-size:10px">✕ REJECT</span>',
    }
    return MAP.get(tier.upper(), tier)

def section_header(title: str, subtitle: str = "") -> None:
    st.markdown(
        f"""<div style="margin:24px 0 12px;padding-bottom:8px;
        border-bottom:1px solid #1e2d42">
        <span style="font-family:'Syne',sans-serif;font-size:16px;
        font-weight:700;color:#c8d8e8;letter-spacing:1px">{title}</span>
        {"<span style='color:#5a7a96;font-size:11px;margin-left:12px'>" + subtitle + "</span>" if subtitle else ""}
        </div>""",
        unsafe_allow_html=True,
    )

def kv_pill(label: str, value: str, color: str = "#00d4ff") -> str:
    return (
        f'<span style="background:#0d1420;border:1px solid {color}33;'
        f'border-radius:2px;padding:3px 10px;margin:2px;display:inline-block;'
        f'font-size:11px;font-family:var(--mono)">'
        f'<span style="color:#5a7a96">{label}</span> '
        f'<span style="color:{color}">{value}</span></span>'
    )

# ── Data loading ────────────────────────────────────────────────────────────────
mode         = os.environ.get("TRADING_MODE", "PAPER")
model_dir    = P("/app/models")
eod_model_dir= P("/app/models/eod")
log_path     = P("/app/logs")

model_files   = list(model_dir.glob("*.pkl"))    if model_dir.exists()     else []
eod_files     = list(eod_model_dir.glob("*.pkl"))if eod_model_dir.exists() else []
log_files     = sorted(log_path.glob("*.log"))   if log_path.exists()      else []

trained_stocks = list(set(m.stem.split("_")[0] for m in model_files))

preds    = load_json("/app/logs/eod/predictions.json")
watchlist= load_json("/app/logs/eod/watchlist.json")
patterns = load_json("/app/logs/eod/patterns.json")
regime   = load_json("/app/logs/regime.json")
portfolio= load_json("/app/logs/portfolio.json")
perf_log = load_json("/app/logs/performance_log.json")
alerts   = load_json("/app/logs/alerts.json")

# ── Parse last bot cycle from logs ─────────────────────────────────────────────
last_cycle, signal_lines, raw_positions = "N/A", [], []
if log_files:
    with open(log_files[-1]) as f:
        lines = f.readlines()
    for line in reversed(lines):
        if "Cycle complete" in line and last_cycle == "N/A":
            last_cycle = line.split("|")[0].strip()
        if "SIGNAL:" in line:
            signal_lines.append(line)
        if "POSITION:" in line:
            raw_positions.append(line)
signal_lines = signal_lines[-20:]

# ── Sidebar ─────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<div style="font-family:\'Syne\',sans-serif;font-size:20px;'
        'font-weight:800;color:#00d4ff;letter-spacing:3px;margin-bottom:4px">'
        '⚡ QUANT<br>TERMINAL</div>',
        unsafe_allow_html=True,
    )
    mode_color = "#00e676" if mode == "LIVE" else "#ffd600"
    st.markdown(
        f'<div style="background:#0d1420;border:1px solid {mode_color}44;'
        f'border-radius:2px;padding:6px 12px;margin-bottom:12px">'
        f'<span style="color:{mode_color};font-size:11px;letter-spacing:2px">'
        f'● {mode} MODE</span></div>',
        unsafe_allow_html=True,
    )

    now = datetime.now()
    st.markdown(
        f'<div style="color:#5a7a96;font-size:10px;letter-spacing:1px;'
        f'margin-bottom:16px">{now.strftime("%d %b %Y")}<br>'
        f'<span style="color:#c8d8e8;font-size:14px">{now.strftime("%H:%M:%S")} IST</span></div>',
        unsafe_allow_html=True,
    )

    # Regime pill
    r = regime.get("trend", "UNKNOWN")
    st.markdown(
        f'<div style="margin-bottom:16px">'
        + kv_pill("REGIME", r, "#00e676" if "BULL" in r else "#ff3d6b" if "BEAR" in r else "#ffd600")
        + kv_pill("VIX", regime.get("vix_level", "—"))
        + kv_pill("BREADTH", regime.get("breadth", "—"), "#b967ff")
        + '</div>',
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    c1.metric("Intraday", len(trained_stocks))
    c2.metric("EOD Models", len(eod_files))

    st.markdown("---")

    tab_sel = st.radio(
        "NAVIGATE",
        ["📈 Live Trading", "🌅 EOD Predictions", "🔍 Watchlist & Patterns",
         "🌍 Regime & Context", "📡 Intraday Scanner", "📊 Performance"],
        label_visibility="collapsed",
    )

    st.markdown("---")
    # Daily risk budget
    daily_pnl   = portfolio.get("daily_pnl", 0)
    daily_limit = portfolio.get("daily_loss_limit", -8000)
    budget_used = abs(min(daily_pnl, 0)) / abs(daily_limit) * 100 if daily_pnl < 0 else 0
    bar_color   = "#ff3d6b" if budget_used > 70 else "#ffd600" if budget_used > 40 else "#00e676"
    st.markdown(
        f'<div style="margin-bottom:8px">'
        f'<span style="color:#5a7a96;font-size:10px;letter-spacing:1px">DAILY RISK BUDGET</span><br>'
        f'<div style="background:#0d1420;border:1px solid #1e2d42;border-radius:2px;height:6px;margin:4px 0">'
        f'<div style="background:{bar_color};height:100%;width:{min(budget_used,100):.0f}%;border-radius:2px;'
        f'transition:width 0.5s"></div></div>'
        f'<span style="color:{bar_color};font-size:10px">{budget_used:.0f}% used</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    capital     = portfolio.get("total_capital", 100000)
    deployed    = portfolio.get("deployed", 0)
    deploy_pct  = deployed / capital * 100 if capital else 0
    st.markdown(
        f'<div>'
        f'<span style="color:#5a7a96;font-size:10px;letter-spacing:1px">CAPITAL DEPLOYED</span><br>'
        f'<div style="background:#0d1420;border:1px solid #1e2d42;border-radius:2px;height:6px;margin:4px 0">'
        f'<div style="background:#00d4ff;height:100%;width:{min(deploy_pct,100):.0f}%;border-radius:2px"></div></div>'
        f'<span style="color:#00d4ff;font-size:10px">₹{deployed:,.0f} / ₹{capital:,.0f}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.markdown(
        f'<div style="color:#5a7a96;font-size:9px;letter-spacing:1px">'
        f'LAST CYCLE: {last_cycle[-8:] if last_cycle != "N/A" else "—"}<br>'
        f'AUTO-REFRESH: 30s</div>',
        unsafe_allow_html=True,
    )

# Auto-refresh
st.markdown('<meta http-equiv="refresh" content="30">', unsafe_allow_html=True)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  TAB 1 — LIVE TRADING                                                       ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
if tab_sel == "📈 Live Trading":

    # ── Header strip ───────────────────────────────────────────────────────────
    pnl       = portfolio.get("daily_pnl", 0)
    pnl_pct   = portfolio.get("daily_pnl_pct", 0)
    open_pos  = portfolio.get("open_positions", 0)
    trades_today = portfolio.get("trades_today", 0)
    win_today = portfolio.get("wins_today", 0)
    loss_today= portfolio.get("losses_today", 0)

    pnl_col   = "#00e676" if pnl >= 0 else "#ff3d6b"

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Today's P&L",
              f"₹{pnl:+,.0f}",
              delta=f"{pnl_pct:+.2f}%")
    c2.metric("Open Positions", open_pos)
    c3.metric("Trades Today",   trades_today)
    c4.metric("Wins / Losses",  f"{win_today} / {loss_today}")
    c5.metric("Capital",        f"₹{capital:,.0f}")
    c6.metric("Bot Status",     "🟢 LIVE" if mode == "LIVE" else "🟡 PAPER")

    # ── Portfolio health panel ──────────────────────────────────────────────────
    section_header("PORTFOLIO HEALTH", "real-time risk snapshot")

    pos_list = portfolio.get("positions", [])
    col_a, col_b = st.columns([2, 1])
    with col_a:
        if pos_list:
            rows = []
            for pos in pos_list:
                entry  = pos.get("entry_price", 0)
                ltp    = pos.get("ltp", entry)
                qty    = pos.get("qty", 0)
                pnl_v  = (ltp - entry) * qty
                pnl_p  = (ltp - entry) / entry * 100 if entry else 0
                sl     = pos.get("stop_loss", 0)
                target = pos.get("target", 0)
                rr     = pos.get("rr_ratio", 0)
                rows.append({
                    "Symbol":    pos.get("symbol", "—"),
                    "Side":      pos.get("side", "LONG"),
                    "Qty":       qty,
                    "Entry":     f"₹{entry:.2f}",
                    "LTP":       f"₹{ltp:.2f}",
                    "P&L":       f"₹{pnl_v:+,.0f}",
                    "P&L %":     f"{pnl_p:+.2f}%",
                    "SL":        f"₹{sl:.2f}",
                    "Target":    f"₹{target:.2f}",
                    "R:R":       f"{rr:.1f}",
                })
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No open positions.")

    with col_b:
        # Risk warnings
        warnings = portfolio.get("risk_warnings", [])
        if warnings:
            for w in warnings:
                st.warning(w)
        corr_warn = portfolio.get("correlation_warning", "")
        if corr_warn:
            st.markdown(
                f'<div style="background:#3d0018;border:1px solid #ff3d6b;'
                f'border-radius:2px;padding:8px 12px;font-size:11px;color:#ff3d6b">'
                f'⚠ CORR WARNING<br><span style="color:#c8d8e8">{corr_warn}</span></div>',
                unsafe_allow_html=True,
            )
        # Regime sizing note
        size_mult = regime.get("position_size_multiplier", 1.0)
        color     = "#00e676" if size_mult >= 1 else "#ffd600" if size_mult >= 0.7 else "#ff3d6b"
        st.markdown(
            f'<div style="background:#0d1420;border:1px solid #1e2d42;'
            f'border-radius:2px;padding:8px 12px;margin-top:8px">'
            f'<div style="color:#5a7a96;font-size:10px;letter-spacing:1px">REGIME SIZING</div>'
            f'<div style="color:{color};font-size:20px;font-weight:700">{size_mult:.1f}×</div>'
            f'<div style="color:#5a7a96;font-size:10px">of base position size</div></div>',
            unsafe_allow_html=True,
        )

    # ── Intraday Models ─────────────────────────────────────────────────────────
    section_header("INTRADAY MODELS", f"{len(trained_stocks)} trained")

    if trained_stocks:
        model_data = []
        for sym in sorted(trained_stocks)[:30]:
            versions = sorted([m for m in model_files if m.stem.startswith(sym)], reverse=True)
            if versions:
                meta    = load_model_meta(versions[0])
                metrics = meta.get("metrics", {})
                sharpe  = metrics.get("sharpe", 0)
                wr      = metrics.get("win_rate", 0)
                ic      = metrics.get("ic", 0)
                # Status
                if sharpe > 0.5 and wr > 0.55:   status = "✅ ACTIVE"
                elif sharpe > 0.3 and wr > 0.52: status = "🟡 MARGINAL"
                else:                             status = "⛔ EXCLUDED"
                model_data.append({
                    "Symbol":   sym,
                    "Sharpe":   round(sharpe, 3),
                    "IC":       round(ic, 4),
                    "Win Rate": f"{wr:.1%}",
                    "Versions": len(versions),
                    "Status":   status,
                })
        if model_data:
            st.dataframe(
                pd.DataFrame(model_data).sort_values("Sharpe", ascending=False),
                use_container_width=True, hide_index=True,
            )

    # ── Recent signals ──────────────────────────────────────────────────────────
    section_header("RECENT SIGNALS", "last 15 entries")

    if signal_lines:
        for sl in reversed(signal_lines[-15:]):
            text = sl.split("SIGNAL:")[-1].strip()[:140]
            is_buy  = "BUY"  in text.upper()
            is_sell = "SELL" in text.upper()
            bg   = "#003d20" if is_buy else "#3d0018" if is_sell else "#1a1a00"
            col  = "#00e676" if is_buy else "#ff3d6b" if is_sell else "#ffd600"
            st.markdown(
                f'<div style="background:{bg};border-left:3px solid {col};'
                f'padding:6px 12px;margin:3px 0;font-size:11px;border-radius:0 2px 2px 0;'
                f'font-family:var(--mono);color:#c8d8e8">{text}</div>',
                unsafe_allow_html=True,
            )
    else:
        st.info("No signals yet — bot is running.")


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  TAB 2 — EOD PREDICTIONS                                                    ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
elif tab_sel == "🌅 EOD Predictions":

    total      = len(preds)
    buys       = sum(1 for p in preds.values() if p.get("direction") == "BUY")
    sells      = sum(1 for p in preds.values() if p.get("direction") == "SELL")
    holds      = total - buys - sells
    high_conf  = sum(1 for p in preds.values() if p.get("confidence", 0) > 0.70)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Stocks",   total)
    c2.metric("▲ BUY",          buys)
    c3.metric("▼ SELL",         sells)
    c4.metric("◆ HOLD",         holds)
    c5.metric("High Confidence",high_conf)

    # Signal distribution bar
    if total:
        buy_pct  = buys  / total * 100
        sell_pct = sells / total * 100
        hold_pct = holds / total * 100
        st.markdown(
            f'<div style="margin:12px 0 4px;height:8px;border-radius:4px;overflow:hidden;'
            f'display:flex;background:#0d1420;border:1px solid #1e2d42">'
            f'<div style="width:{buy_pct:.1f}%;background:#00e676"></div>'
            f'<div style="width:{hold_pct:.1f}%;background:#ffd600"></div>'
            f'<div style="width:{sell_pct:.1f}%;background:#ff3d6b"></div>'
            f'</div>'
            f'<div style="font-size:10px;color:#5a7a96">'
            f'▲ {buy_pct:.0f}% BUY &nbsp;&nbsp; ◆ {hold_pct:.0f}% HOLD &nbsp;&nbsp; ▼ {sell_pct:.0f}% SELL</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # Filters
    col_f1, col_f2, col_f3, _ = st.columns([1, 1, 1, 3])
    sig_filter  = col_f1.selectbox("Signal", ["ALL", "BUY", "SELL", "HOLD"])
    conf_filter = col_f2.selectbox("Confidence", ["ALL", "> 70%", "> 60%", "> 50%"])
    tier_filter = col_f3.selectbox("Tier", ["ALL", "HIGH CONVICTION", "MODERATE", "SPECULATIVE"])

    # Build rows
    if preds:
        rows = []
        for sym, p in preds.items():
            pat        = patterns.get(sym, {})
            direction  = p.get("direction", "HOLD")
            confidence = p.get("confidence", 0)
            tier       = pat.get("tier", "")

            # Apply filters
            if sig_filter  != "ALL" and direction != sig_filter:         continue
            if conf_filter == "> 70%" and confidence <= 0.70:            continue
            if conf_filter == "> 60%" and confidence <= 0.60:            continue
            if conf_filter == "> 50%" and confidence <= 0.50:            continue
            if tier_filter != "ALL" and tier.upper() != tier_filter:     continue

            lc         = p.get("last_close", 0)
            exp_ret    = p.get("expected_return", 0)
            pred_close = lc * (1 + exp_ret) if lc else 0
            risk       = p.get("risk_score", 0)
            wr         = p.get("win_rate",   0)
            sl         = p.get("stop_loss",  0)
            tgt        = p.get("target",     0)
            rr         = p.get("rr_ratio",   0)

            rows.append({
                "Symbol":       sym,
                "Sector":       p.get("sector", "—"),
                "Last Close":   f"₹{lc:.2f}"         if lc else "—",
                "Pred Close":   f"₹{pred_close:.2f}" if pred_close else "—",
                "Exp Return":   f"{exp_ret*100:+.2f}%" if exp_ret else "—",
                "Confidence":   f"{confidence:.0%}",
                "Win Rate":     f"{wr:.0%}",
                "Risk":         f"{risk:.2f}"         if risk else "—",
                "SL":           f"₹{sl:.2f}"          if sl else "—",
                "Target":       f"₹{tgt:.2f}"         if tgt else "—",
                "R:R":          f"{rr:.1f}"            if rr else "—",
                "Signal":       direction,
                "Pattern":      ", ".join(pat.get("patterns", [])) if pat else "—",
                "Tier":         tier,
            })

        if rows:
            df = pd.DataFrame(rows)

            def row_style(row):
                sig = row["Signal"]
                if sig == "BUY":  return ["background-color: #001a0d"] * len(row)
                if sig == "SELL": return ["background-color: #1a000a"] * len(row)
                return [""] * len(row)

            st.dataframe(
                df.style.apply(row_style, axis=1),
                use_container_width=True,
                height=480,
                hide_index=True,
            )

            # Top 5 BUY picks
            top_buys = [r for r in rows if r["Signal"] == "BUY"]
            top_buys.sort(key=lambda x: float(x["Confidence"].replace("%", "")), reverse=True)
            if top_buys:
                section_header("TOP BUY PICKS", "sorted by confidence")
                cols = st.columns(min(5, len(top_buys)))
                for i, pick in enumerate(top_buys[:5]):
                    with cols[i]:
                        st.markdown(
                            f'<div style="background:#001a0d;border:1px solid #00e676;'
                            f'border-radius:2px;padding:12px;text-align:center">'
                            f'<div style="font-family:\'Syne\',sans-serif;font-size:15px;'
                            f'font-weight:700;color:#00e676">{pick["Symbol"]}</div>'
                            f'<div style="color:#5a7a96;font-size:10px">{pick["Sector"]}</div>'
                            f'<div style="color:#c8d8e8;font-size:18px;margin:4px 0">{pick["Exp Return"]}</div>'
                            f'<div style="color:#5a7a96;font-size:10px">conf {pick["Confidence"]}</div>'
                            f'<div style="color:#c8d8e8;font-size:10px;margin-top:4px">'
                            f'SL {pick["SL"]} · T {pick["Target"]}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
        else:
            st.info("No predictions match the current filters.")
    else:
        st.info("No predictions yet. Run `src/scripts/run_eod_predictions.py`.")


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  TAB 3 — WATCHLIST & PATTERNS                                               ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
elif tab_sel == "🔍 Watchlist & Patterns":

    section_header("DYNAMIC WATCHLIST", f"{len(watchlist)} stocks · scored & ranked")

    if watchlist:
        # Source breakdown
        sources = {}
        for info in watchlist.values():
            s = info.get("source", "unknown")
            sources[s] = sources.get(s, 0) + 1

        src_cols = st.columns(len(sources) or 1)
        for i, (src, cnt) in enumerate(sorted(sources.items(), key=lambda x: -x[1])):
            src_cols[i % len(src_cols)].metric(src.replace("_", " ").upper(), cnt)

        st.markdown("---")

        col_left, col_right = st.columns([3, 2])

        with col_left:
            section_header("TOP 30 BY SCORE")
            wl_rows = []
            for sym, info in sorted(watchlist.items(), key=lambda x: x[1].get("score", 0), reverse=True)[:30]:
                score  = info.get("score", 0)
                source = info.get("source", "—")
                volume = info.get("volume_ratio", 0)
                ret5d  = info.get("return_5d", 0)
                liq    = info.get("liquidity_score", 0)

                score_bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
                wl_rows.append({
                    "Symbol":       sym,
                    "Score":        f"{score:.3f}",
                    "Momentum Bar": score_bar[:10],
                    "Source":       source,
                    "Vol Ratio":    f"{volume:.1f}×" if volume else "—",
                    "5D Return":    f"{ret5d*100:+.1f}%" if ret5d else "—",
                })
            st.dataframe(pd.DataFrame(wl_rows), use_container_width=True, hide_index=True)

        with col_right:
            section_header("SOURCES BREAKDOWN")
            for src, cnt in sorted(sources.items(), key=lambda x: -x[1]):
                pct = cnt / len(watchlist) * 100
                st.markdown(
                    f'<div style="margin:6px 0">'
                    f'<div style="display:flex;justify-content:space-between;'
                    f'font-size:11px;margin-bottom:2px">'
                    f'<span style="color:#c8d8e8">{src.replace("_"," ").upper()}</span>'
                    f'<span style="color:#5a7a96">{cnt} stocks</span></div>'
                    f'<div style="background:#0d1420;border:1px solid #1e2d42;height:4px;border-radius:2px">'
                    f'<div style="background:#00d4ff;height:100%;width:{pct:.0f}%;border-radius:2px"></div>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
    else:
        st.info("No watchlist data. Run the morning scan.")

    st.markdown("---")
    section_header("PATTERN RECOGNITION", "quality-scored setups")

    if patterns:
        p_rows = []
        for sym, pat in patterns.items():
            detected = pat.get("patterns", [])
            if not detected:
                continue
            quality = pat.get("quality_score", 0)
            tier    = pat.get("tier", "SPECULATIVE")
            vol_conf= pat.get("volume_confirmed", False)
            p_rows.append({
                "Symbol":   sym,
                "Patterns": ", ".join(detected),
                "Quality":  f"{quality:.0%}",
                "Tier":     tier,
                "Vol OK":   "✅" if vol_conf else "❌",
                "Sector Aligned": "✅" if pat.get("sector_aligned") else "❌",
            })

        if p_rows:
            df_p = pd.DataFrame(p_rows).sort_values("Quality", ascending=False)
            st.dataframe(df_p, use_container_width=True, hide_index=True, height=360)

        # Pattern frequency chart (text-based)
        all_patterns = []
        for pat in patterns.values():
            all_patterns.extend(pat.get("patterns", []))
        pat_freq = {}
        for p in all_patterns:
            pat_freq[p] = pat_freq.get(p, 0) + 1

        if pat_freq:
            section_header("PATTERN FREQUENCY")
            max_cnt = max(pat_freq.values())
            for pat_name, cnt in sorted(pat_freq.items(), key=lambda x: -x[1]):
                bar_w = int(cnt / max_cnt * 30)
                st.markdown(
                    f'<div style="display:flex;align-items:center;margin:4px 0;font-size:11px">'
                    f'<span style="color:#c8d8e8;width:200px">{pat_name}</span>'
                    f'<span style="color:#00d4ff;letter-spacing:-1px">{"█" * bar_w}</span>'
                    f'<span style="color:#5a7a96;margin-left:8px">{cnt}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
    else:
        st.info("No pattern data. Run the morning scan.")


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  TAB 4 — REGIME & GLOBAL CONTEXT                                            ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
elif tab_sel == "🌍 Regime & Context":

    section_header("MARKET REGIME ENGINE", "4-state regime detection")

    r_trend   = regime.get("trend",     "UNKNOWN")
    r_vol     = regime.get("vol",       "UNKNOWN")
    r_breadth = regime.get("breadth",   "UNKNOWN")
    r_liq     = regime.get("liquidity", "UNKNOWN")
    r_playbook= regime.get("playbook",  {})

    c1, c2, c3, c4 = st.columns(4)
    for col, label, val, color_map in [
        (c1, "TREND",     r_trend,   {"BULL":"#00e676","BEAR":"#ff3d6b","SIDEWAYS":"#ffd600","CHOP":"#ff6b35"}),
        (c2, "VOLATILITY",r_vol,     {"LOW":"#00e676","NORMAL":"#00d4ff","HIGH":"#ffd600","EXTREME":"#ff3d6b"}),
        (c3, "BREADTH",   r_breadth, {"BROAD":"#00e676","NARROW":"#ffd600","DIVERGING":"#ff3d6b"}),
        (c4, "LIQUIDITY", r_liq,     {"RISK_ON":"#00e676","RISK_OFF":"#ff3d6b"}),
    ]:
        c = color_map.get(val, "#5a7a96")
        col.markdown(
            f'<div style="background:#0d1420;border:1px solid {c}44;border-radius:2px;'
            f'padding:16px;text-align:center">'
            f'<div style="color:#5a7a96;font-size:10px;letter-spacing:2px">{label}</div>'
            f'<div style="color:{c};font-size:22px;font-weight:700;font-family:\'Syne\','
            f'sans-serif;margin:8px 0">{val}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Regime playbook
    if r_playbook:
        st.markdown("---")
        section_header("REGIME PLAYBOOK", "current rules")
        bias       = r_playbook.get("bias",             "—")
        size_mult  = r_playbook.get("size_multiplier",  1.0)
        stop_mult  = r_playbook.get("stop_multiplier",  1.0)
        preferred  = r_playbook.get("preferred_setups", [])
        avoided    = r_playbook.get("avoid_setups",     [])

        pb1, pb2, pb3 = st.columns(3)
        pb1.metric("Directional Bias", bias)
        pb2.metric("Size Multiplier",  f"{size_mult:.1f}×")
        pb3.metric("Stop Multiplier",  f"{stop_mult:.1f}×")

        if preferred:
            st.success(f"✅ Preferred: {', '.join(preferred)}")
        if avoided:
            st.error(f"⛔ Avoid: {', '.join(avoided)}")

    # Global context
    st.markdown("---")
    section_header("GLOBAL CONTEXT", "pre-market signals")

    gc = regime.get("global_context", {})
    if gc:
        g_rows = []
        for key, info in gc.items():
            val   = info.get("value",  "—")
            chg   = info.get("change", 0)
            impact= info.get("impact", "—")
            arrow = "▲" if chg > 0 else "▼" if chg < 0 else "—"
            color = "#00e676" if chg > 0 else "#ff3d6b" if chg < 0 else "#5a7a96"
            g_rows.append({
                "Instrument": key.replace("_", " ").upper(),
                "Value":      str(val),
                "Change":     f'{arrow} {abs(chg):.2f}%' if chg else "—",
                "Impact":     impact,
            })
        st.dataframe(pd.DataFrame(g_rows), use_container_width=True, hide_index=True)
    else:
        # Placeholder display
        placeholders = [
            ("SGX NIFTY",  "—", "—", "Opening gap indicator"),
            ("S&P 500 FUT","—", "—", "IT sector bias"),
            ("CRUDE OIL",  "—", "—", "Energy sector bias"),
            ("GOLD",       "—", "—", "Safe haven sentiment"),
            ("USD/INR",    "—", "—", "FII flow proxy"),
        ]
        df_gc = pd.DataFrame(placeholders, columns=["Instrument","Value","Change","Impact"])
        st.dataframe(df_gc, use_container_width=True, hide_index=True)
        st.caption("Fetch live data by running the global context module.")

    # Sector rotation
    st.markdown("---")
    section_header("SECTOR ROTATION", "1-day performance")
    sector_data = regime.get("sector_returns", {})
    if sector_data:
        sorted_sectors = sorted(sector_data.items(), key=lambda x: x[1], reverse=True)
        for sec, ret in sorted_sectors:
            bar_len  = abs(ret) * 20
            bar_color= "#00e676" if ret >= 0 else "#ff3d6b"
            direction= "█" * int(min(bar_len, 40))
            st.markdown(
                f'<div style="display:flex;align-items:center;margin:4px 0;font-size:11px">'
                f'<span style="color:#c8d8e8;width:180px">{sec}</span>'
                f'''{"<span style='color:#5a7a96'>" + "░" * int(min(abs(ret)*20,40)) + "</span>" if ret < 0 else ""}'''
                f'<span style="color:{bar_color}">{direction}</span>'
                f'<span style="color:{bar_color};margin-left:8px">{ret:+.2f}%</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.info("Sector data not yet loaded.")


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  TAB 5 — INTRADAY SCANNER                                                   ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
elif tab_sel == "📡 Intraday Scanner":

    section_header("LIVE SCANNER ALERTS", "tiered signal stream")

    alert_list = alerts.get("alerts", [])

    t1 = [a for a in alert_list if a.get("tier") == 1]
    t2 = [a for a in alert_list if a.get("tier") == 2]
    t3 = [a for a in alert_list if a.get("tier") == 3]

    ca, cb, cc = st.columns(3)
    ca.metric("🔴 Tier 1 (Urgent)",  len(t1))
    cb.metric("🟡 Tier 2 (Alert)",   len(t2))
    cc.metric("⚪ Tier 3 (Watch)",   len(t3))

    st.markdown("---")

    def render_alert(a: dict) -> None:
        tier   = a.get("tier",   3)
        sym    = a.get("symbol", "—")
        msg    = a.get("message","—")
        score  = a.get("score",  0)
        tags   = a.get("tags",   [])
        ts     = a.get("time",   "")
        entry  = a.get("entry_zone", "")
        sl     = a.get("stop_loss",  "")
        tgt    = a.get("target",     "")
        rr     = a.get("rr_ratio",   "")

        tier_cfg = {
            1: ("#ff3d6b", "#3d0018", "🔴 URGENT"),
            2: ("#ffd600", "#3d3000", "🟡 ALERT"),
            3: ("#5a7a96", "#0d1420", "⚪ WATCH"),
        }
        bdr, bg, label = tier_cfg.get(tier, tier_cfg[3])

        tags_html = " ".join(
            f'<span style="background:#0d1420;border:1px solid #1e2d42;'
            f'border-radius:2px;padding:1px 6px;font-size:9px;color:#5a7a96">{t}</span>'
            for t in tags
        )

        st.markdown(
            f'<div style="background:{bg};border-left:3px solid {bdr};'
            f'border-radius:0 2px 2px 0;padding:12px 16px;margin:6px 0">'
            f'<div style="display:flex;justify-content:space-between;align-items:center">'
            f'<span style="font-family:\'Syne\',sans-serif;font-size:14px;'
            f'font-weight:700;color:{bdr}">{sym}</span>'
            f'<span style="font-size:9px;color:#5a7a96">{label} · score {score} · {ts}</span>'
            f'</div>'
            f'<div style="color:#c8d8e8;font-size:11px;margin:4px 0">{msg}</div>'
            f'<div style="margin:4px 0">{tags_html}</div>'
            + (
                f'<div style="font-size:10px;color:#5a7a96;margin-top:6px">'
                f'Entry: <span style="color:#c8d8e8">{entry}</span> · '
                f'SL: <span style="color:#ff3d6b">{sl}</span> · '
                f'Target: <span style="color:#00e676">{tgt}</span> · '
                f'R:R: <span style="color:#00d4ff">{rr}</span>'
                f'</div>'
                if entry else ""
            )
            + '</div>',
            unsafe_allow_html=True,
        )

    if alert_list:
        col_t1, col_t2 = st.columns([1, 1])
        with col_t1:
            section_header("TIER 1 — ACT NOW")
            if t1:
                for a in sorted(t1, key=lambda x: x.get("score", 0), reverse=True):
                    render_alert(a)
            else:
                st.markdown('<div style="color:#5a7a96;font-size:11px;padding:12px">No Tier 1 alerts</div>',
                            unsafe_allow_html=True)

        with col_t2:
            section_header("TIER 2 — MONITOR")
            if t2:
                for a in sorted(t2, key=lambda x: x.get("score", 0), reverse=True):
                    render_alert(a)
            else:
                st.markdown('<div style="color:#5a7a96;font-size:11px;padding:12px">No Tier 2 alerts</div>',
                            unsafe_allow_html=True)

        section_header("TIER 3 — ON RADAR")
        if t3:
            t3_cols = st.columns(2)
            for i, a in enumerate(t3):
                with t3_cols[i % 2]:
                    render_alert(a)
        else:
            st.markdown('<div style="color:#5a7a96;font-size:11px;padding:12px">No Tier 3 alerts</div>',
                        unsafe_allow_html=True)
    else:
        st.info("No alerts yet. Scanner starts at 9:15 AM.")


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  TAB 6 — PERFORMANCE                                                        ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
elif tab_sel == "📊 Performance":

    section_header("PERFORMANCE ANALYTICS", "walk-forward · model health · calibration")

    history = perf_log.get("daily_history", [])

    if history:
        df_h = pd.DataFrame(history)
        df_h["date"] = pd.to_datetime(df_h["date"])
        df_h = df_h.sort_values("date")

        # Summary metrics
        total_trades = df_h["trades"].sum()    if "trades" in df_h else 0
        total_pnl    = df_h["pnl"].sum()       if "pnl"    in df_h else 0
        avg_wr       = df_h["win_rate"].mean()  if "win_rate" in df_h else 0
        best_day     = df_h["pnl"].max()        if "pnl" in df_h else 0
        worst_day    = df_h["pnl"].min()        if "pnl" in df_h else 0
        cum_pnl_last = df_h["cum_pnl"].iloc[-1] if "cum_pnl" in df_h else 0

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Total P&L",   f"₹{total_pnl:+,.0f}")
        c2.metric("Total Trades",total_trades)
        c3.metric("Avg Win Rate",f"{avg_wr:.1%}")
        c4.metric("Best Day",    f"₹{best_day:+,.0f}")
        c5.metric("Worst Day",   f"₹{worst_day:+,.0f}")
        c6.metric("Cum P&L",     f"₹{cum_pnl_last:+,.0f}")

        st.markdown("---")

        # Cumulative P&L chart (native Streamlit line_chart)
        if "cum_pnl" in df_h and "date" in df_h:
            section_header("CUMULATIVE P&L CURVE")
            chart_df = df_h.set_index("date")[["cum_pnl"]]
            st.line_chart(chart_df, use_container_width=True, height=200)

        # Daily P&L bar chart
        if "pnl" in df_h and "date" in df_h:
            section_header("DAILY P&L")
            bar_df = df_h.set_index("date")[["pnl"]]
            st.bar_chart(bar_df, use_container_width=True, height=160)

        # Model-level performance
        st.markdown("---")
        section_header("MODEL PERFORMANCE BREAKDOWN", "per-symbol health")
        sym_perf = perf_log.get("symbol_performance", {})
        if sym_perf:
            sp_rows = []
            for sym, sp in sym_perf.items():
                wr_20   = sp.get("win_rate_20d",  0)
                ic_20   = sp.get("ic_20d",        0)
                sharpe  = sp.get("sharpe_90d",    0)
                status  = "✅" if wr_20 > 0.52 else "⚠️" if wr_20 > 0.48 else "🔴"
                drift   = "⚠️ DRIFT" if sp.get("feature_drift", False) else "OK"
                sp_rows.append({
                    "Symbol":       sym,
                    "WR (20d)":     f"{wr_20:.1%}",
                    "IC (20d)":     f"{ic_20:.4f}",
                    "Sharpe (90d)": f"{sharpe:.2f}",
                    "Status":       status,
                    "Drift":        drift,
                })
            st.dataframe(
                pd.DataFrame(sp_rows).sort_values("WR (20d)", ascending=False),
                use_container_width=True, hide_index=True, height=360,
            )

        # Prediction log accuracy
        st.markdown("---")
        section_header("EOD PREDICTION ACCURACY", "directional hit rate")
        pred_acc = perf_log.get("eod_accuracy", {})
        if pred_acc:
            acc_rows = []
            for sym, acc in pred_acc.items():
                acc_rows.append({
                    "Symbol":       sym,
                    "Hit Rate":     f"{acc.get('hit_rate', 0):.1%}",
                    "Conf Cal.":    f"{acc.get('conf_calibration', 0):.2f}",
                    "Predictions":  acc.get("total_predictions", 0),
                    "Last 20 WR":   f"{acc.get('last_20_wr', 0):.1%}",
                    "Degraded":     "🔴 YES" if acc.get("degraded", False) else "✅ NO",
                })
            st.dataframe(pd.DataFrame(acc_rows), use_container_width=True, hide_index=True)
        else:
            st.info("EOD accuracy data will populate after predictions are live for 5+ days.")
    else:
        # Empty state with useful message
        st.markdown(
            '<div style="background:#0d1420;border:1px solid #1e2d42;border-radius:4px;'
            'padding:40px;text-align:center">'
            '<div style="font-family:\'Syne\',sans-serif;font-size:18px;color:#5a7a96;'
            'margin-bottom:8px">NO PERFORMANCE DATA YET</div>'
            '<div style="color:#5a7a96;font-size:11px">'
            'Performance history populates after the bot runs for at least one full trading day.<br>'
            'Expected keys: <code>daily_history</code>, <code>symbol_performance</code>, '
            '<code>eod_accuracy</code> in <code>/app/logs/performance_log.json</code>'
            '</div></div>',
            unsafe_allow_html=True,
        )


# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    f'<div style="display:flex;justify-content:space-between;font-size:10px;'
    f'color:#5a7a96;letter-spacing:1px">'
    f'<span>⚡ QUANT TERMINAL · {mode} MODE</span>'
    f'<span>AUTO-REFRESH 30s</span>'
    f'<span>BUILD {datetime.now().strftime("%Y.%m.%d")}</span>'
    f'</div>',
    unsafe_allow_html=True,
)