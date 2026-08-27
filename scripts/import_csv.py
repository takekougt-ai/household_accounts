"""One-time initial load: import an Amex CSV export into BigQuery.

American Express Japan's "ご利用明細" CSV export has changed column
headers across card products and over the years, so the mapping below
is deliberately explicit rather than positional -- check your actual
export's header row with `python import_csv.py --file foo.csv --dry-run`
and adjust COLUMN_MAP if the names differ.

Usage:
    python import_csv.py --file 202401_amex.csv
    python import_csv.py --file 202401_amex.csv --dry-run   # parse only, no BigQuery write
"""

import argparse
import sys
from datetime import datetime

import pandas as pd

from categorize import categorize_batch
from transaction_utils import build_row
from write_bigquery import upsert_transactions

# Amex Japan's web CSV export typically uses these Japanese headers.
# Update the right-hand values if your export differs.
COLUMN_MAP = {
    "date": "ご利用日",
    "merchant": "ご利用内容",
    "amount": "金額",
}

# Amex Japan CSV exports are Shift-JIS (cp932) encoded.
CSV_ENCODING = "cp932"


def parse_amex_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, encoding=CSV_ENCODING, dtype=str)

    missing = [col for col in COLUMN_MAP.values() if col not in df.columns]
    if missing:
        raise ValueError(
            f"Expected columns not found in {path}: {missing}. "
            f"Actual columns: {list(df.columns)}. Update COLUMN_MAP in import_csv.py."
        )

    out = pd.DataFrame()
    out["transaction_date"] = pd.to_datetime(df[COLUMN_MAP["date"]], errors="coerce").dt.date
    out["merchant_name"] = df[COLUMN_MAP["merchant"]].str.strip()
    out["amount"] = (
        df[COLUMN_MAP["amount"]].str.replace(",", "", regex=False).str.replace("¥", "", regex=False).astype(float)
    )

    before = len(out)
    out = out.dropna(subset=["transaction_date", "merchant_name"])
    dropped = before - len(out)
    if dropped:
        print(f"Warning: dropped {dropped} row(s) with unparseable date/merchant", file=sys.stderr)

    return out


def main():
    parser = argparse.ArgumentParser(description="Import an Amex CSV export into BigQuery")
    parser.add_argument("--file", required=True, help="Path to the Amex CSV export")
    parser.add_argument("--dry-run", action="store_true", help="Parse and categorize only, skip the BigQuery write")
    args = parser.parse_args()

    df = parse_amex_csv(args.file)
    print(f"Parsed {len(df)} transactions from {args.file}")

    merchant_names = df["merchant_name"].tolist()
    categories = categorize_batch(merchant_names)

    rows = [
        build_row(
            transaction_date=row.transaction_date,
            merchant_name=row.merchant_name,
            amount=row.amount,
            source="csv_import",
            category=categories[i],
        )
        for i, row in enumerate(df.itertuples(index=False))
    ]

    if args.dry_run:
        print(f"Dry run: would write {len(rows)} rows. Sample: {rows[:3]}")
        return

    upsert_transactions(rows)
    print(f"Wrote {len(rows)} rows to BigQuery")


if __name__ == "__main__":
    main()
