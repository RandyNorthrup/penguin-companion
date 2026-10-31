"""Settings you edit (config.toml) and state the companion keeps (state.json)."""

from __future__ import annotations

import copy
import json
import os
import tomllib
from pathlib import Path
from typing import Any

from . import paths

DEFAULTS: dict[str, Any] = {
    "name": "",
    "size": 120,
    "walk": True,
    "sleep_after_minutes": 10,
    "ai": {"brain": "auto", "timeout_seconds": 180, "brains": {}},
    "breaks": {"every_minutes": 60, "snooze_minutes": 10},
    "focus": {"minutes": 25},
    "heads_up": {
        "battery_low": 20,
        "battery_critical": 10,
        "disk_full_percent": 90,
        "updates": True,
        "updates_every_hours": 6,
    },
}

TEMPLATE = """\
# Penguin companion settings. Save this file, then pick "Reload settings" from
# the penguin's menu (right-click it), or restart it.

# What the penguin is called. Empty: it asks the first time it runs.
name = ""

# Height of the penguin on screen, in pixels.
size = 120

# Wander along the bottom of the screen.
walk = true

# Fall asleep after this many minutes without any attention (0: never).
sleep_after_minutes = 10

[ai]
# Which brain answers your questions. "auto" picks the first one available, in
# this order: claude, codex, gemini, grok (their command-line tools, using your
# own login), then anthropic-api, openai-api, gemini-api, xai-api, openrouter
# (when their API key is set). Or name one, including your own from below.
brain = "auto"
timeout_seconds = 180

# Add your own brain, or change a built-in one by using its name.
#
# A command brain gets the question on stdin, or in a file whose path replaces
# a "{prompt_file}" argument, or as a "{prompt}" argument itself; it answers on
# stdout, or in the file named by an "{output_file}" argument:
#
# [ai.brains.my-tool]
# type = "command"
# command = ["my-tool", "--quiet"]
#
# An HTTP brain speaks the Anthropic Messages API (type = "anthropic") or the
# OpenAI chat completions API (type = "openai"), which most providers accept:
#
# [ai.brains.my-provider]
# type = "openai"
# url = "https://api.example.com/v1"
# model = "some-model"
# api_key_env = "MY_PROVIDER_API_KEY"

[breaks]
# Nudge you to take a break after this many minutes at the screen (0: off).
every_minutes = 60
snooze_minutes = 10

[focus]
minutes = 25

[heads_up]
battery_low = 20          # percent; 0 turns battery warnings off
battery_critical = 10
disk_full_percent = 90    # 0 turns disk warnings off
updates = true            # say when system updates are waiting
updates_every_hours = 6
"""


def merge(base: dict, override: dict) -> dict:
    """`base` with `override` laid over it, recursing into tables."""
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: Path | None = None) -> tuple[dict, str | None]:
    """The settings, and an error message if the file could not be read."""
    path = path or paths.config_file()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(TEMPLATE, encoding="utf-8")
    try:
        user = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return copy.deepcopy(DEFAULTS), f"{path.name}: {exc}"
    return merge(DEFAULTS, user), None


class State:
    """Small JSON file for what the companion remembers between runs."""

    def __init__(self, path: Path, data: dict):
        self.path = path
        self.data = data

    @classmethod
    def load(cls, path: Path | None = None) -> "State":
        path = path or paths.state_file()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        return cls(path, data if isinstance(data, dict) else {})

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)
