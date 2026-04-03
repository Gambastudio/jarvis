"""macOS Keychain integration for secure API key storage.

Uses the 'security' CLI tool to store/retrieve the Anthropic API key
in the macOS Keychain — never written to disk or environment files.
"""

from __future__ import annotations

import logging
import subprocess

log = logging.getLogger("jarvis")

_SERVICE = "jarvis-voice"
_ACCOUNT = "anthropic-api-key"
_DEEPGRAM_ACCOUNT = "deepgram-api-key"


def set_api_key(api_key: str, account: str = _ACCOUNT) -> bool:
    """Store API key in macOS Keychain. Overwrites existing entry."""
    result = subprocess.run(
        ["security", "add-generic-password", "-s", _SERVICE, "-a", account, "-w", api_key, "-U"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        log.info(f"API key saved to Keychain ({account})")
        return True
    log.warning(f"Failed to save API key: {result.stderr.strip()}")
    return False


def get_api_key(account: str = _ACCOUNT) -> str | None:
    """Retrieve API key from macOS Keychain. Returns None if not found."""
    result = subprocess.run(
        ["security", "find-generic-password", "-s", _SERVICE, "-a", account, "-w"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip() or None
    return None


def has_api_key(account: str = _ACCOUNT) -> bool:
    """Check whether an API key is stored in the Keychain."""
    return get_api_key(account) is not None


def set_deepgram_key(api_key: str) -> bool:
    """Store Deepgram API key in macOS Keychain."""
    return set_api_key(api_key, _DEEPGRAM_ACCOUNT)


def get_deepgram_key() -> str | None:
    """Retrieve Deepgram API key from macOS Keychain."""
    return get_api_key(_DEEPGRAM_ACCOUNT)


def has_deepgram_key() -> bool:
    """Check whether a Deepgram API key is stored."""
    return has_api_key(_DEEPGRAM_ACCOUNT)


_ELEVENLABS_ACCOUNT = "elevenlabs-api-key"


def set_elevenlabs_key(api_key: str) -> bool:
    """Store ElevenLabs API key in macOS Keychain."""
    return set_api_key(api_key, _ELEVENLABS_ACCOUNT)


def get_elevenlabs_key() -> str | None:
    """Retrieve ElevenLabs API key from macOS Keychain."""
    return get_api_key(_ELEVENLABS_ACCOUNT)


def has_elevenlabs_key() -> bool:
    """Check whether an ElevenLabs API key is stored."""
    return has_api_key(_ELEVENLABS_ACCOUNT)
