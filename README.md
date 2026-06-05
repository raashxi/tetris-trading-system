# ⚡ TETRIS — Multi-Strategy AI Trading System

<div align="center">

Python 3.11
Docker
FastAPI
Redis
PyTorch
License: MIT

Production-grade algorithmic trading for the Indian stock market — ML ensembles, real-time risk management, and an institutional dashboard.

</div>

---

## 📑 Table of Contents

- Overview
- Features
- Architecture
- Tech Stack
- Project Structure
- Installation
- Usage
- API Endpoints
- Dashboard
- Risk Management
- Future Roadmap
- Contributing
- License
- Author

---

## 🔭 Overview

TETRIS is a fully autonomous trading system that runs four independent alpha strategies across NSE stocks, orchestrated through Docker microservices and protected by institutional-grade risk controls.

### 🎯 Strategies at a Glance

| Strategy | Type | Horizon |
|----------|------|----------|
| EOD Predictions | RF + XGBoost | Next Trading Day |
| 90-Minute Intraday ML | RF + XGBoost + LSTM | 90 Minutes |
| Mean Reversion | RSI + VWAP | 10-45 Minutes |
| Momentum | Return + RSI | Intraday Swing |

---

## ✨ Features

### 🤖 AI & Machine Learning

- Dual-horizon ML ensemble
- 65+ engineered features
- Walk-forward validation
- Confidence scoring
- Automated daily retraining

### 🛡️ Risk Management

- Half-Kelly position sizing
- ATR trailing stops
- Circuit breakers
- Daily loss limits
- Correlation limits

### 📊 Dashboard

- Real-time P&L
- Prediction tables
- Pattern detection
- Regime analysis
- Scanner alerts
- Telegram notifications

### 🏗️ Infrastructure

- Docker Compose microservices
- FastAPI backend
- Redis caching
- Automated backups
- PDF reporting

---

## 🏛️ Architecture

text ┌───────────────────────────────────────────────┐ │                 TETRIS SYSTEM                 │ ├───────────────────────────────────────────────┤ │ EOD Model     Intraday ML     Mean Reversion │ │ Momentum      Scanner         Order Filter   │ ├───────────────────────────────────────────────┤ │             Order Manager + Risk             │ ├───────────────────────────────────────────────┤ │              Paper Broker Layer              │ ├───────────────────────────────────────────────┤ │         Dashboard + API + Telegram           │ └───────────────────────────────────────────────┘ 

---

## 🛠️ Tech Stack

### Backend

- Python 3.11
- FastAPI
- Redis
- Docker
- Pandas
- NumPy

### Machine Learning

- Scikit-Learn
- XGBoost
- PyTorch
- Optuna

### Frontend

- Streamlit
- Chart.js
- HTML
- CSS
- JavaScript

---

## 📁 Project Structure

text tetris-trading-system/ ├── src/ │   ├── api/ │   ├── auth/ │   ├── backtest/ │   ├── data/ │   ├── features/ │   ├── models/ │   ├── monitoring/ │   ├── risk/ │   ├── scanner/ │   ├── scripts/ │   ├── strategies/ │   ├── trading/ │   └── main.py ├── config/ ├── docker/ ├── frontend/ ├── scripts/ ├── tests/ ├── .env.template ├── docker-compose.yml ├── requirements.txt └── README.md 

---

## ⚙️ Installation

### Prerequisites

- Docker Desktop
- Python 3.11
- Zerodha Kite Connect API
- Telegram Bot Token

### Clone Repository

bash git clone https://github.com/raashxi/tetris-trading-system.git cd tetris-trading-system 

### Configure Environment

bash cp .env.template .env nano .env 

Example:

env KITE_API_KEY=your_api_key KITE_API_SECRET=your_api_secret TELEGRAM_BOT_TOKEN=your_token TELEGRAM_CHAT_ID=your_chat_id TRADING_MODE=PAPER 

### Build & Start

bash docker-compose up -d --build 

---

## 🚀 Usage

bash # Morning startup ./start_tetris.sh  # Monitor system ./watch_tetris.sh  # Evening shutdown ./stop_tetris.sh 

### Dashboard

text http://localhost:8502 

### Streamlit Backup

text http://localhost:8501 

---

## 📡 API Endpoints

| Endpoint | Method | Description |
|-----------|---------|-------------|
| /api/status | GET | Bot status |
| /api/positions | GET | Open positions |
| /api/signals | GET | Recent signals |
| /api/eod/predictions | GET | Daily predictions |
| /api/performance | GET | Performance analytics |
| /api/alerts | GET | Scanner alerts |

---

## 📊 Dashboard

- Live Trading
- EOD Predictions
- Watchlists
- Pattern Detection
- Market Regime Analysis
- Performance Analytics

---

## 🛡️ Risk Management

| Layer | Rule |
|---------|---------|
| Position Limits | Max concurrent positions |
| Kelly Sizing | Risk-adjusted sizing |
| Stop Loss | ATR-based |
| Trailing Stop | Profit protection |
| Daily Loss Limit | Auto halt |
| Circuit Breaker | API failure protection |

---

## 🔮 Future Roadmap

- NSE options integration
- Direction-specific models
- Confidence calibration
- Dynamic position sizing
- AWS deployment
- Mobile Telegram commands
- Multi-symbol walk-forward testing

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch

bash git checkout -b feature/amazing-feature 

3. Commit your changes

bash git commit -m "Add amazing feature" 

4. Push changes

bash git push origin feature/amazing-feature 

5. Open a Pull Request

---

## 📜 License

Distributed under the MIT License.

---

## 👤 Author

Muhammed Rashid A T

GitHub: https://github.com/raashxi

---

## ⚠️ Disclaimer

This software is for educational and research purposes only.

Past performance does not guarantee future results. Trading involves risk and the authors assume no liability for financial losses.

---

<div align="center">

⭐ If you find this project useful, please consider giving it a star! ⭐