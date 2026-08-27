"""Write transaction rows to BigQuery, de-duplicated by transaction_id.

BigQuery has no native upsert-on-insert, so new rows are loaded into a
temporary staging table and merged into the main table with a MERGE
statement keyed on transaction_id.
"""

import uuid
from typing import List

from google.cloud import bigquery

from config import BQ_DATASET, BQ_TABLE, GCP_PROJECT_ID

_SCHEMA = [
    bigquery.SchemaField("transaction_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("transaction_date", "DATE"),
    bigquery.SchemaField("amount", "FLOAT64"),
    bigquery.SchemaField("merchant_name", "STRING"),
    bigquery.SchemaField("category", "STRING"),
    bigquery.SchemaField("raw_category", "STRING"),
    bigquery.SchemaField("source", "STRING"),
    bigquery.SchemaField("created_at", "TIMESTAMP"),
]

_COLUMNS = [field.name for field in _SCHEMA]


def build_merge_query(target_table: str, staging_table: str) -> str:
    """Build the MERGE statement that upserts staging_table into target_table."""
    update_cols = [c for c in _COLUMNS if c != "transaction_id"]
    update_clause = ", ".join(f"{c} = S.{c}" for c in update_cols)
    insert_cols = ", ".join(_COLUMNS)
    insert_values = ", ".join(f"S.{c}" for c in _COLUMNS)

    return f"""
        MERGE `{target_table}` T
        USING `{staging_table}` S
        ON T.transaction_id = S.transaction_id
        WHEN MATCHED THEN
          UPDATE SET {update_clause}
        WHEN NOT MATCHED THEN
          INSERT ({insert_cols})
          VALUES ({insert_values})
    """


def upsert_transactions(rows: List[dict]) -> None:
    """Upsert transaction rows into the amex_transactions table."""
    if not rows:
        return

    client = bigquery.Client(project=GCP_PROJECT_ID or None)
    dataset_ref = f"{client.project}.{BQ_DATASET}"
    target_table = f"{dataset_ref}.{BQ_TABLE}"
    staging_table = f"{dataset_ref}._staging_{BQ_TABLE}_{uuid.uuid4().hex[:8]}"

    job_config = bigquery.LoadJobConfig(
        schema=_SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    load_job = client.load_table_from_json(rows, staging_table, job_config=job_config)
    load_job.result()

    try:
        client.query(build_merge_query(target_table, staging_table)).result()
    finally:
        client.delete_table(staging_table, not_found_ok=True)
