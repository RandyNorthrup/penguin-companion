"""Command line: start the companion, or talk to the one that's running."""

from __future__ import annotations

import json
import os
import shlex
import sys

from . import __version__, events, paths

USAGE = """\
usage: penguin-companion [command]

  (no command)             start the companion
  notify [EVENT] [JSON]    tell it what an AI agent is doing (for hooks)
      --source NAME        who it's from: claude, codex, gemini, grok...
      --stdin              read the hook's JSON payload from stdin
      --message TEXT       what to show
      EVENT is one of: working, needs-you, done, success, error, idle;
      left out, it's worked out from the payload
  say TEXT                 make it say something
  remind WHEN [to] TEXT    set a reminder: remind in 20m to stretch
  hooks [AGENT]            print the hook setup for claude, codex, or any agent
  autostart on|off         start it when you log in
  --version
"""


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        from .app import run

        return run()
    command, rest = args[0], args[1:]
    if command in ("-h", "--help", "help"):
        print(USAGE, end="")
        return 0
    if command == "--version":
        print(__version__)
        return 0
    if command == "notify":
        return notify(rest)
    if command == "say":
        return _send({"type": "say", "text": " ".join(rest)})
    if command == "remind":
        return _send({"type": "remind", "text": " ".join(rest)})
    if command == "hooks":
        print(hooks(rest[0] if rest else "all"))
        return 0
    if command == "autostart" and rest and rest[0] in ("on", "off"):
        from . import autostart

        autostart.set_enabled(rest[0] == "on")
        print(f"Autostart {rest[0]}: {autostart.where()}")
        return 0
    print(USAGE, end="", file=sys.stderr)
    return 2


def _send(message: dict) -> int:
    if events.send(message):
        return 0
    print("The penguin isn't running. Start it with: penguin-companion", file=sys.stderr)
    return 1


def _json(text: str) -> dict:
    try:
        value = json.loads(text)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def notify(args: list[str]) -> int:
    """For hooks: never fails, never waits, never prints."""
    if os.environ.get(events.INTERNAL_ENV):
        return 0
    event = source = message = None
    payload: dict = {}
    read_stdin = False
    it = iter(args)
    for arg in it:
        if arg == "--source":
            source = next(it, None)
        elif arg == "--message":
            message = next(it, None)
        elif arg == "--stdin":
            read_stdin = True
        elif arg.lstrip().startswith("{"):
            payload = _json(arg)
        elif event is None:
            event = arg
        elif message is None:
            message = arg
    if read_stdin and not sys.stdin.isatty():
        payload = _json(sys.stdin.read()) or payload
    msg = events.event_from(event, payload, source=source, message=message)
    if msg:
        events.send(msg)
    return 0


def hooks(agent: str) -> str:
    cmd = shlex.join(paths.command_line())
    claude = json.dumps(
        {
            "hooks": {
                name: [{"hooks": [{"type": "command", "command": f"{cmd} notify --source claude --stdin"}]}]
                for name in ("UserPromptSubmit", "Notification", "Stop")
            }
        },
        indent=2,
    )
    codex_notify = json.dumps(paths.command_line() + ["notify", "--source", "codex"])
    parts = {
        "claude": f"# Claude Code: merge into ~/.claude/settings.json\n{claude}",
        "codex": f"# Codex: add to ~/.codex/config.toml (Codex calls it when a turn finishes)\nnotify = {codex_notify}",
        "any": (
            "# Any other agent or script (Gemini CLI, Grok, Aider, CI...): have its hooks run\n"
            f"{cmd} notify working   --source NAME    # started on something\n"
            f"{cmd} notify needs-you --source NAME 'Approve the deploy?'\n"
            f"{cmd} notify done      --source NAME    # finished"
        ),
    }
    if agent in parts:
        return parts[agent]
    return "\n\n".join(parts.values())
