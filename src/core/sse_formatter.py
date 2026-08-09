import json
from typing import Any


def format_sse_event(event: str, data: Any) -> str:
    """Serialize a payload into a valid SSE frame."""

    event_name = event.strip() or "message"
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event_name}\ndata: {payload}\n\n"
