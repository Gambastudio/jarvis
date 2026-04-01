"""Clean text for speech output — strip markdown and formatting.

Ported from Jarvis4Gamba claude_bridge.py _clean_for_speech().
"""

import re


def clean_for_speech(text: str, max_length: int = 800) -> str:
    """Remove markdown formatting and truncate for TTS output."""
    if not text:
        return ""
    # Code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Inline code
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Markdown headers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Bold / italic
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    # Links
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Markdown tables (entire lines with |)
    text = re.sub(r"^\|.*\|$", "", text, flags=re.MULTILINE)
    # Table separator lines (---|---)
    text = re.sub(r"^[-|: ]+$", "", text, flags=re.MULTILINE)
    # Horizontal rules
    text = re.sub(r"^---+$", "", text, flags=re.MULTILINE)
    # Bullet points
    text = re.sub(r"^[-*]\s+", "", text, flags=re.MULTILINE)
    # Multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Truncate
    if len(text) > max_length:
        text = text[:max_length] + "... und mehr."
    return text.strip()
