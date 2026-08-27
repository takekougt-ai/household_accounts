"""Cloud Functions (Gen2, HTTP-triggered) entry point.

Wired to Cloud Scheduler via an HTTP trigger (see deploy/deploy.sh):
fetch the last few days of MoneyForward transactions, categorize them
with Claude, and upsert into BigQuery.
"""

import logging
from datetime import date, timedelta

import functions_framework

from categorize import categorize_batch
from fetch_moneyforward import fetch_transactions
from write_bigquery import upsert_transactions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MoneyForward's own web UI lags a day or two behind card issuers in
# posting transactions, so re-fetching a short trailing window each run
# (rather than just "yesterday") catches anything that posted late.
# The BigQuery MERGE makes re-fetching already-seen rows a no-op.
LOOKBACK_DAYS = 7


@functions_framework.http
def sync_amex_transactions(request):
    end_date = date.today()
    start_date = end_date - timedelta(days=LOOKBACK_DAYS)

    logger.info("Fetching MoneyForward transactions from %s to %s", start_date, end_date)
    rows = fetch_transactions(start_date, end_date)
    logger.info("Fetched %d transactions", len(rows))

    if not rows:
        return {"status": "ok", "transactions": 0}, 200

    categories = categorize_batch([row["merchant_name"] for row in rows])
    for row, category in zip(rows, categories):
        row["category"] = category

    upsert_transactions(rows)
    logger.info("Upserted %d transactions into BigQuery", len(rows))

    return {"status": "ok", "transactions": len(rows)}, 200
