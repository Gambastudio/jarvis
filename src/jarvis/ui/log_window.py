"""Cocoa NSWindow log viewer — thread-safe colored live log.

Uses a queue.Queue for thread safety: background threads call enqueue(),
the Main Thread polls via flush() (called from a rumps.Timer every 100ms).
"""

from __future__ import annotations

import logging
import queue

log = logging.getLogger("jarvis")

# Color map: log category → (R, G, B)
_COLORS = {
    "stt": (0.4, 0.8, 1.0),  # light blue
    "jarvis": (0.4, 1.0, 0.4),  # green
    "session": (1.0, 0.85, 0.2),  # yellow
    "error": (1.0, 0.3, 0.3),  # red
    "system": (0.7, 0.5, 1.0),  # purple
    "default": (0.75, 0.75, 0.75),  # grey
    "time": (0.5, 0.5, 0.5),  # dark grey
}
_EMOJIS = {
    "stt": "🎙",
    "jarvis": "🤖",
    "session": "●",
    "error": "❌",
    "system": "⚙️",
    "default": "  ",
}
_BG = (0.1, 0.1, 0.12)
_MAX_LINES = 500


def _classify(text: str) -> str:
    t = text.lower()
    if "stt:" in t:
        return "stt"
    if "jarvis:" in t:
        return "jarvis"
    if "session" in t:
        return "session"
    if "error" in t or "fehler" in t:
        return "error"
    if "recorder" in t or "pipeline" in t:
        return "system"
    return "default"


class LogWindow:
    """Native macOS log window. Call enqueue() from any thread, flush() from Main Thread."""

    def __init__(self) -> None:
        self._queue: queue.Queue[str] = queue.Queue()
        self._window = None
        self._text_view = None
        self._font = None
        self._color_cache: dict = {}

    def _nscolor(self, rgb: tuple) -> object:
        if rgb not in self._color_cache:
            from AppKit import NSColor

            self._color_cache[rgb] = NSColor.colorWithCalibratedRed_green_blue_alpha_(
                rgb[0], rgb[1], rgb[2], 1.0
            )
        return self._color_cache[rgb]

    def create(self) -> None:
        """Create and show the window. Must be called from Main Thread."""
        if self._window is not None:
            self._window.makeKeyAndOrderFront_(None)
            return

        from AppKit import (
            NSBackingStoreBuffered,
            NSBezelBorder,
            NSFont,
            NSMakeRect,
            NSScrollView,
            NSTextView,
            NSWindow,
            NSWindowCollectionBehaviorCanJoinAllSpaces,
            NSWindowStyleMaskClosable,
            NSWindowStyleMaskMiniaturizable,
            NSWindowStyleMaskResizable,
            NSWindowStyleMaskTitled,
        )

        bg = self._nscolor(_BG)
        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskResizable
            | NSWindowStyleMaskMiniaturizable
        )
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(100, 200, 720, 480), style, NSBackingStoreBuffered, False
        )
        self._window.setTitle_("Jarvis — Log")
        self._window.setMinSize_((400, 200))
        self._window.setLevel_(3)
        self._window.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces)
        self._window.setBackgroundColor_(bg)
        self._window.setReleasedWhenClosed_(False)

        content = self._window.contentView()
        frame = content.bounds()

        scroll = NSScrollView.alloc().initWithFrame_(frame)
        scroll.setHasVerticalScroller_(True)
        scroll.setHasHorizontalScroller_(False)
        scroll.setAutoresizingMask_(0x12)
        scroll.setBorderType_(NSBezelBorder)
        scroll.setBackgroundColor_(bg)

        self._text_view = NSTextView.alloc().initWithFrame_(frame)
        self._text_view.setEditable_(False)
        self._text_view.setSelectable_(True)
        self._text_view.setRichText_(True)
        self._text_view.setBackgroundColor_(bg)
        self._text_view.setTextContainerInset_((8, 8))
        self._text_view.setAutoresizingMask_(0x12)

        self._font = NSFont.fontWithName_size_("Menlo", 12)
        if not self._font:
            self._font = NSFont.monospacedSystemFontOfSize_weight_(12, 0)
        self._text_view.setFont_(self._font)
        scroll.setDocumentView_(self._text_view)
        content.addSubview_(scroll)
        self._window.makeKeyAndOrderFront_(None)

    def close(self) -> None:
        """Hide the window."""
        if self._window:
            self._window.orderOut_(None)

    def enqueue(self, text: str) -> None:
        """Thread-safe: add a log line to the display queue."""
        self._queue.put(text)

    def flush(self) -> None:
        """Drain queue into NSTextView. Must be called from Main Thread."""
        if not self._text_view:
            # Window not yet created — drain silently to prevent overflow
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
            return

        count = 0
        while not self._queue.empty() and count < 50:
            try:
                text = self._queue.get_nowait()
                self._append(text)
                count += 1
            except queue.Empty:
                break

    def _append(self, text: str) -> None:
        """Append one colored line to the NSTextView. Main Thread only."""
        from AppKit import NSAttributedString, NSFontAttributeName, NSForegroundColorAttributeName
        from Foundation import NSDictionary, NSMutableAttributedString

        category = _classify(text)
        color = self._nscolor(_COLORS.get(category, _COLORS["default"]))
        time_color = self._nscolor(_COLORS["time"])
        emoji = _EMOJIS.get(category, "  ")

        full = NSMutableAttributedString.alloc().init()

        parts = text.split("] ", 1)
        if len(parts) == 2:
            time_part, msg_part = parts[0] + "] ", parts[1]
        else:
            time_part, msg_part = "", text

        def _attr_str(s: str, clr: object) -> object:
            attrs = NSDictionary.dictionaryWithObjects_forKeys_(
                [clr, self._font],
                [NSForegroundColorAttributeName, NSFontAttributeName],
            )
            return NSAttributedString.alloc().initWithString_attributes_(s, attrs)

        if time_part:
            full.appendAttributedString_(_attr_str(time_part, time_color))
        full.appendAttributedString_(_attr_str(f"{emoji} {msg_part}\n", color))

        storage = self._text_view.textStorage()
        storage.appendAttributedString_(full)
        self._text_view.scrollRangeToVisible_((storage.length(), 0))

        # Trim to _MAX_LINES to prevent memory growth
        text_str = storage.string()
        lines = text_str.split("\n")
        if len(lines) > _MAX_LINES:
            cut = 0
            for _ in range(100):
                idx = text_str.find("\n", cut)
                if idx == -1:
                    break
                cut = idx + 1
            if cut > 0:
                storage.deleteCharactersInRange_((0, cut))


class WindowLogHandler(logging.Handler):
    """Logging handler that forwards records to LogWindow.enqueue()."""

    def __init__(self, log_window: LogWindow) -> None:
        super().__init__()
        self.log_window = log_window
        self.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.log_window.enqueue(self.format(record))
        except Exception:
            pass
