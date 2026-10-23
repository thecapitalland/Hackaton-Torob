from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_committed_json_schemas_match_pydantic_models():
    result = subprocess.run(
        [sys.executable, str(ROOT / "backend" / "scripts" / "export_schemas.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
