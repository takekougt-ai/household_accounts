"""Environment configuration shared by all scripts.

Loads from a local .env file when present (for local development); in
Cloud Functions, environment variables are injected directly and
python-dotenv's load_dotenv() is a no-op if no .env file exists.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
BQ_DATASET = os.environ.get("BQ_DATASET", "household_accounts")
BQ_TABLE = os.environ.get("BQ_TABLE", "amex_transactions")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

MONEYFORWARD_EMAIL = os.environ.get("MONEYFORWARD_EMAIL", "")
MONEYFORWARD_PASSWORD = os.environ.get("MONEYFORWARD_PASSWORD", "")
MONEYFORWARD_ACCOUNT_ID = os.environ.get("MONEYFORWARD_ACCOUNT_ID", "")
