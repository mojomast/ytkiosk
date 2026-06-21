#!/usr/bin/env python3

"""Compatibility launcher for the packaged YTKiosk legacy app.

The implementation now lives in ``src/ytkiosk/legacy.py``. This file remains so
existing desktop shortcuts, tests, and direct invocations continue to work.
"""

from __future__ import annotations

import sys
from importlib import reload
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ytkiosk import legacy as _legacy  # noqa: E402

_legacy = reload(_legacy)


for _name in dir(_legacy):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_legacy, _name)


if __name__ == "__main__":
    raise SystemExit(_legacy.main())
