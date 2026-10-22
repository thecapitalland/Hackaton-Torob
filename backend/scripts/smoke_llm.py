"""Check which BoxAPI base URL works and which model answers.

    python backend/scripts/smoke_llm.py

Prints the working base URL / model so it can be copied into `.env`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm import get_client  # noqa: E402

BASE_URLS = [
    os.environ.get("BOXAPI_BASE_URL", "https://ai.boxapi.ir/api/v1"),
    "https://ai.boxapi.ir/api/v1",
    "https://ai.boxapi.ir/ai/v1",
]

MODELS = [
    os.environ.get("LLM_MODEL", "gpt-5-mini"),
    os.environ.get("LLM_MODEL_FALLBACK", "gpt-5.4-mini"),
    "gpt-4o-mini",
]


def main() -> int:
    client = get_client()
    if not client.api_key:
        print("BOXAPI_API_KEY is not set - nothing to test.")
        return 1

    for base_url in dict.fromkeys(BASE_URLS):
        client.base_url = base_url
        for model in dict.fromkeys(MODELS):
            result = client.chat_json(
                [
                    {"role": "system", "content": "فقط یک JSON برگردان: {\"ok\": true}"},
                    {"role": "user", "content": "سلام"},
                ],
                model=model,
            )
            if result:
                print(f"OK   base_url={base_url}  model={model}  -> {result}")
            else:
                print(f"FAIL base_url={base_url}  model={model}")
    print()
    print("Recommended .env values:")
    print(f"BOXAPI_BASE_URL={client.base_url}")
    print(f"LLM_MODEL={client.model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
