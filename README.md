<div align="center">

```
████████╗███████╗████████╗██████╗ ██╗███████╗
   ██╔══╝██╔════╝╚══██╔══╝██╔══██╗██║██╔════╝
   ██║   █████╗     ██║   ██████╔╝██║███████╗
   ██║   ██╔══╝     ██║   ██╔══██╗██║╚════██║
   ██║   ███████╗   ██║   ██║  ██║██║███████║
   ╚═╝   ╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝╚══════╝
```

### **Multi Strategy AI Trading System NSE India**
*Autonomous · ML Powered · Institutionally Risk Managed*

<br/>

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-REST_API-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Redis](https://img.shields.io/badge/Redis-Cache-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io/)
[![PyTorch](https://img.shields.io/badge/PyTorch-LSTM-EE4C2C?style=for-the-badge&logo=pytorch&logoColor=white)](https://pytorch.org/)
[![XGBoost](https://img.shields.io/badge/XGBoost-Ensemble-FF6600?style=for-the-badge)](https://xgboost.readthedocs.io/)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-ML-F7931E?style=for-the-badge&logo=scikit-learn&logoColor=white)](https://scikit-learn.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-Dashboard-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-F7DF1E?style=for-the-badge)](LICENSE)
[![NSE](https://img.shields.io/badge/Exchange-NSE_India-FF6600?style=for-the-badge)](https://www.nseindia.com/)
[![Status](https://img.shields.io/badge/Status-Paper_Trading-00C853?style=for-the-badge)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen?style=for-the-badge)](CONTRIBUTING.md)

</div>

---

## Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Architecture](#-architecture)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Installation](#-installation)
- [Usage](#-usage)
- [API Endpoints](#-api-endpoints)
- [Dashboard](#-dashboard)
- [Risk Management](#-risk-management)
- [ML Models](#-ml-models)
- [Future Roadmap](#-future-roadmap)
- [Contributing](#-contributing)
- [License](#-license)
- [Author](#-author)
- [Disclaimer](#-disclaimer)

---

## Overview

**TETRIS** is a fully autonomous, AI driven algorithmic trading system engineered for the Indian stock market (NSE). It combines machine learning ensembles with battle tested rule based strategies to trade 50 Nifty stocks across multiple time horizons all guarded by institutional grade risk controls.

The system runs 4 containerized microservices via Docker Compose, exposes 12+ REST endpoints via FastAPI, and delivers a 6 tab premium dashboard with realtime P&L, signals, regime analysis, and model performance with Telegram alerts and automated PDF reports.

> Currently deployed in **paper trading mode** via Zerodha Kite Connect API.

```
ML Ensemble + Rule-Based Strategies → Microstructure Filter → Risk Engine → Order Execution
```

---

## Features

### Machine Learning
- **Dual horizon ML ensemble** 60-min intraday predictions + nextday EOD(End of the day)forecasts
- **65+ engineered technical features** with strict lookahead prevention
- **Walk-forward validation** with purge embargo gaps for realistic backtesting
- **Hyperparameter optimization** via Optuna (50+ trials per model)
- **Automated daily retraining** models stay fresh without manual intervention

### Trading Strategies
- **Intraday ML (60-min)** RF + XGBoost + LSTM ensemble for moves >0.25%
- **EOD Predictions** Daily RF + XGBoost classifier for directional moves >0.5%
- **Mean Reversion** RSI + VWAP rule based, targets +1% recovery in 10–45 min
- **Momentum** 1–5 day return continuation with RSI confirmation
- **Microstructure Filter** Order book supply/demand validation on every signal

### Risk Management
- Half Kelly position sizing with 1% capital risk per trade
- ATR-based stop losses with trailing logic
- Circuit breakers, daily loss limits, sector & correlation limits
- Full details in the [Risk Management](#-risk-management) section

### Infrastructure
- **6 tab institutional dashboard** with real time P&L, sparklines, and charts
- **12+ REST API endpoints** via FastAPI
- **Telegram alerts** for signals, exits, and system errors
- **Automated PDF report** generation post market
- **Docker containerized** with 4 microservices
- **Persistent Kite session** management with auto login

---

## Architecture

TETRIS runs as **4 microservices** orchestrated via Docker Compose:

```
┌─────────────────────────────────────────────────────────────────┐
│                        TETRIS SYSTEM                            │
│                                                                 │
│  ┌───────────────────┐      ┌──────────────────────────────┐    │
│  │  trading_bot_main │      │      trading_bot_api         │    │
│  │                   │◄────►│   FastAPI · 12+ endpoints    │    │
│  │  • Orchestrator   │      │   Port: 8502                 │    │
│  │  • ML Predictions │      └──────────────────────────────┘    │
│  │  • Order Manager  │                                          │
│  │  • Risk Engine    │      ┌──────────────────────────────┐    │
│  │  • Retraining     │◄────►│      trading_bot_redis       │    │
│  └───────────────────┘      │   Redis · Historical Cache   │    │
│                             └──────────────────────────────┘    │
│                                                                 │
│                             ┌──────────────────────────────┐    │
│                             │   trading_bot_dashboard      │    │
│                             │          Port: 8501          │    │
│                             └──────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
         │                          │
         ▼                          ▼
  Zerodha Kite API            Telegram Bot
  (Order Execution)           (Alerts & Reports)
```

**Signal Flow:**
```
Market Data → Feature Engineering → ML Ensemble → Microstructure Filter
→ Risk Engine → Kelly Sizing → Order Execution → Monitoring & Alerts
```

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Runtime** | Python 3.11 | Core language |
| **API** | FastAPI | 12+ REST endpoints, dashboard backend |
| **Cache** | Redis | Historical data caching, session state |
| **Containers** | Docker + Docker Compose | 4-microservice orchestration |
| **ML — Ensemble** | scikit-learn (RF), XGBoost | Classification, feature importance |
| **ML — Deep** | PyTorch (LSTM) | Sequence modeling for intraday |
| **ML — Tuning** | Optuna | Hyperparameter optimization (50+ trials) |
| **Data** | Pandas, NumPy | Feature engineering, data pipelines |
| **Broker API** | Zerodha Kite Connect | Market data, order execution |
| **Dashboard** | HTML5/CSS3/JS, Chart.js | Premium 6-tab trading dashboard |
| **Backup UI** | Streamlit | Lightweight backup dashboard |
| **Alerts** | Telegram Bot API | Real-time signal & error notifications |
| **DevOps** | Shell Scripts, Cron | Daily automation, retraining, backups |

---

## Project Structure

```
tetris/
├── src/
│   ├── api/                    # FastAPI server REST endpoints
│   │   ├── main.py             # App entrypoint, route registration
│   │   └── routes/             # Modular route handlers
│   ├── auth/                   # Zerodha Kite session management
│   │   ├── kite_auth.py        # Auto-login, token refresh
│   │   └── session_manager.py  # Persistent session handling
│   ├── backtest/               # Vectorized backtesting engine
│   │   ├── engine.py           # Core backtester with cost model
│   │   └── metrics.py          # Sharpe, drawdown, win rate
│   ├── data/                   # Market data layer
│   │   ├── kite_fetcher.py     # Live & historical OHLCV via Kite
│   │   ├── cache.py            # Redis caching layer
│   │   └── calendar.py         # NSE trading calendar
│   ├── features/               # Feature engineering (65+ features)
│   │   ├── technical.py        # RSI, MACD, Bollinger, ATR, VWAP...
│   │   ├── microstructure.py   # Order book depth, bid ask spread
│   │   └── market_relative.py  # Nifty relative, sector features
│   ├── models/                 # ML pipeline
│   │   ├── trainer.py          # Walk-forward training with embargo
│   │   ├── predictor.py        # Inference with confidence scoring
│   │   ├── ensemble.py         # RF + XGBoost + LSTM ensemble
│   │   └── optimizer.py        # Optuna hyperparameter search
│   ├── monitoring/             # Observability layer
│   │   ├── dashboard.py        # Dashboard data aggregation
│   │   ├── alerts.py           # Telegram alert dispatcher
│   │   └── performance.py      # Live P&L, drawdown tracking
│   ├── risk/                   # Risk management engine
│   │   ├── position_sizer.py   # Half Kelly sizing
│   │   ├── stop_loss.py        # ATR trailing stops
│   │   └── portfolio.py        # Sector limits, correlation checks
│   ├── scanner/                # Intraday opportunity scanner
│   │   ├── volume_scanner.py   # Unusual volume detection
│   │   ├── breakout_scanner.py # Technical breakout alerts
│   │   └── rsi_scanner.py      # RSI extreme scanner
│   ├── strategies/             # Strategy implementations
│   │   ├── mean_reversion.py   # RSI + VWAP mean reversion
│   │   └── momentum.py         # 1–5 day momentum strategy
│   └── trading/                # Execution layer
│       ├── executor.py         # Order placement via Kite API
│       ├── order_manager.py    # Order lifecycle management
│       └── cost_model.py       # Brokerage, STT, slippage model
├── config/
│   ├── trading.yaml            # Universe, capital, broker settings
│   ├── risk.yaml               # All risk limits & circuit breakers
│   ├── models.yaml             # Feature sets, hyperparameter spaces
│   └── strategies.yaml         # Entry/exit rules per strategy
├── docker/
│   └── Dockerfile              # Multi stage Python build
├── frontend/
│   ├── index.html              # Premium 6 tab dashboard
│   ├── styles.css              # Dashboard styling
│   └── charts.js               # Chart.js visualizations
├── scripts/
│   ├── start_tetris.sh         # Morning startup sequence
│   ├── watch_tetris.sh         # Live log monitoring
│   └── stop_tetris.sh          # Evening shutdown + retrain
├── tests/
│   ├── unit/                   # Unit tests per module
│   └── integration/            # End-to-end pipeline tests
├── logs/                       # Daily logs & JSON data    [gitignored]
├── models/                     # Saved ML pipelines        [gitignored]
├── docker-compose.yml
├── requirements.txt
├── .env.template
└── README.md
```

---

## Installation

### Prerequisites

| Requirement | Details |
|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | v24+ recommended |
| [Zerodha Kite Connect](https://kite.trade/) | API key + secret |
| Telegram Bot Token | For real time alerts [@BotFather](https://t.me/BotFather) |
| Python 3.11 *(optional)* | For local dev without Docker |

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/raashxi/tetris-trading-system.git
cd tetris-trading-system

# 2. Configure your credentials
cp .env.template .env
```

Edit `.env` with your credentials:

```env
# Zerodha Kite Connect
KITE_API_KEY=your_api_key_here
KITE_API_SECRET=your_api_secret_here
KITE_USER_ID=your_user_id

# Telegram Alerts
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# System
CAPITAL=1000000          # Starting capital in INR
PAPER_TRADING=true       # Set to false for live trading
LOG_LEVEL=INFO
```

```bash
# 3. Build and launch all 4 microservices
docker-compose up -d --build

# 4. Verify all services are running
docker-compose ps

# 5. Access the dashboard
open http://localhost:8502
```

---

## Usage

### Daily Operations

```bash
# Morning run before 9:15 AM IST
./scripts/start_tetris.sh

# During market hours live monitoring
./scripts/watch_tetris.sh

# Evening shutdown, retrain, backup
./scripts/stop_tetris.sh
```

### Docker Management

```bash
# View live logs from all services
docker-compose logs -f

# View logs from a specific service
docker-compose logs -f trading_bot_main

# Restart a specific service
docker-compose restart trading_bot_api

# Stop all services
docker-compose down

# Rebuild after code changes
docker-compose up -d --build
```

### Manual Model Retraining

```bash
# Retrain all models manually
docker exec trading_bot_main python src/models/trainer.py --full-retrain

# Run backtests
docker exec trading_bot_main python src/backtest/engine.py --strategy all
```

### Running Tests

```bash
# Full test suite
docker-compose run --rm trading_bot_main pytest tests/ -v

# With coverage report
docker-compose run --rm trading_bot_main pytest tests/ --cov=src --cov-report=term-missing
```

---

## API Endpoints

Base URL: `http://localhost:8502/api`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/status` | System health, uptime, service status |
| `GET` | `/positions` | Live open positions with P&L |
| `GET` | `/signals` | Active trading signals with confidence scores |
| `GET` | `/eod/predictions` | Next day predictions for 50 Nifty stocks |
| `GET` | `/eod/watchlist` | Ranked watchlist with signal filters |
| `GET` | `/eod/patterns` | Candlestick pattern detections |
| `GET` | `/eod/accuracy` | Historical model prediction accuracy |
| `GET` | `/regime` | Market regime (trend, volatility, VIX context) |
| `GET` | `/alerts` | Recent system and trading alerts |
| `GET` | `/performance` | P&L curves, Sharpe, drawdown metrics |
| `GET` | `/options/sentiment` | Options chain sentiment analysis |
| `POST` | `/trading/pause` | Manually pause trading (circuit breaker) |

**Example request:**

```bash
curl http://localhost:8502/api/status
```

```json
{
  "status": "active",
  "uptime": "6h 23m",
  "market_open": true,
  "positions": 3,
  "daily_pnl": 1842.50,
  "paper_trading": true
}
```

---

## Dashboard

Access at **`http://localhost:8502`** · Streamlit backup at **`http://localhost:8501`**

| Tab | Content |
|---|---|
| **Live Trading** | Real time positions, live P&L, active signals, order book |
| **EOD Predictions** | 50 stocks with confidence bars, directional signals, filters |
| **Watchlist & Patterns** | Ranked watchlist, candlestick pattern detection |
| **Regime & Context** | Market trend, VIX, sector rotation, global macro context |
| **Intraday Scanner** | Tiered alerts volume spikes, breakouts, RSI extremes |
| **Performance** | Equity curves, model accuracy, strategy level analytics |

---

## Risk Management

Every signal clears a full risk waterfall before execution:

```
┌───────────────────────────────────────────────────────┐
│                   RISK WATERFALL                      │
│                                                       │
│  1. Microstructure Filter  ← Order book validation    │
│  2. Correlation Check      ← Reject if r > 0.85       │
│  3. Sector Limit           ← Max 2 per sector         │
│  4. Daily Loss Limit       ← Halt at 2% capital       │
│  5. Intraday Drawdown      ← Halt at 5% drawdown      │
│  6. Circuit Breaker        ← 3 rejects → 10 min pause │
│  7. Kelly Sizing           ← Half-Kelly, 1% risk/trade│
│  8. ATR Stop Loss          ← Trailing, auto-adjusted  │
│  9. Symbol Cooldown        ← Lockout after any exit   │
└───────────────────────────────────────────────────────┘
```

| Parameter | Value |
|---|---|
| Max risk per trade | 1% of capital (Half-Kelly) |
| Stop loss type | ATR-based with trailing logic |
| Max sector concentration | 2 positions per sector |
| Correlation rejection threshold | r > 0.85 |
| Circuit breaker trigger | 3 consecutive signal rejections |
| Circuit breaker cooldown | 10 minutes |
| Daily loss limit | 2% of total capital |
| Intraday drawdown halt | 5% |

---

## ML Models

| Model | Algorithms | Features | Validation Strategy |
|---|---|---|---|
| **Intraday (60-min)** | RF + XGBoost + LSTM · Optuna-tuned | 30+ technical indicators, microstructure depth | Purged walk forward CV with embargo gaps |
| **EOD (Daily)** | RF + XGBoost Classifier | 35+ daily + market-relative features | Walk-forward with strict lookahead prevention |

**Feature categories:**

```
Technical Indicators  →  RSI, MACD, Bollinger Bands, ATR, EMA, VWAP, Stochastic
Microstructure        →  Bid-ask spread, order book imbalance, depth ratio
Market-Relative       →  Nifty-relative returns, sector performance, beta
Volume Features       →  VWAP deviation, volume z-score, unusual volume flags
Price Action          →  Higher highs/lows, support/resistance proximity
Temporal              →  Time-of-day, day-of-week, expiry proximity
```

---

## 🗺️ Future Roadmap

- [ ] **Options Strategy Layer** delta-neutral spreads, iron condors
- [ ] **Paper Trading UI** simulated P&L with order replay
- [ ] **Multi-Broker Support** Fyers, Angel One, Upstox
- [ ] **Earnings Catalyst Scanner** NLP-powered event detection
- [ ] **Backtesting UI** parameter sweep visualization with equity curves
- [ ] **Regime-Adaptive Sizing** volatility scaled position sizes
- [ ] **Cloud Deployment** AWS/GCP with automated market-hours scaling
- [ ] **Portfolio Optimizer** mean-variance + Black-Litterman allocation

---

## Contributing

Contributions, issues, and feature requests are welcome!

```bash
# 1. Fork the repository
# 2. Create your feature branch
git checkout -b feature/your-feature-name

# 3. Commit your changes
git commit -m "feat: add your feature description"

# 4. Push to your branch
git push origin feature/your-feature-name

# 5. Open a Pull Request
```

**Commit convention:** `feat:`, `fix:`, `docs:`, `refactor:`, `test:`

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for full terms.

---

## Author

<div align="center">

**Muhammed Rashid A T**

[![GitHub](https://img.shields.io/badge/GitHub-raashxi-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/raashxi)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://linkedin.com/in/raashxi)

*Built with precision for the Indian markets.*

</div>

---

## Disclaimer

> **This software is provided strictly for educational and research purposes only.**
>
> Algorithmic trading involves substantial risk of financial loss. Past performance of any strategy backtested or live does not guarantee future results. This system is currently configured for **paper trading only** and has not been validated for live capital deployment.
>
> The author assumes no responsibility for financial decisions made using this software. Always validate thoroughly in paper trading mode before considering live deployment. **Trade at your own risk.**

---

<div align="center">

**If TETRIS helped you, please consider giving it a ⭐**

[![Star this repo](https://img.shields.io/github/stars/raashxi/tetris-trading-system?style=social)](https://github.com/raashxi/tetris-trading-system)

*Built for the Indian markets*

</div>
