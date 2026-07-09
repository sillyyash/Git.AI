from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)


def log_ai_event(event: Dict[str, Any], prefix: str = "ai_request") -> str:
    """Write an AI request event to the repo logs directory."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    filename = LOGS_DIR / f"{prefix}_{timestamp}.json"
    filename.write_text(json.dumps(event, indent=2, sort_keys=True), encoding="utf-8")
    return str(filename)
