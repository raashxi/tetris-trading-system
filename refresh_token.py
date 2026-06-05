"""Standalone token refresh - run this once per day."""
import sys
sys.path.insert(0, '/app/src')
from auth.session import daily_token_refresh
success = daily_token_refresh()
print("SUCCESS" if success else "FAILED")
