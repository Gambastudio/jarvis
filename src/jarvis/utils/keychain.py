"""macOS Keychain integration for secure API key storage.

Uses the 'security' CLI tool to store/retrieve the Anthropic API key
in the macOS Keychain — never written to disk or environment files.
"""
from __future__ import annotations

import subprocess
import logging

log = logging.getLogger("jarvis")

_SERVICE = "jarvis-voice"
_ACCOUNT = "anthropic-api-key"


def set_api_key(api_key: str) -> bool:
    """Store API key in macOS Keychain. Overwrites existing entry."""
    result = subprocess.run(
        ["security", "add-generic-password",
         "-s", _SERVICE, "-a", _ACCOUNT,
         "-w", api_key, "-U"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        log.info("API key saved to Keychain")
        return True
    log.warning(f"Failed to save API key: {result.stderr.strip()}")
    return False


def get_api_key() -> str | None:
    """Retrieve API key from macOS Keychain. Returns None if not found."""
    result = subprocess.run(
        ["security", "find-generic-password",
         "-s", _SERVICE, "-a", _ACCOUNT, "-w"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip() or None
    return None


def has_api_key() -> bool:
    """Check whether an API key is stored in the Keychain."""
    return get_api_key() is not None
