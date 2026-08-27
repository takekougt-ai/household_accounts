# Amex ダッシュボード自動化

American Express の利用明細を自動取得・カテゴライズし、BigQuery に蓄積して
Tableau Public でダッシュボード化するパイプライン。

## アーキテクチャ

```
【初期データ投入（1回のみ）】
Amex CSV手動DL（過去24ヶ月） → import_csv.py → BigQuery

【継続データ取得（自動・毎日）】
MoneyForward ME → fetch_moneyforward.py
  → categorize.py（Claude API） → write_bigquery.py（MERGEでUPSERT）
  ← Cloud Scheduler → Cloud Functions（main.py）

【可視化】
Tableau Public ← BigQuery ネイティブコネクタ（マスク済みビュー経由）
```

## セットアップ

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # 値を編集
```

`.env` の各変数の意味は `.env.example` を参照。カテゴライズには
`ANTHROPIC_MODEL`（デフォルト `claude-haiku-4-5-20251001`）を使用する。
分類タスクは単純なので Haiku で十分かつ低コスト。

### BigQuery テーブル作成

```bash
bq query --use_legacy_sql=false < sql/create_tables.sql
```

### 初期データ投入（Amex CSV、過去24ヶ月分）

1. Amex マイアカウントで「ご利用明細」CSV をダウンロード（Shift-JIS/CP932）
2. `scripts/import_csv.py` の `COLUMN_MAP` を実際のヘッダー名に合わせて確認
   （Amex の CSV ヘッダーはカード種別・時期によって変わることがある）
3. 実行:
   ```bash
   python scripts/import_csv.py --file 202401_amex.csv --dry-run  # まず確認
   python scripts/import_csv.py --file 202401_amex.csv
   ```

### 継続取得（MoneyForward ME、ローカルで手動実行する場合）

```bash
python -c "
from datetime import date, timedelta
from fetch_moneyforward import fetch_transactions
from categorize import categorize_batch
from write_bigquery import upsert_transactions

rows = fetch_transactions(date.today() - timedelta(days=7), date.today())
cats = categorize_batch([r['merchant_name'] for r in rows])
for r, c in zip(rows, cats):
    r['category'] = c
upsert_transactions(rows)
"
```

**注意:** `fetch_moneyforward.py` は MoneyForward ME の非公式スクレイピングです。
ログインフロー・CSV エクスポートの URL は同サービスの仕様変更で壊れる可能性があるため、
`scripts/fetch_moneyforward.py` 冒頭のコメントを読み、実際のサイト挙動と照らして
検証・更新してください。個人利用の範囲でのみ使用すること。

### Cloud Functions + Cloud Scheduler へのデプロイ（自動実行）

```bash
export PROJECT_ID=your-gcp-project
export ANTHROPIC_API_KEY=sk-ant-xxxx
export MONEYFORWARD_EMAIL=you@example.com
export MONEYFORWARD_PASSWORD=xxxx
./deploy/deploy.sh
```

`deploy/deploy.sh` は以下を行う:
- 必要な GCP API の有効化
- BigQuery データセット/テーブル作成
- Cloud Functions（Gen2, HTTP トリガー）へ `scripts/main.py` をデプロイ
- Cloud Scheduler で毎日 6:00 (JST) に起動するジョブを作成/更新

デフォルトでは直近7日分を再取得して BigQuery に MERGE するため、
MoneyForward 側の反映遅延があっても取りこぼしにくい構成になっている
（`scripts/main.py` の `LOOKBACK_DAYS`）。

### Tableau Public への接続

Tableau Public はデータそのものが公開されるため、**生の `amex_transactions`
テーブルには接続しないこと**。まず個人情報をマスクしたビューを作成する:

```bash
bq query --use_legacy_sql=false < tableau/create_masked_view.sql
```

作成されるビュー:
- `v_monthly_category_summary` — 月×カテゴリの件数・合計金額のみ（個別取引・店舗名なし）
- `v_merchant_ranking` — 月×カテゴリ×店舗名（店舗名は末尾の店舗番号等を除去）の集計

Tableau Public の BigQuery コネクタでこれらのビューに接続し、以下を構築する:
- カテゴリ別支出（月次）
- 月次トレンド推移
- 前月比・前年同月比
- 店舗・サービス別ランキング

## ディレクトリ構成

```
sql/create_tables.sql         BigQuery データセット・テーブル定義
scripts/config.py             環境変数読み込み
scripts/categories.py         カテゴリ一覧（食費/交通/サブスク/交際費/日用品/旅行/その他）
scripts/transaction_utils.py  重複排除用IDの生成・行データ組み立て
scripts/import_csv.py         Amex CSV 初期投入（1回限り想定）
scripts/fetch_moneyforward.py MoneyForward ME からの明細取得（非公式）
scripts/categorize.py         Claude API によるカテゴライズ
scripts/write_bigquery.py     BigQuery への UPSERT（MERGE）
scripts/main.py               Cloud Functions エントリーポイント
deploy/deploy.sh              GCPへのデプロイスクリプト
tableau/create_masked_view.sql Tableau Public 用マスク済みビュー
tests/                        ユニットテスト（重複排除ロジック等）
```

## テスト

```bash
pip install pytest
pytest tests/
```

MoneyForward スクレイピングと BigQuery/Claude API 呼び出しは実サービスに
依存するため自動テスト対象外。ユニットテストは純粋なロジック
（重複排除キーの生成、MERGE クエリの組み立て）のみを検証する。

## 未決定事項 / 既知の制約

- MoneyForward の認証方式・CSV エクスポート URL は変更される可能性がある
  （`scripts/fetch_moneyforward.py` 参照）
- MoneyForward 無料プランは連携4件まで・閲覧1年まで
- Claude API のコストは明細数百行/月なら数円〜数十円程度
