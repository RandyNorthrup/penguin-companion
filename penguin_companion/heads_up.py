"""Things worth a heads-up: a low battery, a filling disk, waiting updates.

Each check tells you once, not every minute: a battery warning once per level
until you plug in, a full disk once a day, waiting updates once a day.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass
class Notice:
    key: str
    title: str
    text: str
    urgent: bool = False


def read_battery() -> tuple[float, bool] | None:
    """(percent, plugged in), or None without a battery."""
    try:
        import psutil

        battery = psutil.sensors_battery()
        if battery is not None:
            return float(battery.percent), bool(battery.power_plugged)
    except Exception:
        pass
    for bat in sorted(Path("/sys/class/power_supply").glob("BAT*")):
        try:
            percent = float((bat / "capacity").read_text().strip())
            status = (bat / "status").read_text().strip()
        except (OSError, ValueError):
            continue
        return percent, status != "Discharging"
    return None


def disk_folders() -> list[Path]:
    """The system disk and the one your files are on."""
    home = Path.home()
    return [Path(home.anchor), home]


def read_disks(folders: list[Path]) -> list[tuple[str, float]]:
    """(folder, percent used) for each folder on a different disk."""
    seen, out = set(), []
    for folder in folders:
        try:
            device = os.stat(folder).st_dev
            usage = shutil.disk_usage(folder)
        except OSError:
            continue
        if device in seen or usage.total == 0:
            continue
        seen.add(device)
        out.append((str(folder), 100.0 * usage.used / usage.total))
    return out


def count_apt(output: str) -> int:
    return sum(1 for line in output.splitlines() if "upgradable from" in line)


def count_flatpak(output: str) -> int:
    return sum(1 for line in output.splitlines() if line.strip())


class Watcher:
    def __init__(self, battery_low: float, battery_critical: float, disk_full: float):
        self.battery_low = battery_low
        self.battery_critical = battery_critical
        self.disk_full = disk_full
        self._battery_told: str | None = None
        self._disk_told: dict[str, date] = {}
        self._updates_told: date | None = None

    def battery(self, reading: tuple[float, bool] | None) -> Notice | None:
        if reading is None or self.battery_low <= 0:
            return None
        percent, plugged = reading
        if plugged or percent > self.battery_low + 2:
            self._battery_told = None
            return None
        level = "critical" if percent <= self.battery_critical else "low" if percent <= self.battery_low else None
        if level is None or level == self._battery_told or (level == "low" and self._battery_told == "critical"):
            return None
        self._battery_told = level
        if level == "critical":
            return Notice("battery", "Battery almost empty", f"Battery at {percent:.0f}%. Plug in now.", urgent=True)
        return Notice("battery", "Battery low", f"Battery at {percent:.0f}%. Time to find the charger.", urgent=True)

    def disks(self, readings: list[tuple[str, float]], today: date) -> list[Notice]:
        out = []
        if self.disk_full <= 0:
            return out
        for folder, percent in readings:
            if percent >= self.disk_full and self._disk_told.get(folder) != today:
                self._disk_told[folder] = today
                out.append(Notice(f"disk:{folder}", "Disk almost full", f"The disk holding {folder} is {percent:.0f}% full.", urgent=True))
        return out

    def updates(self, count: int, today: date) -> Notice | None:
        if count <= 0 or self._updates_told == today:
            return None
        self._updates_told = today
        plural = "s" if count != 1 else ""
        return Notice("updates", "Updates waiting", f"{count} system update{plural} waiting to install.")
