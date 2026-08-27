"""Categorize merchant names into household-spending categories via Claude."""

from typing import List

import anthropic

from categories import CATEGORIES
from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY or None)
    return _client

_CATEGORIZE_TOOL = {
    "name": "categorize_transactions",
    "description": "Assign one household-spending category to each merchant, in the same order given.",
    "input_schema": {
        "type": "object",
        "properties": {
            "categories": {
                "type": "array",
                "items": {"type": "string", "enum": CATEGORIES},
                "description": "One category per input merchant, same order and length as the input list.",
            }
        },
        "required": ["categories"],
        "additionalProperties": False,
    },
    "strict": True,
}

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

        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=4096,
            system=(
                "あなたは家計簿アプリのカテゴライズ担当です。"
                "各利用店舗名を、次のカテゴリのいずれか一つに分類してください: "
                f"{', '.join(CATEGORIES)}。"
                "判断に迷う場合は「その他」を選んでください。"
            ),
            tools=[_CATEGORIZE_TOOL],
            tool_choice={"type": "tool", "name": "categorize_transactions"},
            messages=[{"role": "user", "content": numbered}],
        )

        tool_use = next(b for b in response.content if b.type == "tool_use")
        chunk_categories = tool_use.input["categories"]

        if len(chunk_categories) != len(chunk):
            raise ValueError(
                f"Model returned {len(chunk_categories)} categories for {len(chunk)} merchants"
            )

        results.extend(chunk_categories)

    return results
