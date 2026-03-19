import time
import uuid

from fastapi import Request

from app.core.logging import log_event
from app.core.request_context import clear_actor, get_actor, set_request_id


async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    set_request_id(request_id)
    clear_actor()
    started = time.perf_counter()
    response = None
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        user_id, role = get_actor()
        log_event(
            "info",
            requestId=request_id,
            path=request.url.path,
            method=request.method,
            userId=user_id,
            role=role,
            statusCode=status_code,
            latencyMs=latency_ms,
        )
        if response is not None:
            response.headers["X-Request-Id"] = request_id
