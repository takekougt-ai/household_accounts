"""Categorize merchant names into household-spending categories via Gemini."""

import json
from typing import List

from google import genai
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

# Keep individual API calls small; a few hundred merchants per call stays
# well under the model's output budget and keeps a single bad row from
# invalidating a huge batch.
_BATCH_SIZE = 200


def categorize_batch(merchant_names: List[str]) -> List[str]:
    """Return one category from CATEGORIES for each merchant name, in order."""
    if not merchant_names:
        return []

    results: List[str] = []
    client = _get_client()

    for start in range(0, len(merchant_names), _BATCH_SIZE):
        chunk = merchant_names[start : start + _BATCH_SIZE]
        numbered = "\n".join(f"{i + 1}. {name}" for i, name in enumerate(chunk))

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=numbered,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=_RESPONSE_SCHEMA,
            ),
        )

        chunk_categories = json.loads(response.text)

        if len(chunk_categories) < len(chunk):
            raise ValueError(
                f"Model returned {len(chunk_categories)} categories for {len(chunk)} merchants"
            )
        if len(chunk_categories) > len(chunk):
            chunk_categories = chunk_categories[: len(chunk)]

        results.extend(chunk_categories)

    return results
