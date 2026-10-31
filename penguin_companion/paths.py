"""Where the companion keeps its settings and state, and how others reach it,
on Linux, macOS and Windows."""

from __future__ import annotations

import getpass
import os
import shutil
import sys
import tempfile
from pathlib import Path

APP = "penguin-companion"


def _base(xdg_var: str, xdg_default: Path) -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    value = os.environ.get(xdg_var)
    return Path(value) if value else xdg_default


def config_dir() -> Path:
    return _base("XDG_CONFIG_HOME", Path.home() / ".config") / APP


def config_file() -> Path:
    return config_dir() / "config.toml"


def state_dir() -> Path:
    path = _base("XDG_STATE_HOME", Path.home() / ".local" / "state") / APP
    return path / "state" if sys.platform in ("win32", "darwin") else path


def state_file() -> Path:
    return state_dir() / "state.json"


def work_dir() -> Path:
    """An empty folder that command-line AI brains run in, away from your files."""
    path = state_dir() / "work"
    path.mkdir(parents=True, exist_ok=True)
    return path


def socket_path() -> Path:
    run = os.environ.get("XDG_RUNTIME_DIR")
    if run:
        return Path(run) / f"{APP}.sock"
    uid = getattr(os, "getuid", lambda: getpass.getuser())()
    return Path(tempfile.gettempdir()) / f"{APP}-{uid}.sock"


def server_name() -> str:
    """The local server's name: a socket path on Linux and macOS, a named
    pipe on Windows."""
    if sys.platform == "win32":
        return f"{APP}-{getpass.getuser()}"
    return str(socket_path())


def anim_dir() -> Path:
    return Path(__file__).resolve().parent / "anim"


def command_line(windowless: bool = False) -> list[str]:
    """How to run this companion from a hook, a shortcut or autostart."""
    installed = shutil.which(APP)
    if installed:
        return [installed]
    python = sys.executable
    if windowless and sys.platform == "win32":
        pythonw = Path(python).with_name("pythonw.exe")
        python = str(pythonw) if pythonw.exists() else python
    launcher = Path(__file__).resolve().parent.parent / APP
    if launcher.exists():
        return [python, str(launcher)]
    return [python, "-m", "penguin_companion"]
