"""Zerodha Kite session manager with manual login flow."""
from __future__ import annotations

import os
import webbrowser
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs

import keyring
try:
    from kiteconnect import KiteConnect
except Exception:  # pragma: no cover - allows local tests without Kite package.
    KiteConnect = None
from loguru import logger

from src.monitoring.alerter import Alerter


class KiteSessionManager:
    """Manages Zerodha Kite Connect authentication and token lifecycle."""

    def __init__(self) -> None:
        self.api_key = os.environ["KITE_API_KEY"]
        self.api_secret = os.environ["KITE_API_SECRET"]
        self.user_id = os.environ["KITE_USER_ID"]
        self.password = os.environ["KITE_PASSWORD"]
        if KiteConnect is None:
            raise RuntimeError("kiteconnect package is not installed")
        self.kite = KiteConnect(api_key=self.api_key)
        self.alerter = Alerter()
        self.token_file = Path("/home/botuser/.trading_bot/kite_token.txt")
        self.token_file.parent.mkdir(exist_ok=True)
        self.keyring_service = "trading_bot_zerodha"

    def _get_stored_token(self) -> Optional[str]:
        if self.token_file.exists():
            try:
                return self.token_file.read_text().strip()
            except Exception:
                pass
        try:
            token = keyring.get_password(self.keyring_service, self.user_id)
            if token:
                return token
        except Exception:
            pass
        return None

    def _store_token(self, token: str) -> None:
        try:
            self.token_file.write_text(token)
        except Exception as e:
            logger.warning(f"Could not write token file: {e}")
        try:
            keyring.set_password(self.keyring_service, self.user_id, token)
        except Exception as e:
            logger.warning(f"Could not store token in keyring: {e}")

    def _is_token_valid(self, token: str) -> bool:
        try:
            self.kite.set_access_token(token)
            profile = self.kite.profile()
            if profile and "user_id" in profile:
                logger.info(f"Token valid for user: {profile['user_name']}")
                return True
        except Exception as e:
            logger.debug(f"Token validation failed: {e}")
        return False

    def _manual_login_flow(self) -> str:
        login_url = self.kite.login_url()
        logger.info("Opening Kite login URL in browser...")
        webbrowser.open(login_url)
        
        print("\n" + "=" * 60)
        print("MANUAL AUTHENTICATION REQUIRED")
        print("=" * 60)
        print(f"Login URL: {login_url}")
        print("\n1. Log in with your Zerodha credentials")
        print("2. Enter your 2FA code if prompted")
        print("3. You'll be redirected to a URL like:")
        print("   http://127.0.0.1:6583/callback?request_token=XXXX&status=success")
        print("4. Copy the ENTIRE URL and paste it below")
        print("=" * 60)
        
        redirect_url = input("\nPaste redirect URL here: ").strip()
        parsed = urlparse(redirect_url)
        params = parse_qs(parsed.query)
        request_token = params.get("request_token", [None])[0]
        
        if not request_token:
            raise ValueError("Could not find request_token in URL")
        
        data = self.kite.generate_session(request_token, api_secret=self.api_secret)
        access_token = data["access_token"]
        logger.success("Successfully generated access token")
        return access_token

    def login(self, mode: str = "manual") -> bool:
        stored_token = self._get_stored_token()
        if stored_token and self._is_token_valid(stored_token):
            self.kite.set_access_token(stored_token)
            logger.info("Using existing valid token")
            return True
        
        logger.info("No valid token found. Starting login flow...")
        self.alerter.send("🔐 Trading Bot needs Kite authentication.")
        
        try:
            token = self._manual_login_flow()
            self._store_token(token)
            self.kite.set_access_token(token)
            self.alerter.send("✅ Kite authentication successful.")
            return True
        except Exception as e:
            logger.error(f"Login failed: {e}")
            self.alerter.send(f"❌ Kite login failed: {str(e)[:100]}")
            return False

    def refresh_if_needed(self) -> bool:
        if not self._get_stored_token():
            return self.login()
        token = self._get_stored_token()
        if self._is_token_valid(token):
            self.kite.set_access_token(token)
            return True
        else:
            logger.warning("Stored token expired. Re-authenticating...")
            return self.login()

    def get_kite_client(self) -> Optional[KiteConnect]:
        if self.kite.access_token:
            return self.kite
        if self.refresh_if_needed():
            return self.kite
        return None


_session_manager: Optional[KiteSessionManager] = None


def get_kite_session() -> Optional[KiteConnect]:
    global _session_manager
    if _session_manager is None:
        _session_manager = KiteSessionManager()
    return _session_manager.get_kite_client()


def daily_token_refresh() -> bool:
    manager = KiteSessionManager()
    return manager.refresh_if_needed()
