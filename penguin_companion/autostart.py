"""Start the companion when you log in: a .desktop file on Linux, a
LaunchAgent on macOS, a Run key in the registry on Windows."""

from __future__ import annotations

import os
import plistlib
import shlex
import subprocess
import sys
from pathlib import Path

from . import paths

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_NAME = "PenguinCompanion"
_LABEL = "io.github.penguin-companion"


def _desktop_file() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart" / f"{paths.APP}.desktop"


def _launch_agent() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_LABEL}.plist"


def where() -> str:
    if sys.platform == "win32":
        return f"HKEY_CURRENT_USER\\{_RUN_KEY}\\{_NAME}"
    return str(_launch_agent() if sys.platform == "darwin" else _desktop_file())


def enabled() -> bool:
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
                winreg.QueryValueEx(key, _NAME)
            return True
        except OSError:
            return False
    return (_launch_agent() if sys.platform == "darwin" else _desktop_file()).exists()


def set_enabled(on: bool) -> None:
    command = paths.command_line(windowless=True)
    if sys.platform == "win32":
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if on:
                winreg.SetValueEx(key, _NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(command))
            else:
                try:
                    winreg.DeleteValue(key, _NAME)
                except OSError:
                    pass
        return
    path = _launch_agent() if sys.platform == "darwin" else _desktop_file()
    if not on:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        path.write_bytes(plistlib.dumps({"Label": _LABEL, "ProgramArguments": command, "RunAtLoad": True}))
        return
    path.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Penguin companion\n"
        "Comment=An electric penguin that lives on your desktop and helps out\n"
        f"Exec={shlex.join(command)}\n"
        "X-GNOME-Autostart-enabled=true\n",
        encoding="utf-8",
    )
