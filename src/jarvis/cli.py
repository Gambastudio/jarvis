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

    console.print(Panel.fit(
        f"[bold green]Jarvis v{__version__}[/bold green]\n"
        f"Wake word: [cyan]{cfg.session.wake_word}[/cyan]\n"
        f"STT: {cfg.stt.engine} ({cfg.stt.model})\n"
        f"TTS: {cfg.tts.engine}\n"
        f"Model: {cfg.agent.model}",
        title="Starting Voice Pipeline",
    ))

    asyncio.run(_run_pipeline(cfg))


async def _run_pipeline(cfg) -> None:
    """Main voice pipeline loop."""
    from jarvis.agent.core import JarvisAgent
    from jarvis.pipeline.wake.whisper_wake import WhisperWakeEngine
    from jarvis.pipeline.tts.macos_say import MacOSSayEngine
    from jarvis.pipeline.feedback_guard import FeedbackGuard
    from jarvis.utils.logging import setup_logging

    import logging
    log = logging.getLogger("jarvis")

    agent = JarvisAgent(cfg)
    wake = WhisperWakeEngine(cfg.wake_word.variants)
    tts = MacOSSayEngine(rate=cfg.tts.rate, voice=cfg.tts.voice)
    guard = FeedbackGuard()

    session_active = False

    def process_text(text: str) -> None:
        nonlocal session_active
        text = text.strip()
        if not text or len(text) < 2:
            return

        log.info(f'STT: "{text}"')

        # Not in session — check for wake word
        if not session_active:
            cmd = wake.check_transcription(text)
            if cmd is None:
                return
            session_active = True
            log.info("SESSION STARTED")

            if cmd:
                response = asyncio.run(agent.ask(cmd))
                log.info(f"Jarvis: {response}")
                guard.mute()
                asyncio.run(tts.speak(response))
                guard.unmute()
            else:
                guard.mute()
                asyncio.run(tts.speak("Ja?"))
                guard.unmute()
            return

        # Check for stop word
        t = text.lower().strip().rstrip(".!,")
        if t in [cfg.session.stop_word, f"{cfg.session.stop_word}schoen", f"vielen {cfg.session.stop_word}"]:
            session_active = False
            asyncio.run(agent.reset_session())
            log.info("SESSION ENDED")
            guard.mute()
            asyncio.run(tts.speak("Alles klar."))
            guard.unmute()
            return

        # Check for exit phrase
        if text.lower() in [cfg.session.exit_phrase, "programm beenden"]:
            guard.mute()
            asyncio.run(tts.speak("Bis spaeter!"))
            guard.unmute()
            log.info("PROGRAM EXIT")
            raise SystemExit(0)

        # Process command
        response = asyncio.run(agent.ask(text))
        log.info(f"Jarvis: {response}")
        guard.mute()
        asyncio.run(tts.speak(response))
        guard.unmute()

    # Main recorder loop with auto-recovery
    log.info(f"Waiting for '{cfg.session.wake_word}'...")

    try:
        from RealtimeSTT import AudioToTextRecorder
    except ImportError:
        console.print("[red]RealtimeSTT not installed.[/red] Run: pip install jarvis-voice[stt]")
        raise SystemExit(1)

    while True:
        recorder = None
        try:
            recorder = AudioToTextRecorder(
                model=cfg.stt.model,
                compute_type=cfg.stt.compute_type,
                language=cfg.stt.language,
                initial_prompt=cfg.stt.initial_prompt,
                spinner=False,
                silero_sensitivity=cfg.vad.sensitivity,
                post_speech_silence_duration=cfg.vad.post_speech_silence,
                min_length_of_recording=cfg.vad.min_recording_length,
                min_gap_between_recordings=0.05,
                on_transcription_start=lambda *a: None,
            )
            guard.set_recorder(recorder)
            log.info("Recorder ready")
            guard.mute()
            asyncio.run(tts.speak("Jarvis online."))
            guard.unmute()

            while True:
                recorder.text(process_text)

        except SystemExit:
            break
        except KeyboardInterrupt:
            break
        except Exception as e:
            log.warning(f"Recorder error: {e} — restarting in 2s...")
            import time
            time.sleep(2)
        finally:
            if recorder:
                try:
                    recorder.stop()
                except Exception:
                    pass

    await agent.close()


@app.command("query")
def query_text(
    prompt: str = typer.Argument(help="Text prompt to send to the agent"),
    config: Path | None = typer.Option(None, "--config", "-c", help="Path to jarvis.yaml"),
) -> None:
    """Send a text query to the agent (no voice, useful for testing)."""
    from jarvis.config import JarvisConfig
    from jarvis.agent.core import JarvisAgent
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
    migrate: Path | None = typer.Option(None, "--migrate", help="Migrate from Jarvis4Gamba config.json"),
) -> None:
    """Manage Jarvis configuration."""
    from jarvis.config import JarvisConfig, DEFAULT_CONFIG_FILE
    import yaml

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
