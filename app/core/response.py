from typing import Any

from app.core.request_context import get_request_id


def ok(data: Any):
    return {"code": 0, "message": "ok", "data": data, "requestId": get_request_id()}
