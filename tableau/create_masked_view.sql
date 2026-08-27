-- Public-safe views for Tableau Public.
--
-- Tableau Public makes the *data*, not just the dashboard, publicly
-- downloadable. These views therefore never expose: transaction_id,
-- exact transaction_date (only year-month), or per-transaction amounts
-- (only aggregates) -- everything the dashboard needs (monthly category
-- breakdown, trend, MoM/YoY, merchant ranking) is derivable from
-- aggregates alone. Point Tableau's BigQuery connector at these views,
-- not at `amex_transactions` directly.

CREATE OR REPLACE VIEW `household_accounts.v_monthly_category_summary` AS
SELECT
  FORMAT_DATE('%Y-%m', transaction_date) AS year_month,
  category,
  COUNT(*) AS transaction_count,
  SUM(amount) AS total_amount
FROM `household_accounts.amex_transactions`
GROUP BY year_month, category;

-- Strips trailing store/branch numbers (e.g. "ampm 渋谷店１２３" -> "ampm 渋谷店")
-- so that individually-identifying branch codes don't leak, while keeping
-- the brand name useful for ranking.
CREATE OR REPLACE VIEW `household_accounts.v_merchant_ranking` AS
SELECT
  FORMAT_DATE('%Y-%m', transaction_date) AS year_month,
  category,
  REGEXP_REPLACE(merchant_name, r'[0-9０-９\-ー]+$', '') AS merchant_name_masked,
  COUNT(*) AS transaction_count,
  SUM(amount) AS total_amount
FROM `household_accounts.amex_transactions`
GROUP BY year_month, category, merchant_name_masked;
