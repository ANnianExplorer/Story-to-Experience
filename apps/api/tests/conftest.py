"""Ensure the repository root is importable when this suite runs on its own."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for entry in (str(ROOT), str(ROOT / "apps" / "api")):
    if entry not in sys.path:
        sys.path.insert(0, entry)
