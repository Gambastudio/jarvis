"""Claude Agent SDK integration — the brain of Jarvis.

Runs a dedicated asyncio event loop in a background thread so the persistent
ClaudeSDKClient stays alive across calls without conflicting with the STT/TTS
event loops. All public methods are synchronous and thread-safe.
"""

from __future__ import annotations

import asyncio
import getpass
import logging
import socket
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)
from claude_agent_sdk.types import (
    PermissionResult,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

from jarvis.config import JarvisConfig
from jarvis.utils.cost_tracker import CostTracker
from jarvis.utils.text_cleaner import clean_for_speech

log = logging.getLogger("jarvis")


    # Human-readable names for common SDK tools
_TOOL_LABELS: dict[str, str] = {
    "Bash": "Führt Befehl aus",
    "Read": "Liest Datei",
    "Write": "Schreibt Datei",
    "Edit": "Bearbeitet Datei",
    "Glob": "Sucht Dateien",
    "Grep": "Durchsucht Code",
    "WebSearch": "Sucht im Web",
    "WebFetch": "Lädt Webseite",
}


class JarvisAgent:
    """Wraps the Claude Agent SDK for voice-agent use cases.

    Maintains a dedicated asyncio event loop in a background thread so the
    persistent ClaudeSDKClient is never torn down between queries.
    """

    # Base system prompt for voice interactions — always applied.
    _VOICE_SYSTEM_PROMPT = (
        "You are Jarvis, a voice assistant. "
        "IMPORTANT: Your responses will be read aloud via text-to-speech. "
        "Rules:\n"
        "- Answer in plain spoken language — NO markdown, NO bullet points, "
        "NO tables, NO code blocks, NO emojis.\n"
        "- Keep answers SHORT: 1-3 sentences for simple questions, "
        "max 5-6 sentences for complex ones.\n"
        "- Never use special characters like *, #, |, >, `, or --- in your response.\n"
        "- Respond in the same language the user spoke.\n"
        "- Be direct and conversational, like a helpful colleague speaking out loud.\n"
        "SAFETY RULE — STRICTLY ENFORCED:\n"
        "- NEVER delete, overwrite, or modify any existing file, folder, setting, or data "
        "without first asking the user explicitly and receiving clear confirmation.\n"
        "- This applies to all tools: Bash, Edit, Write, and any other. "
        "When in doubt, ask first."
    )

    # Tools that are safe to auto-approve (read-only, no side effects)
    _SAFE_TOOLS = {
        "Read", "Glob", "Grep", "WebSearch", "WebFetch",
        "TodoRead", "TodoWrite", "Agent",
    }

    def __init__(self, config: JarvisConfig) -> None:
        self.config = config
        self.cost_tracker = CostTracker()
        self._client: ClaudeSDKClient | None = None
        self._session_active = False  # True after first ask() in a session
        self._progress_callback: Callable[[str], None] | None = None
        # Voice permission callback — set by the orchestrator.
        # Signature: (tool_name: str, description: str) -> bool
        self.permission_handler: Callable[[str, str], bool] | None = None

        # Dedicated event loop — lives for the lifetime of this agent.
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._loop.run_forever, daemon=True, name="JarvisAgentLoop"
        )
        self._loop_thread.start()

        # Start connecting immediately in the background.
        asyncio.run_coroutine_threadsafe(self._connect(), self._loop)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _run(self, coro, timeout: float = 90) -> object:
        """Submit a coroutine to the agent loop and block until done."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def _build_memory_block(self) -> str:
        """Load configured memory files — included once in the system prompt."""
        memory_path = Path(self.config.memory.path).expanduser()
        loaded = []
        for filename in self.config.memory.files:
            if filename.lower() == "credentials.md":
                continue
            fpath = memory_path / filename
            if fpath.exists():
                try:
                    content = fpath.read_text().strip()
                    if content:
                        loaded.append(f"### {filename}\n{content}")
                        log.info(f"Memory loaded: {filename}")
                except Exception as e:
                    log.warning(f"Could not read memory file {fpath}: {e}")
            else:
                log.warning(f"Memory file not found: {fpath}")
        if not loaded:
            return ""
        return "\n## Gedächtnis\n" + "\n\n".join(loaded)

    def _build_runtime_context(self) -> str:
        """Per-query context: current time/date — prepended to each message."""
        now = datetime.now().astimezone()
        tz_str = now.tzname() or "UTC"
        weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
        weekday = weekdays[now.weekday()]
        return (
            f"## Aktueller Kontext\n"
            f"- Datum: {weekday}, {now.strftime('%d.%m.%Y')}\n"
            f"- Uhrzeit: {now.strftime('%H:%M')} ({tz_str})\n"
            f"- Benutzer: {getpass.getuser()}\n"
            f"- Hostname: {socket.gethostname()}"
        )

    def _describe_tool_use(self, tool_name: str, tool_input: dict) -> str:
        """Build a human-readable German description of a tool use for voice."""
        if tool_name == "Bash":
            cmd = tool_input.get("command", "unbekannter Befehl")
            # Truncate long commands
            if len(cmd) > 80:
                cmd = cmd[:80] + "..."
            return f"Ich möchte folgenden Befehl ausführen: {cmd}. Soll ich?"
        elif tool_name == "Write":
            path = tool_input.get("file_path", "unbekannte Datei")
            return f"Ich möchte die Datei {Path(path).name} erstellen. Soll ich?"
        elif tool_name == "Edit":
            path = tool_input.get("file_path", "unbekannte Datei")
            return f"Ich möchte die Datei {Path(path).name} bearbeiten. Soll ich?"
        elif tool_name == "NotebookEdit":
            path = tool_input.get("notebook_path", "unbekanntes Notebook")
            return f"Ich möchte das Notebook {Path(path).name} bearbeiten. Soll ich?"
        else:
            return f"Ich möchte das Tool {tool_name} verwenden. Soll ich?"

    async def _can_use_tool(
        self,
        tool_name: str,
        tool_input: dict,
        context: ToolPermissionContext,
    ) -> PermissionResult:
        """Voice-based tool permission callback.

        Auto-approves safe tools (Read, Grep, etc.). For dangerous tools
        (Bash, Write, Edit), asks the user via TTS and waits for voice response.
        """
        # Auto-approve safe/read-only tools
        if tool_name in self._SAFE_TOOLS:
            return PermissionResultAllow()

        # No permission handler wired up → deny (safer than auto-approve)
        if not self.permission_handler:
            log.warning(f"No permission handler — denying {tool_name}")
            return PermissionResultDeny(message="Keine Sprachgenehmigung möglich")

        description = self._describe_tool_use(tool_name, tool_input)

        # Call the voice permission handler (blocks until user responds)
        # Run in executor since it blocks on threading.Event
        loop = asyncio.get_running_loop()
        granted = await loop.run_in_executor(
            None, self.permission_handler, tool_name, description
        )

        if granted:
            return PermissionResultAllow()
        else:
            return PermissionResultDeny(
                message="Vom Benutzer per Sprache abgelehnt"
            )

    def _build_options(self) -> ClaudeAgentOptions:
        """Build ClaudeAgentOptions — includes memory in system prompt."""
        system_prompt = self._VOICE_SYSTEM_PROMPT

        memory_block = self._build_memory_block()
        if memory_block:
            system_prompt += "\n\n" + memory_block

        claude_md = Path.home() / ".jarvis" / "CLAUDE.md"
        if claude_md.exists():
            system_prompt += "\n\n" + claude_md.read_text()

        opts = ClaudeAgentOptions(
            model=self.config.agent.model,
            max_turns=self.config.agent.max_turns,
            max_budget_usd=self.config.agent.max_budget_usd,
            permission_mode=self.config.agent.permission_mode,
            thinking=self.config.agent.thinking,
            system_prompt=system_prompt,
            can_use_tool=self._can_use_tool,
        )
        if self.config.mcp_servers:
            opts.mcp_servers = self.config.mcp_servers
        if self.config.allowed_tools:
            opts.allowed_tools = self.config.allowed_tools
        if self.config.disallowed_tools:
            opts.disallowed_tools = self.config.disallowed_tools
        return opts

    # ── Async internals (run in the dedicated loop) ────────────────────────────

    async def _connect(self) -> None:
        """Connect the persistent ClaudeSDKClient."""
        try:
            options = self._build_options()
            self._client = ClaudeSDKClient(options=options)
            await self._client.connect()
            log.info(f"Agent SDK client connected (model: {options.model})")
        except Exception as e:
            log.error(f"Agent warmup failed: {e}")
            self._client = None

    async def _ask_async(self, text: str) -> str:
        if self._client is None:
            await self._connect()

        # First message of the session: inject memory so Claude has it in context.
        if not self._session_active:
            self._session_active = True
            memory_block = self._build_memory_block()
            prefix = self._build_runtime_context()
            if memory_block:
                prefix += "\n\n" + memory_block
            prompt = prefix + "\n\n" + text
        else:
            prompt = self._build_runtime_context() + "\n\n" + text
        response_text = ""
        try:
            await self._client.query(prompt)
            async for message in self._client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            response_text += block.text
                        elif isinstance(block, ToolUseBlock):
                            label = _TOOL_LABELS.get(block.name, block.name)
                            detail = ""
                            if block.name == "Bash" and block.input.get("command"):
                                detail = f": {block.input['command'][:120]}"
                            elif block.name in ("Read", "Write", "Edit", "Glob") and block.input.get("file_path"):
                                detail = f": {block.input['file_path']}"
                            elif block.name == "Grep" and block.input.get("pattern"):
                                detail = f": {block.input['pattern']}"
                            elif block.name in ("WebSearch", "WebFetch") and block.input.get("query"):
                                detail = f": {block.input['query']}"
                            log.info(f"🔧 {label}{detail}")
                            if self._progress_callback:
                                self._progress_callback(label)
                if isinstance(message, ResultMessage):
                    log.debug(
                        f"ResultMessage: subtype={message.subtype!r}, "
                        f"has_result={bool(message.result)}, "
                        f"result_len={len(message.result) if message.result else 0}"
                    )
                    if message.result:
                        response_text = message.result
                    if message.subtype != "success":
                        log.warning(
                            f"Agent finished with subtype={message.subtype!r}"
                        )
                    self.cost_tracker.record(message.total_cost_usd)
                    log.info(
                        f"Agent response ({message.duration_ms}ms, "
                        f"{message.num_turns} turns, "
                        rf"\${message.total_cost_usd or 0:.4f})"
                    )
        except Exception as e:
            log.error(f"Agent SDK error: {e}")
            return f"Entschuldigung, da gab es einen Fehler: {e}"

        cleaned = clean_for_speech(response_text)
        if not cleaned.strip():
            log.warning("Agent returned empty response")
            return "Entschuldigung, ich konnte leider keine Antwort generieren."
        return cleaned

    async def _save_memory_async(self) -> None:
        """Ask Claude to write updated memory files based on the session."""
        if not self._session_active or self._client is None:
            return
        memory_path = Path(self.config.memory.path).expanduser()
        for filename in self.config.memory.files:
            if filename.lower() == "credentials.md":
                continue
            fpath = memory_path / filename
            try:
                prompt = (
                    f"[MEMORY UPDATE] Bitte erstelle eine aktualisierte Version "
                    f"der Memory-Datei '{filename}' basierend auf unserem Gespräch. "
                    f"Antworte NUR mit dem reinen Dateiinhalt — keine Erklärungen, "
                    f"kein Markdown, keine Anführungszeichen. "
                    f"Wenn nichts Relevantes besprochen wurde, gib den bestehenden Inhalt unverändert zurück."
                )
                await self._client.query(prompt)
                updated = ""
                async for message in self._client.receive_response():
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                updated += block.text
                    if isinstance(message, ResultMessage):
                        if message.subtype == "success" and message.result:
                            updated = message.result
                if updated.strip():
                    fpath.parent.mkdir(parents=True, exist_ok=True)
                    fpath.write_text(updated.strip() + "\n")
                    log.info(f"Memory saved: {filename}")
            except Exception as e:
                log.warning(f"Memory save failed for {filename}: {e}")

    async def _reset_async(self) -> None:
        self._session_active = False
        if self._client:
            await self._client.disconnect()
            self._client = None
        log.info("Session reset — reconnecting...")
        await self._connect()

    async def _reconfigure_async(self) -> None:
        """Disconnect and reconnect with current config (e.g. after model change)."""
        self._session_active = False
        if self._client:
            await self._client.disconnect()
            self._client = None
        log.info("Agent reconfiguring with new options...")
        await self._connect()

    async def _close_async(self) -> None:
        if self._client:
            await self._client.disconnect()
            self._client = None

    # ── Public sync API (called from orchestrator / any thread) ───────────────

    def interrupt(self) -> None:
        """Interrupt the currently running agent query."""
        if self._client:
            try:
                self._client.interrupt()
                log.info("Agent interrupted")
            except Exception as e:
                log.warning(f"Interrupt failed: {e}")

    def ask(self, text: str) -> str:
        """Send a voice command and return the spoken response (blocking)."""
        return self._run(self._ask_async(text))

    def save_memory(self) -> None:
        """Fire-and-forget: write updated memory files in background."""
        asyncio.run_coroutine_threadsafe(self._save_memory_async(), self._loop)

    def reset_session(self) -> None:
        """End the current session and reconnect for the next one."""
        self._run(self._reset_async())

    def reconfigure(self) -> None:
        """Restart the SDK client with current config. Call after changing model/options."""
        self._run(self._reconfigure_async())

    def close(self) -> None:
        """Clean up resources."""
        try:
            self._run(self._close_async(), timeout=5)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        log.info(f"Agent closed. {self.cost_tracker.summary()}")
