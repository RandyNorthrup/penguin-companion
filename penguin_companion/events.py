"""The little protocol that lets hooks, scripts and a second launch talk to
the running companion: one JSON object per line over a local socket."""

from __future__ import annotations

import json
import socket
import sys
from typing import Any

from . import paths

# Set in the environment of the AI tools the companion itself runs, so their
# hooks don't make the penguin react to its own questions.
INTERNAL_ENV = "PENGUIN_COMPANION_INTERNAL"

EVENTS = {
    "working": ("working", "start", "started", "busy", "thinking", "prompt"),
    "needs-you": ("needs-you", "needs_you", "attention", "permission", "input", "waiting", "notification", "alert"),
    "done": ("done", "stop", "stopped", "finished", "complete", "completed", "turn-complete"),
    "success": ("success", "celebrate", "passed", "merged"),
    "error": ("error", "failed", "failure"),
    "idle": ("idle", "reset", "clear", "end"),
}
_ALIASES = {alias: name for name, aliases in EVENTS.items() for alias in aliases}

# Event names in hook payloads: Claude Code's hook_event_name, Codex's notify
# type, and the BeforeAgent/AfterAgent style other CLIs use.
_PAYLOAD_EVENTS = {
    "UserPromptSubmit": "working",
    "Notification": "needs-you",
    "Stop": "done",
    "SessionEnd": "idle",
    "BeforeAgent": "working",
    "AfterAgent": "done",
    "agent-turn-complete": "done",
}

_MESSAGE_KEYS = ("message", "last-assistant-message", "last_assistant_message")


def normalize(name: str | None) -> str | None:
    if not name:
        return None
    return _ALIASES.get(name.strip().lower())


def event_from(
    event: str | None, payload: dict[str, Any] | None = None, *, source: str | None = None, message: str | None = None
) -> dict[str, Any] | None:
    """The message to send for a hook call, or None if there's nothing to say."""
    payload = payload or {}
    name = normalize(event)
    if name is None and event is None:
        hook = payload.get("hook_event_name") or payload.get("type")
        name = _PAYLOAD_EVENTS.get(str(hook)) if hook else None
    if name is None:
        return None
    if message is None:
        for key in _MESSAGE_KEYS:
            if isinstance(payload.get(key), str) and payload[key].strip():
                message = payload[key].strip()
                break
    return {"type": "event", "event": name, "source": source or "agent", "message": message or ""}


def send(message: dict[str, Any], timeout: float = 0.5) -> bool:
    """Deliver a message to the running companion. False if it isn't running."""
    data = (json.dumps(message) + "\n").encode("utf-8")
    if sys.platform == "win32":
        return _send_pipe(data, timeout)
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(paths.server_name())
            sock.sendall(data)
        return True
    except OSError:
        return False


def _send_pipe(data: bytes, timeout: float) -> bool:
    from PyQt6.QtNetwork import QLocalSocket

    sock = QLocalSocket()
    sock.connectToServer(paths.server_name())
    if not sock.waitForConnected(int(timeout * 1000)):
        return False
    sock.write(data)
    sock.waitForBytesWritten(int(timeout * 1000))
    sock.disconnectFromServer()
    return True


def parse_lines(data: bytes) -> list[dict[str, Any]]:
    out = []
    for line in data.decode("utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            out.append(value)
    return out
