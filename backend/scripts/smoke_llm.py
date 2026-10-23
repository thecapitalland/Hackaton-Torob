"""Check configured OpenAI-compatible endpoint/models without probing other hosts.

    python backend/scripts/smoke_llm.py

The API key is sent only to ``BOXAPI_BASE_URL`` as configured in the environment.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm import get_client  # noqa: E402

def main() -> int:
    client = get_client()
    if not client.api_key:
        print("BOXAPI_API_KEY is not set - nothing to test.")
        return 1

    # Never probe alternate hosts: credentials are sent only to the configured
    # BOXAPI_BASE_URL (which may be OpenRouter or another compatible provider).
    for model in dict.fromkeys([client.model, client.fallback_model]):
        result = client.chat_json(
            [
                {"role": "system", "content": "فقط یک JSON برگردان: {\"ok\": true}"},
                {"role": "user", "content": "سلام"},
            ],
            model=model,
        )
        if result:
            print(f"OK   base_url={client.base_url}  model={model}  -> {result}")
        else:
            print(f"FAIL base_url={client.base_url}  model={model}")
    print()
    print("Recommended .env values:")
    print(f"BOXAPI_BASE_URL={client.base_url}")
    print(f"LLM_MODEL={client.model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
