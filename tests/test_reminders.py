from datetime import datetime, timedelta

import pytest

from penguin_companion.reminders import BreakTracker, ReminderBook, describe, parse_command, parse_when, seconds_in

NOW = datetime(2026, 10, 31, 14, 0, 0)


@pytest.mark.parametrize(
    "text, seconds",
    [
        ("20m", 1200),
        ("20 minutes", 1200),
        ("1 hour and 30 minutes", 5400),
        ("1h30m", 5400),
        ("half an hour", 1800),
        ("an hour", 3600),
        ("90 secs", 90),
        ("2 days", 172800),
    ],
)
def test_seconds_in(text, seconds):
    assert seconds_in(text) == seconds


def test_months_are_not_minutes():
    assert seconds_in("5 months") == 0


@pytest.mark.parametrize(
    "text, due, what",
    [
        ("remind me in 20m to stretch", NOW + timedelta(minutes=20), "stretch"),
        ("remind me to call Sam in 2 hours", NOW + timedelta(hours=2), "call Sam"),
        ("remind me at 3pm to call Sam", NOW.replace(hour=15), "call Sam"),
        ("remind me at 15:30 about the build", NOW.replace(hour=15, minute=30), "the build"),
        ("remind me at 9am to water plants", NOW.replace(hour=9) + timedelta(days=1), "water plants"),
        ("remind me tomorrow at 8:15 am that it's trash day", NOW.replace(hour=8, minute=15) + timedelta(days=1), "it's trash day"),
        ("remind me at noon to eat", NOW.replace(hour=12) + timedelta(days=1), "eat"),
        ("Remind me tomorrow to renew the domain", (NOW + timedelta(days=1)).replace(hour=9), "renew the domain"),
    ],
)
def test_reminders(text, due, what):
    cmd = parse_command(text, NOW)
    assert cmd.kind == "reminder"
    assert cmd.due == due
    assert cmd.text == what


def test_reminder_without_a_time_is_unclear():
    assert parse_command("remind me to buy milk", NOW).kind == "unclear"


def test_plain_numbers_are_not_times():
    assert parse_when("buy 3 apples", NOW) is None


def test_timers():
    cmd = parse_command("timer 10 min for the pasta", NOW)
    assert (cmd.kind, cmd.due, cmd.text) == ("timer", NOW + timedelta(minutes=10), "the pasta")
    assert parse_command("set a timer for 5", NOW).due == NOW + timedelta(minutes=5)
    assert parse_command("timer", NOW) is None


def test_focus():
    assert parse_command("focus", NOW).minutes is None
    assert parse_command("focus 50", NOW).minutes == 50
    assert parse_command("start a focus session for 1 hour", NOW).minutes == 60


def test_questions_are_not_commands():
    assert parse_command("what is a closure in python?", NOW) is None
    assert parse_command("focused reading tips?", NOW) is None


def test_book_pops_due_in_order_and_round_trips():
    book = ReminderBook()
    b = book.add(200, "second")
    a = book.add(100, "first")
    book.add(900, "later", "focus")
    assert [r.text for r in book.pop_due(250)] == ["first", "second"]
    assert book.focus().text == "later"
    again = ReminderBook.from_list(book.to_list() + [{"bad": 1}])
    assert [r.text for r in again.upcoming()] == ["later"]
    assert not again.cancel(a.id) and not again.cancel(b.id)


def test_describe():
    now = NOW.timestamp()
    assert describe(now + 300, now) == "in 5 min"
    assert describe(now + 2 * 3600, now) == "at 4:00 PM"
    assert describe((NOW + timedelta(hours=20)).timestamp(), now) == "tomorrow at 10:00 AM"


def test_breaks():
    t = BreakTracker(60, now=0)
    assert not t.due(3599)
    assert t.due(3600)
    t.snooze(3600, 10)
    assert not t.due(3601) and t.due(3600 + 600)
    t.away(4000)
    assert not t.due(5000)
    t.back(4000 + 301)  # five minutes away counts as a break
    assert t.active_since == 4301 and not t.due(4400)


def test_short_time_away_is_not_a_break():
    t = BreakTracker(60, now=0)
    t.away(100)
    t.back(200)
    assert t.active_since == 0


def test_breaks_off():
    assert not BreakTracker(0, now=0).due(10**9)
