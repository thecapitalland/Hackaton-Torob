"""Export committed Pydantic JSON schemas shared with the TypeScript client."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.decision import Decision  # noqa: E402
from app.main import ChatResponse  # noqa: E402


def schemas() -> dict[str, dict]:
    return {
        "decision.json": Decision.model_json_schema(),
        "chat-response.json": ChatResponse.model_json_schema(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if committed schemas are stale")
    args = parser.parse_args()
    out_dir = ROOT / "shared" / "schemas"
    out_dir.mkdir(parents=True, exist_ok=True)
    stale = []
    for name, schema in schemas().items():
        rendered = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        path = out_dir / name
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != rendered:
                stale.append(name)
        else:
            path.write_text(rendered, encoding="utf-8")
    if stale:
        print("Stale shared schemas: " + ", ".join(stale))
        print("Run: python backend/scripts/export_schemas.py")
        return 1
    if not args.check:
        print(f"Exported {len(schemas())} schemas to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
