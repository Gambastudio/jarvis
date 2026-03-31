"""Voice-specific hooks for the Agent SDK.

Hooks intercept agent behavior at key points: before/after tool use,
on stop, etc. Voice agents need specific hooks for logging, cost tracking,
and potentially voice-based confirmation of destructive actions.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("jarvis")


async def log_tool_usage(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: Any,
) -> dict[str, Any]:
    """Log every tool invocation for transparency."""
    tool_name = input_data.get("tool_name", "unknown")
    tool_input = input_data.get("tool_input", {})
    log.info(f"Tool: {tool_name} | Input: {str(tool_input)[:100]}")
    return {}


async def block_dangerous_bash(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: Any,
) -> dict[str, Any]:
    """Block dangerous bash commands (rm -rf, etc.)."""
    if input_data.get("tool_name") != "Bash":
        return {}

    command = input_data.get("tool_input", {}).get("command", "")
    dangerous_patterns = ["rm -rf /", "rm -rf ~", "mkfs", "> /dev/", "dd if="]

    for pattern in dangerous_patterns:
        if pattern in command:
            log.warning(f"Blocked dangerous command: {command[:50]}")
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"Dangerous command blocked: {pattern}",
                }
            }
    return {}
