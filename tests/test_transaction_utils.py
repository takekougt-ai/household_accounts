import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from transaction_utils import build_row, make_transaction_id


def test_transaction_id_is_deterministic():
    id1 = make_transaction_id(date(2024, 1, 15), "スターバックス 渋谷店", 550.0, "csv_import")
    id2 = make_transaction_id(date(2024, 1, 15), "スターバックス 渋谷店", 550.0, "csv_import")
    assert id1 == id2


def test_transaction_id_differs_by_source():
    common = (date(2024, 1, 15), "スターバックス 渋谷店", 550.0)
    id_csv = make_transaction_id(*common, "csv_import")
    id_mf = make_transaction_id(*common, "moneyforward")
    assert id_csv != id_mf


def test_transaction_id_ignores_merchant_whitespace():
    id1 = make_transaction_id(date(2024, 1, 15), "スターバックス", 550.0, "csv_import")
    id2 = make_transaction_id(date(2024, 1, 15), "  スターバックス  ", 550.0, "csv_import")
    assert id1 == id2


def test_build_row_contains_dedup_key_and_fields():
    row = build_row(date(2024, 1, 15), "コンビニ", 300.0, "csv_import", category="日用品")
    assert row["transaction_id"] == make_transaction_id(date(2024, 1, 15), "コンビニ", 300.0, "csv_import")
    assert row["transaction_date"] == "2024-01-15"
    assert row["category"] == "日用品"
    assert row["source"] == "csv_import"
