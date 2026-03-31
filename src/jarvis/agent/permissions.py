"""Permission management for voice-controlled tool access.

Ported from Jarvis4Gamba claude_bridge.py BLOCKED_TOOLS concept.
Now uses the Agent SDK native disallowed_tools + can_use_tool callback.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("jarvis")

# Default disallowed tools — write/delete/modify operations on MCP servers.
# These require explicit voice confirmation before execution.
DEFAULT_DISALLOWED_TOOLS: list[str] = [
    # Datto RMM — block all write operations
    "mcp__datto-rmm__create-*",
    "mcp__datto-rmm__delete-*",
    "mcp__datto-rmm__update-*",
    "mcp__datto-rmm__move-*",
    "mcp__datto-rmm__set-*",
    "mcp__datto-rmm__resolve-*",
    # Filesystem — block write operations
    "mcp__filesystem__create_directory",
    "mcp__filesystem__edit_file",
    "mcp__filesystem__move_file",
    "mcp__filesystem__write_file",
]

# Default allowed tools — read-only operations
DEFAULT_ALLOWED_TOOLS: list[str] = [
    "Read",
    "Glob",
    "Grep",
    "WebSearch",
    "WebFetch",
]


async def voice_permission_handler(
    tool_name: str,
    input_data: dict[str, Any],
    context: Any,
) -> dict[str, Any]:
    """Permission callback that could request voice confirmation for risky tools.

    This is a placeholder for the full voice-confirmation flow.
    In the MVP, we rely on allowed_tools/disallowed_tools instead.
    """
    # Check if this is a destructive operation
    destructive_keywords = ["delete", "create", "update", "move", "write", "remove"]
    is_destructive = any(kw in tool_name.lower() for kw in destructive_keywords)

    if is_destructive:
        log.warning(f"Destructive tool blocked: {tool_name}")
        return {
            "behavior": "deny",
            "message": f"Tool '{tool_name}' requires explicit permission.",
        }

    return {"behavior": "allow", "updated_input": input_data}
