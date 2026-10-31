from datetime import date
from pathlib import Path

from penguin_companion.heads_up import Watcher, count_apt, count_flatpak, read_disks

TODAY = date(2026, 10, 31)


def test_battery_warns_once_per_level():
    w = Watcher(20, 10, 90)
    assert w.battery((50, False)) is None
    low = w.battery((19, False))
    assert low.title == "Battery low" and low.urgent
    assert w.battery((18, False)) is None
    assert w.battery((9, False)).title == "Battery almost empty"
    assert w.battery((8, False)) is None
    assert w.battery((15, False)) is None  # back up to "low" after critical: no repeat


def test_battery_resets_when_plugged_in():
    w = Watcher(20, 10, 90)
    assert w.battery((19, False))
    assert w.battery((19, True)) is None
    assert w.battery((19, False))


def test_battery_off_or_missing():
    assert Watcher(0, 10, 90).battery((5, False)) is None
    assert Watcher(20, 10, 90).battery(None) is None


def test_disk_once_a_day():
    w = Watcher(20, 10, 90)
    assert [n.key for n in w.disks([("/", 95), ("/home", 50)], TODAY)] == ["disk:/"]
    assert w.disks([("/", 96)], TODAY) == []
    assert len(w.disks([("/", 96)], date(2026, 11, 1))) == 1


def test_updates_once_a_day():
    w = Watcher(20, 10, 90)
    assert w.updates(0, TODAY) is None
    assert w.updates(3, TODAY).text == "3 system updates waiting to install."
    assert w.updates(4, TODAY) is None
    assert w.updates(1, date(2026, 11, 1)).text == "1 system update waiting to install."


def test_counts():
    apt = "Listing...\nfoo/questing-updates 1.2 amd64 [upgradable from: 1.1]\nbar/questing 2 all [upgradable from: 1]\n"
    assert count_apt(apt) == 2
    assert count_flatpak("org.a.App\n\norg.b.App\n") == 2


def test_read_disks_skips_duplicates_and_missing(tmp_path):
    (tmp_path / "sub").mkdir()
    readings = read_disks([tmp_path, tmp_path / "sub", Path("/definitely/not/here")])
    assert len(readings) == 1 and 0 <= readings[0][1] <= 100
