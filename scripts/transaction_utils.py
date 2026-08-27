"""Shared helpers for building transaction rows destined for BigQuery."""

import hashlib
from datetime import date, datetime, timezone
from typing import Optional


def make_transaction_id(transaction_date: date, merchant_name: str, amount: float, source: str) -> str:
    """Deterministic dedup key.

    Amex CSV exports and MoneyForward's feed don't carry a stable
    transaction ID we can rely on across sources, so we derive one from
    the fields that uniquely identify a purchase in practice. This means
    two genuinely distinct purchases at the same merchant, for the same
    amount, on the same day, will collide and be treated as one row --
    acceptable for a personal household-accounts feed, and a rare edge
    case for Amex data.
    """
    key = f"{transaction_date.isoformat()}|{merchant_name.strip()}|{amount:.2f}|{source}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def build_row(
    transaction_date: date,
    merchant_name: str,
    amount: float,
    source: str,
    category: Optional[str] = None,
    raw_category: Optional[str] = None,
) -> dict:
    return {
        "transaction_id": make_transaction_id(transaction_date, merchant_name, amount, source),
        "transaction_date": transaction_date.isoformat(),
        "amount": amount,
        "merchant_name": merchant_name,
        "category": category,
        "raw_category": raw_category,
        "source": source,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
