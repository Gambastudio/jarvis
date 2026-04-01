"""Claude Agent SDK integration — the brain of Jarvis.

Replaces the old `anthropic.Anthropic.messages.create()` call with the
full Agent SDK, giving Jarvis access to tools, MCP servers, sessions,
subagents, hooks, and structured output.
"""

from __future__ import annotations

import logging
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    query,
)

from jarvis.config import JarvisConfig
from jarvis.utils.cost_tracker import CostTracker
from jarvis.utils.text_cleaner import clean_for_speech

log = logging.getLogger("jarvis")


class JarvisAgent:
    """Wraps the Claude Agent SDK for voice-agent use cases."""

    def __init__(self, config: JarvisConfig) -> None:
        self.config = config
        self.cost_tracker = CostTracker()
        self._client: ClaudeSDKClient | None = None
        self._session_id: str | None = None

    def _build_options(self) -> ClaudeAgentOptions:
        """Build ClaudeAgentOptions from JarvisConfig."""
        opts = ClaudeAgentOptions(
            model=self.config.agent.model,
            max_turns=self.config.agent.max_turns,
            max_budget_usd=self.config.agent.max_budget_usd,
            permission_mode=self.config.agent.permission_mode,
            thinking=self.config.agent.thinking,
        )

        # System prompt from CLAUDE.md if it exists
        claude_md = Path.cwd() / "CLAUDE.md"
        if not claude_md.exists():
            claude_md = Path.cwd() / ".jarvis" / "CLAUDE.md"
        if claude_md.exists():
            opts.system_prompt = claude_md.read_text()

        # MCP servers
        if self.config.mcp_servers:
            opts.mcp_servers = self.config.mcp_servers

        # Tool permissions
        if self.config.allowed_tools:
            opts.allowed_tools = self.config.allowed_tools
        if self.config.disallowed_tools:
            opts.disallowed_tools = self.config.disallowed_tools

        # Load project settings (CLAUDE.md, skills, etc.)
        opts.setting_sources = ["project"]

        return opts

    async def ask(self, text: str) -> str:
        """Send a voice command to Claude and return the spoken response.

        Uses query() for stateless single interactions.
        """
        options = self._build_options()
        response_text = ""

        try:
            async for message in query(prompt=text, options=options):
                if isinstance(message, ResultMessage):
                    if message.subtype == "success" and message.result:
                        response_text = message.result
                    self.cost_tracker.record(message.total_cost_usd)
                    self._session_id = message.session_id
                    log.info(
                        f"Agent response ({message.duration_ms}ms, "
                        f"{message.num_turns} turns, "
                        rf"\${message.total_cost_usd or 0:.4f})"
                    )
        except Exception as e:
            log.error(f"Agent SDK error: {e}")
            return f"Entschuldigung, da gab es einen Fehler: {e}"

        return clean_for_speech(response_text)

    async def ask_with_session(self, text: str) -> str:
        """Send a voice command with session context (multi-turn).

        Uses ClaudeSDKClient to maintain conversation context.
        """
        if self._client is None:
            options = self._build_options()
            self._client = ClaudeSDKClient(options=options)
            await self._client.connect()

        response_text = ""
        try:
            await self._client.query(text)
            async for message in self._client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            response_text += block.text
                if isinstance(message, ResultMessage):
                    if message.subtype == "success" and message.result:
                        response_text = message.result
                    self.cost_tracker.record(message.total_cost_usd)
        except Exception as e:
            log.error(f"Agent SDK error: {e}")
            return f"Entschuldigung, da gab es einen Fehler: {e}"

        return clean_for_speech(response_text)

    async def reset_session(self) -> None:
        """End the current session and start fresh."""
        if self._client:
            await self._client.disconnect()
            self._client = None
        self._session_id = None
        log.info("Session reset")

    async def close(self) -> None:
        """Clean up resources."""
        await self.reset_session()
        log.info(f"Agent closed. {self.cost_tracker.summary()}")
