-- BigQuery schema for the Amex dashboard automation project.
-- Run with: bq query --use_legacy_sql=false < sql/create_tables.sql
-- (replace ${PROJECT}/${DATASET} or run via `envsubst` / `bq` with -DPROJECT etc.
--  substituted beforehand; kept as literal placeholders here for clarity.)

CREATE SCHEMA IF NOT EXISTS `household_accounts`;

CREATE TABLE IF NOT EXISTS `household_accounts.amex_transactions` (
  transaction_id  STRING    NOT NULL,  -- dedup key: hash(date, merchant, amount, source)
  transaction_date DATE,
  amount          FLOAT64,
  merchant_name   STRING,
  category        STRING,              -- assigned by Claude API
  raw_category    STRING,              -- original MoneyForward category, if any
  source          STRING,              -- 'moneyforward' or 'csv_import'
  created_at      TIMESTAMP
)
PARTITION BY transaction_date
CLUSTER BY category, source;
