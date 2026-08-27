import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from write_bigquery import build_merge_query


def test_merge_query_matches_on_transaction_id():
    query = build_merge_query("proj.ds.amex_transactions", "proj.ds._staging_tmp")
    assert "ON T.transaction_id = S.transaction_id" in query


def test_merge_query_updates_all_non_key_columns():
    query = build_merge_query("proj.ds.amex_transactions", "proj.ds._staging_tmp")
    for col in ["transaction_date", "amount", "merchant_name", "category", "raw_category", "source", "created_at"]:
        assert f"{col} = S.{col}" in query
    assert "transaction_id = S.transaction_id" not in query.split("WHEN MATCHED")[1].split("WHEN NOT MATCHED")[0]


def test_merge_query_inserts_transaction_id_on_no_match():
    query = build_merge_query("proj.ds.amex_transactions", "proj.ds._staging_tmp")
    insert_clause = query.split("WHEN NOT MATCHED")[1]
    assert "transaction_id" in insert_clause
