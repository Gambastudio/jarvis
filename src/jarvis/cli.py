"""Jarvis CLI — command line interface for the voice agent framework."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from jarvis import __version__

app = typer.Typer(
    name="jarvis",
    help="Jarvis — Open Source Voice Agent Framework powered by Claude Agent SDK.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def listen(
    config: Path | None = typer.Option(None, "--config", "-c", help="Path to jarvis.yaml"),
) -> None:
    """Start the voice pipeline — listen for wake word and process commands."""
    from jarvis.config import JarvisConfig
    from jarvis.utils.logging import setup_logging

    cfg = JarvisConfig.load(config)
    setup_logging(cfg.logging.level, cfg.logging.file)

    console.print(
        Panel.fit(
            f"[bold green]Jarvis v{__version__}[/bold green]\n"
            f"Wake word: [cyan]{cfg.session.wake_word}[/cyan]\n"
            f"STT: {cfg.stt.engine} ({cfg.stt.model})\n"
            f"TTS: {cfg.tts.engine}\n"
            f"Model: {cfg.agent.model}",
            title="Starting Voice Pipeline",
        )
    )

    asyncio.run(_run_pipeline(cfg))


async def _run_pipeline(cfg) -> None:
    """Main voice pipeline — delegates to VoicePipeline orchestrator."""
    from jarvis.agent.core import JarvisAgent
    from jarvis.pipeline.orchestrator import VoicePipeline
    from jarvis.pipeline.tts.macos_say import MacOSSayEngine
    from jarvis.pipeline.wake.whisper_wake import WhisperWakeEngine

    try:
        from jarvis.pipeline.stt.realtimestt import RealtimeSTTEngine
    except ImportError:
        console.print("[red]RealtimeSTT not installed.[/red] Run: pip install jarvis-voice[stt]")
        raise SystemExit(1)

    stt = RealtimeSTTEngine(stt_config=cfg.stt, vad_config=cfg.vad)
    tts = MacOSSayEngine(rate=cfg.tts.rate, voice=cfg.tts.voice)
    wake = WhisperWakeEngine(cfg.wake_word.variants)
    agent = JarvisAgent(cfg)

    pipeline = VoicePipeline(stt=stt, tts=tts, wake=wake, agent=agent, config=cfg)
    await pipeline.run()


@app.command("query")
def query_text(
    prompt: str = typer.Argument(help="Text prompt to send to the agent"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Path to jarvis.yaml"),
) -> None:
    """Send a text query to the agent (no voice, useful for testing)."""
    from jarvis.agent.core import JarvisAgent
    from jarvis.config import JarvisConfig
    from jarvis.utils.logging import setup_logging

    cfg = JarvisConfig.load(config)
    setup_logging(cfg.logging.level)

    async def run() -> None:
        agent = JarvisAgent(cfg)
        response = await agent.ask(prompt)
        console.print(f"\n[green]Jarvis:[/green] {response}\n")
        await agent.close()

    asyncio.run(run())


@app.command()
def version() -> None:
    """Show Jarvis version."""
    console.print(f"Jarvis v{__version__}")


@app.command()
def config(
    init: bool = typer.Option(False, "--init", help="Create default config file"),
    show: bool = typer.Option(False, "--show", help="Show current config"),
    migrate: Path | None = typer.Option(
        None, "--migrate", help="Migrate from Jarvis4Gamba config.json"
    ),
) -> None:
    """Manage Jarvis configuration."""

    from jarvis.config import DEFAULT_CONFIG_FILE, JarvisConfig

    if init:
        DEFAULT_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        cfg = JarvisConfig()
        # Write default config as YAML
        console.print(f"[green]Config created at {DEFAULT_CONFIG_FILE}[/green]")
    elif migrate and migrate.exists():
        cfg = JarvisConfig.from_legacy_json(migrate)
        console.print("[green]Migrated from Jarvis4Gamba config.[/green]")
    elif show:
        cfg = JarvisConfig.load()
        console.print(f"Model: {cfg.agent.model}")
        console.print(f"STT: {cfg.stt.engine} ({cfg.stt.model})")
        console.print(f"TTS: {cfg.tts.engine}")
        console.print(f"Wake: {cfg.session.wake_word}")
    else:
        typer.echo("Use --init, --show, or --migrate. See --help.")


if __name__ == "__main__":
    app()
