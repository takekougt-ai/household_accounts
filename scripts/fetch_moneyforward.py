"""Fetch recent Amex transactions from MoneyForward ME (unofficial, personal use).

MoneyForward ME has no public API for individual accounts (only for
corporate/business plans), so this scrapes the authenticated web session
the same way a browser would: log in, then download the household-ledger
CSV export that MoneyForward ME already offers as a built-in feature.

IMPORTANT -- this is inherently fragile:
  - MoneyForward's login flow, CSRF token placement, and CSV export URL
    have changed before and can change again without notice.
  - Verify each step against the live site (open devtools -> Network tab,
    log in and export a CSV by hand once) before relying on this in
    production, and expect to update the constants below over time.
  - Use only for your own account, at a reasonable polling frequency
    (this project runs it once/day via Cloud Scheduler) -- do not hammer
    the site or share scraped credentials/cookies.

The CSV export columns as of this writing (household ledger export):
    計算対象, 日付, 内容, 金額（円）, 保有金融機関, 大項目, 中項目, メモ, 振替, ID
"""

import io
from datetime import date
from typing import List, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup

from config import MONEYFORWARD_ACCOUNT_ID, MONEYFORWARD_EMAIL, MONEYFORWARD_PASSWORD
from transaction_utils import build_row

SIGN_IN_URL = "https://moneyforward.com/sign_in"
CSV_EXPORT_URL = "https://moneyforward.com/cf/csv"

_USER_AGENT = "Mozilla/5.0 (compatible; household-accounts-sync/1.0)"


def _login(session: requests.Session) -> None:
    resp = session.get(SIGN_IN_URL, headers={"User-Agent": _USER_AGENT})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    token_tag = soup.find("meta", attrs={"name": "csrf-token"})
    if token_tag is None:
        raise RuntimeError(
            "Could not find CSRF token on the MoneyForward sign-in page. "
            "MoneyForward's login flow may have changed -- inspect the page manually."
        )
    csrf_token = token_tag["content"]

    login_resp = session.post(
        SIGN_IN_URL,
        data={
            "authenticity_token": csrf_token,
            "mfid_user[email]": MONEYFORWARD_EMAIL,
            "mfid_user[password]": MONEYFORWARD_PASSWORD,
        },
        headers={"User-Agent": _USER_AGENT},
    )
    login_resp.raise_for_status()

    if "sign_in" in login_resp.url:
        raise RuntimeError(
            "MoneyForward login failed -- check credentials, or the site may be "
            "requiring 2FA / showing a different login form than expected."
        )


def _download_csv(session: requests.Session, year: int, month: int) -> pd.DataFrame:
    resp = session.get(
        CSV_EXPORT_URL,
        params={"year": year, "month": month},
        headers={"User-Agent": _USER_AGENT},
    )
    resp.raise_for_status()
    return pd.read_csv(io.BytesIO(resp.content), encoding="cp932")


def fetch_transactions(start_date: date, end_date: date) -> List[dict]:
    """Fetch Amex transactions from MoneyForward ME between two dates (inclusive)."""
    session = requests.Session()
    _login(session)

    months = sorted({(d.year, d.month) for d in _month_starts(start_date, end_date)})

    frames = [_download_csv(session, year, month) for year, month in months]
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if df.empty:
        return []

    df["日付"] = pd.to_datetime(df["日付"]).dt.date
    df = df[(df["日付"] >= start_date) & (df["日付"] <= end_date)]

    if MONEYFORWARD_ACCOUNT_ID:
        df = df[df["保有金融機関"].str.contains(MONEYFORWARD_ACCOUNT_ID, na=False)]

    # 計算対象 == 0 means the user excluded the row from totals (e.g. a
    # transfer); skip those rather than double-counting money movement.
    if "計算対象" in df.columns:
        df = df[df["計算対象"] != 0]

    rows = [
        build_row(
            transaction_date=row.日付,
            merchant_name=str(row.内容).strip(),
            amount=float(row.__getattr__("金額（円）")),
            source="moneyforward",
            raw_category=str(row.中項目) if pd.notna(row.中項目) else None,
        )
        for row in df.itertuples(index=False)
    ]
    return rows


def _month_starts(start_date: date, end_date: date):
    current = date(start_date.year, start_date.month, 1)
    while current <= end_date:
        yield current
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
