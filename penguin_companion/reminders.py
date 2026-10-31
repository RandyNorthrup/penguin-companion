"""Reminders, timers, focus sessions and break nudges, and the plain-English
ways people ask for them ("remind me in 20m to stretch", "timer 10 min")."""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ten": 10,
    "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "half an": 0.5, "half a": 0.5,
}
_NUMBER = r"\d+(?:\.\d+)?"
_WORD = r"half an?|an?|one|two|three|four|five|ten|fifteen|twenty|thirty|forty|fifty"
_UNIT = r"seconds?|secs?|minutes?|mins?|hours?|hrs?|hr|days?|[smhd]"
# A word amount needs a space before its unit, so "and" is never "an d(ay)".
_PART = rf"(?:(?<![\d.]){_NUMBER}\s*|(?<![a-z])(?:{_WORD})\s+)(?:{_UNIT})(?![a-z])"
_PART_RE = re.compile(rf"(?:(?<![\d.])(?P<number>{_NUMBER})\s*|(?<![a-z])(?P<word>{_WORD})\s+)(?P<unit>{_UNIT})(?![a-z])", re.I)
_DURATIONS = rf"{_PART}(?:\s*(?:,|and)?\s*{_PART})*"
_IN_RE = re.compile(rf"\bin\s+(?P<d>{_DURATIONS})", re.I)
_LEADING_RE = re.compile(rf"^\s*(?:for\s+)?(?P<d>{_DURATIONS}|\d+)", re.I)
_CLOCK_RE = re.compile(
    r"\b(?:(?P<tomorrow>tomorrow)\s+)?(?P<at>at\s+)?"
    r"(?:(?P<word>noon|midday|midnight)|(?P<h>\d{1,2})(?::(?P<min>\d{2}))?\s*(?P<ap>[ap]\.?m\.?)?)"
    r"(?![\w:])(?:\s+(?P<tomorrow2>tomorrow))?",
    re.I,
)
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def seconds_in(text: str) -> float:
    """Total seconds in a phrase like "1 hour and 30 minutes" or "1h30m"."""
    total = 0.0
    for m in _PART_RE.finditer(text):
        value = float(m.group("number")) if m.group("number") else _WORDS[" ".join(m.group("word").lower().split())]
        total += value * _UNIT_SECONDS[m.group("unit")[0].lower()]
    return total


def _cut(text: str, m: re.Match) -> str:
    return " ".join((text[: m.start()] + " " + text[m.end() :]).split())


def parse_when(text: str, now: datetime) -> tuple[datetime, str] | None:
    """When the text means, and the text with that part taken out."""
    m = _IN_RE.search(text)
    if m:
        secs = seconds_in(m.group("d"))
        if secs > 0:
            return now + timedelta(seconds=secs), _cut(text, m)
    for m in _CLOCK_RE.finditer(text):
        if not (m.group("at") or m.group("min") or m.group("ap") or m.group("word")):
            continue
        word = (m.group("word") or "").lower()
        if word:
            hour, minute = (0, 0) if word == "midnight" else (12, 0)
        else:
            hour, minute = int(m.group("h")), int(m.group("min") or 0)
            ap = (m.group("ap") or "").lower()
            if ap.startswith("p") and hour < 12:
                hour += 12
            elif ap.startswith("a") and hour == 12:
                hour = 0
        if hour > 23 or minute > 59:
            continue
        due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if m.group("tomorrow") or m.group("tomorrow2"):
            due += timedelta(days=1)
        elif due <= now:
            due += timedelta(days=1)
        return due, _cut(text, m)
    m = re.search(r"\btomorrow\b", text, re.I)
    if m:
        due = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        return due, _cut(text, m)
    return None


def _what(text: str) -> str:
    text = re.sub(r"^\s*(?:to|that|about|of|:|,)\s+", "", text.strip(), flags=re.I)
    return text.strip(" .!?,:")


@dataclass
class Command:
    kind: str  # "reminder", "timer", "focus", or "unclear" (a reminder without a time)
    due: datetime | None = None
    text: str = ""
    minutes: float | None = None


def parse_command(text: str, now: datetime) -> Command | None:
    """A reminder, timer or focus request typed in the ask box, if it is one."""
    t = text.strip()
    m = re.match(r"^(?:please\s+)?remind me\b[\s,:]*(?P<rest>.*)$", t, re.I | re.S)
    if m:
        when = parse_when(m.group("rest"), now)
        if when is None:
            return Command("unclear", text=_what(m.group("rest")))
        due, rest = when
        return Command("reminder", due, _what(rest) or "Reminder")
    m = re.match(r"^(?:set\s+(?:a\s+)?)?timer\b\s*(?P<rest>.*)$", t, re.I)
    if m:
        lead = _LEADING_RE.match(m.group("rest"))
        if lead:
            d = lead.group("d")
            secs = float(d) * 60 if d.isdigit() else seconds_in(d)
            if secs > 0:
                rest = m.group("rest")[lead.end() :]
                return Command("timer", now + timedelta(seconds=secs), _what(re.sub(r"^\s*for\s+", "", rest)) or "Timer")
        return None
    m = re.match(r"^(?:start\s+(?:a\s+)?)?focus(?:\s+(?:session|time|mode))?\b\s*(?P<rest>.*)$", t, re.I)
    if m:
        rest = m.group("rest").strip()
        if not rest:
            return Command("focus")
        lead = _LEADING_RE.match(rest)
        if lead:
            d = lead.group("d")
            minutes = float(d) if d.isdigit() else seconds_in(d) / 60
            if minutes > 0:
                return Command("focus", minutes=minutes)
    return None


def clock(when: datetime) -> str:
    return f"{(when.hour % 12) or 12}:{when.minute:02d} {'AM' if when.hour < 12 else 'PM'}"


def describe(due: float, now: float) -> str:
    """"in 5 min", "at 3:30 PM", "tomorrow at 9:00 AM"..."""
    delta = due - now
    if 0 <= delta < 3600:
        return f"in {max(1, round(delta / 60))} min"
    d, n = datetime.fromtimestamp(due), datetime.fromtimestamp(now)
    if d.date() == n.date():
        return f"at {clock(d)}"
    if d.date() == n.date() + timedelta(days=1):
        return f"tomorrow at {clock(d)}"
    return f"on {d:%a %b} {d.day} at {clock(d)}"


@dataclass
class Reminder:
    due: float
    text: str
    kind: str = "reminder"  # "reminder", "timer" or "focus"
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


class ReminderBook:
    def __init__(self, items: list[Reminder] | None = None):
        self.items: list[Reminder] = list(items or [])

    @classmethod
    def from_list(cls, data: list) -> "ReminderBook":
        items = []
        for entry in data or []:
            try:
                items.append(Reminder(float(entry["due"]), str(entry["text"]), str(entry.get("kind", "reminder")), str(entry.get("id") or uuid.uuid4().hex[:8])))
            except (KeyError, TypeError, ValueError):
                continue
        return cls(items)

    def to_list(self) -> list[dict]:
        return [asdict(r) for r in self.items]

    def add(self, due: float, text: str, kind: str = "reminder") -> Reminder:
        reminder = Reminder(due, text, kind)
        self.items.append(reminder)
        return reminder

    def cancel(self, rid: str) -> bool:
        before = len(self.items)
        self.items = [r for r in self.items if r.id != rid]
        return len(self.items) != before

    def pop_due(self, now: float) -> list[Reminder]:
        due = sorted((r for r in self.items if r.due <= now), key=lambda r: r.due)
        self.items = [r for r in self.items if r.due > now]
        return due

    def upcoming(self) -> list[Reminder]:
        return sorted(self.items, key=lambda r: r.due)

    def focus(self) -> Reminder | None:
        return next((r for r in self.items if r.kind == "focus"), None)


class BreakTracker:
    """Counts time at the screen and says when a break is due. Time away
    (locked screen, suspend) of five minutes or more counts as a break."""

    AWAY_IS_A_BREAK = 300

    def __init__(self, every_minutes: float, now: float):
        self.every = every_minutes * 60
        self.active_since = now
        self.snoozed_until = 0.0
        self.away_since: float | None = None

    def away(self, now: float) -> None:
        if self.away_since is None:
            self.away_since = now

    def back(self, now: float) -> None:
        if self.away_since is not None and now - self.away_since >= self.AWAY_IS_A_BREAK:
            self.took_break(now)
        self.away_since = None

    def took_break(self, now: float) -> None:
        self.active_since = now
        self.snoozed_until = 0.0

    def snooze(self, now: float, minutes: float) -> None:
        self.snoozed_until = now + minutes * 60

    def minutes_on(self, now: float) -> int:
        return int((now - self.active_since) // 60)

    def due(self, now: float) -> bool:
        return (
            self.every > 0
            and self.away_since is None
            and now - self.active_since >= self.every
            and now >= self.snoozed_until
        )
