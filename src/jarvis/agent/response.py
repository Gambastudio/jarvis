"""Response routing — decide how to present agent output to the user."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import Enum

log = logging.getLogger("jarvis")


class ResponseType(Enum):
    SPEAK = "speak"
    ACTION_CONFIRM = "action_confirm"
    DATA_DISPLAY = "data_display"
    ERROR = "error"


@dataclass
class JarvisResponse:
    """Parsed agent response with routing information."""

    response_type: ResponseType
    spoken_text: str
    display_data: dict | None = None
    actions_taken: list[str] | None = None
    raw: str = ""


def parse_response(text: str) -> JarvisResponse:
    """Parse agent response into a structured JarvisResponse.

    Tries to parse as JSON (structured output), falls back to plain text.
    """
    # Try structured JSON output
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "response_type" in data:
            return JarvisResponse(
                response_type=ResponseType(data["response_type"]),
                spoken_text=data.get("spoken_text", text),
                display_data=data.get("display_data"),
                actions_taken=data.get("actions_taken"),
                raw=text,
            )
    except (json.JSONDecodeError, ValueError, KeyError):
        pass

    # Plain text response — just speak it
    return JarvisResponse(
        response_type=ResponseType.SPEAK,
        spoken_text=text,
        raw=text,
    )
