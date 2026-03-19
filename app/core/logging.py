import json
import logging
from datetime import datetime, timezone
from typing import Any


logger = logging.getLogger("teabuy")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


def log_event(level: str, **fields: Any) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **fields,
    }
    message = json.dumps(payload, ensure_ascii=False, default=str)
    fn = getattr(logger, level, logger.info)
    fn(message)
