"""Telegram alerting module for critical notifications."""
from __future__ import annotations

import os

import requests
from loguru import logger


class Alerter:
    """Send alerts via Telegram bot."""

    def __init__(self) -> None:
        self.bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        self.enabled = bool(self.bot_token and self.chat_id)
        if not self.enabled:
            logger.warning("Telegram alerts disabled (missing token or chat_id)")

    def send(self, message: str, priority: str = "normal") -> bool:
        """Send a Telegram message."""
        if not self.enabled:
            return False
        
        if priority == "high":
            message = f"🔴 {message}"
        
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"}
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info(f"Alert sent: {message[:50]}...")
                return True
            else:
                logger.error(f"Telegram error: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")
            return False