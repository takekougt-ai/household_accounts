"""Categorize merchant names into household-spending categories via Gemini.

Rule-based pre-filtering handles ~80% of transactions locally; only
unmatched names are sent to the Gemini API.
"""

import json
import time
from typing import List, Optional

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from categories import CATEGORIES
from config import GEMINI_API_KEY, GEMINI_MODEL

_client = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY or None)
    return _client


_RESPONSE_SCHEMA = types.Schema(
    type=types.Type.ARRAY,
    items=types.Schema(type=types.Type.STRING, enum=CATEGORIES),
)

_SYSTEM_INSTRUCTION = (
    "あなたは家計簿アプリのカテゴライズ担当です。"
    "各利用店舗名を、次のカテゴリのいずれか一つに分類してください: "
    f"{', '.join(CATEGORIES)}。"
    "判断に迷う場合は「その他」を選んでください。"
    "出力は入力と同じ順序・同じ件数のJSON配列にしてください。"
)

_BATCH_SIZE = 200

# Keyword rules applied before calling the API.
# Checked in order; first match wins. Keywords are substring-matched.
_RULES: list[tuple[list[str], str]] = [
    # その他: payment method placeholders and card meta-charges
    (["クイックペイプラス", "前回分口座振替", "年会費", "消費税", "決済手数料",
      "楽天ペイ", "メルカリ"], "その他"),
    # 交通
    (["スマートＥＸ", "ＪＲ東日本", "ＪＲ東海", "ＪＲ西日本", "Ｓｕｉｃａ",
      "えきねっと", "スカイライナー", "RYDE PASS", "RYDEPASS",
      "バス", "タクシー", "飛鳥交通", "宝交通", "HUI CAR",
      "CHARGESPOT", "EXIMBAY", "TMONEY"], "交通"),
    # サブスク
    (["Ｎｅｔｆｌｉｘ", "Netflix", "GOOGLE ONE", "GOOGLE *GOOGLE",
      "Ａｐｐｌｅ　ｉＴｕｎｅｓ", "iTunes", "ソフトバンクＭ",
      "ANTHROPIC", "CLAUDE", "DISNEY PLUS", "Disney Plus",
      "ネイティブキャンプ", "TRANSATEL", "UBIGI",
      "ちょこＺＡＰ", "chocoZAP", "STATION WORK", "テレキュ",
      "ITX JAPAN"], "サブスク"),
    # 食費: convenience stores, cafes, restaurants
    (["ファミリーマート", "セブンイレブン", "ローソン", "デイリーヤマザキ",
      "まいばすけっと", "マルエツ", "スターバックス", "マクドナルド",
      "すき家", "松屋", "吉野家", "タリーズ", "ドトール", "バーガーキング",
      "UBER EATS", "UBEREATS", "UBERDIRECT", "DOMINO", "ドミノ",
      "社食", "モンスーン", "ジョナサン", "ＨＵＢ", "笑笑", "和民",
      "うどん", "ラーメン", "焼肉", "居酒屋", "食堂", "レストラン",
      "ビストロ", "コーヒー", "COFFEE", "カフェ", "コカ・コーラ",
      "breadworks", "AMAMERIA", "一番どり", "壱角家", "らぁ麺",
      "おにやんま", "カレー", "やきとり", "飲食"], "食費"),
    # 日用品
    (["マツモトキヨシ", "ドン　キホーテ", "ドンキホーテ", "薬局",
      "クリーニング", "ドラッグ"], "日用品"),
    # 交際費
    (["カラオケ", "野球場", "ディズニー", "Disney", "ライブ",
      "ドームショップ", "下北沢ＥＲＡ"], "交際費"),
    # 旅行
    (["ホテル", "HOTEL", "RESORT", "リゾート", "Ｔｒｉｐ．ｃｏｍ",
      "Trip.com", "空港", "AIRPORT"], "旅行"),
]


def _rule_categorize(name: str) -> Optional[str]:
    """Return a category by keyword rule, or None if no rule matches."""
    for keywords, category in _RULES:
        if any(kw in name for kw in keywords):
            return category
    return None


def _call_gemini(merchant_names: List[str]) -> List[str]:
    """Call Gemini API to categorize a list of merchant names."""
    results: List[str] = []
    client = _get_client()

    for start in range(0, len(merchant_names), _BATCH_SIZE):
        chunk = merchant_names[start : start + _BATCH_SIZE]
        numbered = "\n".join(f"{i + 1}. {name}" for i, name in enumerate(chunk))

        for attempt in range(4):
            try:
                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=numbered,
                    config=types.GenerateContentConfig(
                        system_instruction=_SYSTEM_INSTRUCTION,
                        response_mime_type="application/json",
                        response_schema=_RESPONSE_SCHEMA,
                    ),
                )
                break
            except genai_errors.ClientError as e:
                if e.status_code == 429 and attempt < 3:
                    wait = 30 * (2 ** attempt)
                    print(f"Rate limited, retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    raise

        chunk_categories = json.loads(response.text)

        if len(chunk_categories) < len(chunk):
            chunk_categories += ["その他"] * (len(chunk) - len(chunk_categories))
        elif len(chunk_categories) > len(chunk):
            chunk_categories = chunk_categories[: len(chunk)]

        results.extend(chunk_categories)

    return results


def categorize_batch(merchant_names: List[str]) -> List[str]:
    """Return one category from CATEGORIES for each merchant name, in order.

    Applies keyword rules first; only unmatched names are sent to Gemini.
    """
    if not merchant_names:
        return []

    rule_results = [_rule_categorize(name) for name in merchant_names]

    gemini_indices = [i for i, cat in enumerate(rule_results) if cat is None]
    rule_count = len(merchant_names) - len(gemini_indices)
    print(f"Rules matched {rule_count}/{len(merchant_names)} merchants; "
          f"sending {len(gemini_indices)} to Gemini")

    if gemini_indices:
        gemini_names = [merchant_names[i] for i in gemini_indices]
        gemini_cats = _call_gemini(gemini_names)
        for idx, cat in zip(gemini_indices, gemini_cats):
            rule_results[idx] = cat

    return rule_results  # type: ignore[return-value]
