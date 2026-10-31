"""The running companion: the penguin, its bubbles and tray icon, and what it
keeps an eye on for you."""

from __future__ import annotations

import os
import shutil
import signal
import sys
import time
from datetime import date, datetime
from functools import partial

from PyQt6.QtCore import QObject, QPoint, QProcess, QTimer, QUrl, pyqtSlot
from PyQt6.QtGui import QActionGroup, QDesktopServices, QGuiApplication, QIcon
from PyQt6.QtNetwork import QLocalServer
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import autostart, brains, events, heads_up, paths, reminders
from .behavior import Behavior
from .bubble import AskBox
from .penguin import Stage
from .settings import State, load_config
from .sprites import Sprites

PRETTY = {"claude": "Claude", "codex": "Codex", "gemini": "Gemini", "grok": "Grok", "copilot": "Copilot", "agent": "Your agent"}
WORK_EXPIRES = 30 * 60  # forget an agent that said it was working but never finished

HELP = """\
**Click me** to ask anything, **drag me** anywhere, **right-click** for the menu.

I also understand, without any AI:
- *remind me in 20m to stretch* · *remind me at 3pm to call Sam*
- *timer 10 min for the pasta* · *focus 50*
- *status* — battery, disk, reminders
- *hide* — I'll duck behind the taskbar and peek out now and then
"""


def pretty(source: str) -> str:
    return PRETTY.get(source.lower(), source[:1].upper() + source[1:])


class Companion(QObject):
    def __init__(self, app: QApplication, server: QLocalServer):
        super().__init__()
        self.app = app
        self.server = server
        self.state = State.load()
        self.config, self.config_error = load_config()
        self.brains = brains.load_brains(self.config["ai"])
        self.reminders = reminders.ReminderBook.from_list(self.state.get("reminders", []))
        self.breaks = reminders.BreakTracker(self.config["breaks"]["every_minutes"], time.time())
        self.watcher = self._make_watcher()
        self.history: list[tuple[str, str]] = []
        self.agents: dict[str, tuple[str, float]] = {}  # source: (state, since)
        self._alert_key: str | None = None
        self._waiting: list = []  # messages held back while an alert is up
        self._asking_name = False
        self._question = ""
        self._last_wall = time.time()
        self._last_ask = 0.0
        self._update_counts: dict[str, int] = {}

        self.sprites = Sprites(paths.anim_dir(), int(self.config["size"]))
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.behavior = Behavior(
            self.sprites.anims(),
            now=time.monotonic(),
            x=float(self.state.get("x", screen.x() + screen.width() * 0.8)),
            walk=bool(self.config["walk"]),
            sleep_after=float(self.config["sleep_after_minutes"]) * 60,
            speed=int(self.config["size"]) * 0.4,
        )
        self.stage = Stage(self.sprites, self.behavior)
        self.ask_box = AskBox()
        self.asker = brains.Asker(self)

        self.stage.clicked.connect(self.on_click)
        self.stage.menu_requested.connect(self.show_menu)
        self.stage.head_moved.connect(self._follow)
        self.stage.message_closed.connect(self._message_closed)
        self.ask_box.closed.connect(self._ask_closed)
        self.ask_box.submitted.connect(self.submit)
        self.ask_box.reset_requested.connect(self._new_chat)
        self.asker.answered.connect(self._answered)
        self.asker.failed.connect(self._failed)
        self.server.newConnection.connect(self._accept)

        self.menu = QMenu()
        self.menu.aboutToShow.connect(self._fill_menu)
        self.tray = QSystemTrayIcon(QIcon(self.sprites.frame("idle", 0, False).pixmap))
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._tray_clicked)
        self.tray.show()
        self.app.setWindowIcon(self.tray.icon())

        self._watch_screen_lock()
        self._every(5_000, self._check_reminders)
        self._every(30_000, self._check_time)
        self._every(60_000, self._check_system)
        self._every(int(self.config["heads_up"]["updates_every_hours"] * 3600_000), self._check_updates)
        QTimer.singleShot(120_000, self._check_updates)
        QTimer.singleShot(1500, self._greet)

    # -- small helpers

    @property
    def name(self) -> str:
        return self.config["name"] or self.state.get("name") or "Penguin"

    def _every(self, ms: int, fn) -> None:
        timer = QTimer(self)
        timer.timeout.connect(fn)
        timer.start(max(1000, ms))

    def _make_watcher(self) -> heads_up.Watcher:
        h = self.config["heads_up"]
        return heads_up.Watcher(float(h["battery_low"]), float(h["battery_critical"]), float(h["disk_full_percent"]))

    def _brain(self) -> brains.Brain | None:
        return brains.choose(self.brains, self.config["ai"]["brain"], self.state.get("brain"))

    def _now(self) -> float:
        return time.monotonic()

    def _follow(self) -> None:
        if self.ask_box.isVisible():
            self.ask_box.place(self.stage.head_point())

    def save(self) -> None:
        self.state.set("x", round(self.behavior.x))
        self.state.set("reminders", self.reminders.to_list())
        self.state.save()

    # -- talking

    def say(self, title: str, text: str = "", buttons=None, timeout_s: float | None = 12) -> None:
        if self._alert_key is not None:  # don't talk over something that needs you
            self._later(partial(self.say, title, text, buttons, timeout_s))
            return
        self.stage.show_message(title, text, buttons, timeout_s)

    def alert(self, key: str, title: str, text: str, buttons=None) -> None:
        """Something needs you: the penguin waves its flippers until you answer."""
        if self._alert_key is not None:
            self._later(partial(self.alert, key, title, text, buttons))
            return
        self._alert_key = key
        self.behavior.set_hidden(False, self._now())
        self.behavior.set_alert(True, self._now())
        self.stage.show_message(title, text, buttons or [("OK", None)], None)

    def _later(self, show) -> None:
        self._waiting = (self._waiting + [show])[-5:]

    def _message_closed(self) -> None:
        if self._alert_key is not None:
            self._alert_key = None
            self.behavior.set_alert(False, self._now())
        if self._waiting:
            QTimer.singleShot(400, self._waiting.pop(0))

    def _greet(self) -> None:
        if self.config_error:
            self.say("I couldn't read my settings", f"`{self.config_error}`\n\nUsing the defaults for now.", timeout_s=30)
        elif not (self.config["name"] or self.state.get("name")):
            self._asking_name = True
            self.open_ask()
        else:
            self.say(f"Hi, I'm {self.name}!", "Click me to ask anything.", timeout_s=5)

    # -- clicks and the ask box

    def on_click(self) -> None:
        now = self._now()
        if self.behavior.alert:
            self.stage.dismiss_message()
        elif self.behavior.asleep:
            self.behavior.wake(now)
        elif self.behavior.hidden:
            self.set_hidden(False)
        elif self.ask_box.isVisible():
            self.ask_box.dismiss()
        else:
            self.open_ask()

    def open_ask(self, prefill: str = "") -> None:
        now = self._now()
        if self.behavior.hidden:
            self.set_hidden(False)
        self.behavior.wake(now)
        self.behavior.set_attending(True, now)
        self.stage.dismiss_message()
        if now - self._last_ask > 15 * 60:
            self.history.clear()
        self._last_ask = now
        anchor = self.stage.head_point()
        if self._asking_name:
            self.ask_box.open(
                anchor, "Hi! I'm your new desktop companion.", "Enter to save · Esc to decide later", "A name for me", text="What should I be called?"
            )
            return
        brain = self._brain()
        via = f"answers from {brain.label}" if brain else "no AI set up yet; reminders and timers still work"
        self.ask_box.open(anchor, f"Ask {self.name}", f"Enter to ask · Esc to close · {via}", "Ask anything, or: remind me in 20m to stretch", prefill=prefill)
        self.ask_box.set_resettable(bool(self.history))

    def _ask_closed(self) -> None:
        now = self._now()
        self._asking_name = False
        self.asker.cancel()
        self.behavior.set_thinking(False, now)
        self.behavior.set_talking(False, now)
        self.behavior.set_attending(False, now)

    def _new_chat(self) -> None:
        self.history.clear()
        self.ask_box.set_resettable(False)
        self.ask_box.set_answer("*New chat. Ask away.*")

    def submit(self, text: str) -> None:
        now = self._now()
        self._last_ask = now
        if self._asking_name:
            self._asking_name = False
            self.state.set("name", text.strip()[:40])
            self.state.save()
            self.ask_box.dismiss()
            self.behavior.react("hop", now)
            self.say(f"{self.name}! I love it.", HELP, timeout_s=25)
            return
        if self._local(text):
            return
        brain = self._brain()
        if brain is None:
            names = ", ".join(b.label for b in self.brains.values())
            self.ask_box.set_answer(
                f"I don't have an AI brain yet. Install one of these or set its API key: {names}. "
                "Then pick it from my menu under **Brain**.\n\n" + HELP
            )
            return
        self._question = text
        self.ask_box.set_answer(f"**You:** {text}\n\n*{brain.label} is thinking…*")
        self.behavior.set_thinking(True, now)
        self.asker.ask(brain, brains.system_prompt(self.name), self.history[-6:], text, float(self.config["ai"]["timeout_seconds"]))

    def _answered(self, answer: str) -> None:
        now = self._now()
        self.behavior.set_thinking(False, now)
        self.history.append((self._question, answer))
        self.ask_box.set_answer(f"**You:** {self._question}\n\n{answer}")
        self.ask_box.set_resettable(True)
        self.behavior.set_talking(True, now)
        QTimer.singleShot(int(min(max(len(answer) / 18, 2), 10) * 1000), lambda: self.behavior.set_talking(False, self._now()))

    def _failed(self, error: str) -> None:
        self.behavior.set_thinking(False, self._now())
        self.ask_box.set_answer(f"**You:** {self._question}\n\n*Hmm, that didn't work.* {error}")

    def _local(self, text: str) -> bool:
        """Reminders, timers and the like, handled without any AI."""
        now = self._now()
        command = reminders.parse_command(text, datetime.now())
        if command is not None:
            if command.kind == "unclear":
                self.ask_box.set_answer("When should I remind you? Try *remind me in 20m to stretch* or *remind me at 3pm to call Sam*.")
            elif command.kind == "focus":
                self.ask_box.dismiss()
                self.start_focus(command.minutes or float(self.config["focus"]["minutes"]))
            else:
                r = self.reminders.add(command.due.timestamp(), command.text, command.kind)
                self.save()
                when = reminders.describe(r.due, time.time())
                what = f"Timer set: **{r.text}**, done {when}." if r.kind == "timer" else f"I'll remind you {when}: **{r.text}**"
                self.ask_box.set_answer(what)
                self.behavior.react("hop", now)
            return True
        word = text.lower().strip(" ?!.")
        if word in ("help", "what can you do", "commands"):
            self.ask_box.set_answer(HELP)
        elif word in ("status", "battery", "system status", "how's my computer"):
            self.ask_box.set_answer(self._status())
        elif word in ("hide", "go hide", "go away"):
            self.ask_box.dismiss()
            self.set_hidden(True)
        elif word in ("new chat", "/new", "reset"):
            self._new_chat()
        else:
            return False
        return True

    def _status(self) -> str:
        lines = []
        battery = heads_up.read_battery()
        if battery:
            lines.append(f"- Battery: {battery[0]:.0f}%{' (plugged in)' if battery[1] else ''}")
        for folder, percent in heads_up.read_disks(heads_up.disk_folders()):
            lines.append(f"- Disk for {folder}: {percent:.0f}% full")
        upcoming = self.reminders.upcoming()
        for r in upcoming[:5]:
            lines.append(f"- {r.kind.capitalize()} {reminders.describe(r.due, time.time())}: {r.text}")
        if not upcoming:
            lines.append("- No reminders set")
        brain = self._brain()
        lines.append(f"- Brain: {brain.label if brain else 'none'}")
        return "\n".join(lines)

    # -- hiding

    def set_hidden(self, on: bool) -> None:
        self.behavior.set_hidden(on, self._now())
        if on:
            self.stage.dismiss_message()
            self.ask_box.dismiss()

    # -- reminders, timers, focus, breaks

    def start_focus(self, minutes: float) -> None:
        old = self.reminders.focus()
        if old:
            self.reminders.cancel(old.id)
        self.reminders.add(time.time() + minutes * 60, f"{minutes:g}-minute focus", "focus")
        self.save()
        self.behavior.react("hop", self._now())
        self.say("Focus time", f"{minutes:g} minutes. I'll keep quiet until then.", timeout_s=5)

    def stop_focus(self) -> None:
        focus = self.reminders.focus()
        if focus:
            self.reminders.cancel(focus.id)
            self.save()
            self.say("Focus stopped", timeout_s=3)

    def _check_reminders(self) -> None:
        now = time.time()
        due = self.reminders.pop_due(now)
        if not due:
            return
        self.save()
        rest = [r for r in due if r.kind != "focus"]
        if len(rest) < len(due):
            self.behavior.react("beam", self._now())
            minutes = float(self.config["focus"]["minutes"])
            self.say(
                "Focus session done!",
                "Nice work. Take five minutes away from the screen.",
                [("Another round", partial(self.start_focus, minutes)), ("Done", None)],
                timeout_s=None,
            )
        if not rest:
            return

        def line(r: reminders.Reminder) -> str:
            late = f" (due at {reminders.clock(datetime.fromtimestamp(r.due))})" if now - r.due > 120 else ""
            return r.text + late

        snooze = float(self.config["breaks"]["snooze_minutes"])
        buttons = [(f"Snooze {snooze:g} min", partial(self._snooze, rest, snooze)), ("Done", None)]
        if len(rest) == 1:
            title = "Time's up!" if rest[0].kind == "timer" else "Reminder"
            self.alert(f"reminder:{rest[0].id}", title, line(rest[0]), buttons)
        else:
            self.alert("reminders", "Reminders", "\n".join(f"- {line(r)}" for r in rest), buttons)

    def _snooze(self, due: list[reminders.Reminder], minutes: float) -> None:
        for r in due:
            self.reminders.add(time.time() + minutes * 60, r.text, r.kind)
        self.save()

    def _check_time(self) -> None:
        now = time.time()
        if now - self._last_wall > 300:  # the computer was asleep
            self.breaks.away(self._last_wall)
            self.breaks.back(now)
        self._last_wall = now
        mono = self._now()
        for source, (state, since) in list(self.agents.items()):
            if state == "working" and mono - since > WORK_EXPIRES:
                del self.agents[source]
        self._update_working()
        if self.breaks.due(now) and self.reminders.focus() is None and not self.stage.message_visible() and not self.ask_box.isVisible():
            minutes = self.breaks.minutes_on(now)
            snooze = float(self.config["breaks"]["snooze_minutes"])
            self.breaks.snooze(now, snooze)
            self.behavior.react("wave", mono)
            self.say(
                "Time for a break?",
                f"You've been at the screen for {minutes} minutes. Stand up, stretch, and look at something far away.",
                [("Taking one", partial(self.breaks.took_break, now)), (f"Snooze {snooze:g} min", None)],
                timeout_s=120,
            )

    def _watch_screen_lock(self) -> None:
        try:  # D-Bus: Linux and the BSDs; elsewhere suspend gaps stand in for it
            from PyQt6.QtDBus import QDBusConnection
        except ImportError:
            return
        bus = QDBusConnection.sessionBus()
        if bus.isConnected():
            bus.connect("org.freedesktop.ScreenSaver", "/ScreenSaver", "org.freedesktop.ScreenSaver", "ActiveChanged", self._screen_locked)

    @pyqtSlot(bool)
    def _screen_locked(self, locked: bool) -> None:
        now = time.time()
        if locked:
            self.breaks.away(now)
        else:
            self.breaks.back(now)
            self.behavior.wake(self._now())

    # -- heads-ups

    def _check_system(self) -> None:
        notices = []
        battery = self.watcher.battery(heads_up.read_battery())
        if battery:
            notices.append(battery)
        notices += self.watcher.disks(heads_up.read_disks(heads_up.disk_folders()), date.today())
        for notice in notices:
            self.alert(notice.key, notice.title, notice.text)

    def _check_updates(self) -> None:
        if not self.config["heads_up"]["updates"]:
            return
        checks = [
            ("apt", ["apt", "list", "--upgradable"], heads_up.count_apt),
            ("flatpak", ["flatpak", "remote-ls", "--updates", "--columns=application"], heads_up.count_flatpak),
        ]
        checks = [c for c in checks if shutil.which(c[1][0])]
        self._update_counts = {}
        for name, command, count in checks:
            proc = QProcess(self)
            proc.finished.connect(partial(self._updates_counted, proc, name, count, len(checks)))
            proc.start(command[0], command[1:])

    def _updates_counted(self, proc: QProcess, name: str, count, expected: int, code: int, _status) -> None:
        output = bytes(proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        proc.deleteLater()
        self._update_counts[name] = count(output) if code == 0 else 0
        if len(self._update_counts) == expected:
            notice = self.watcher.updates(sum(self._update_counts.values()), date.today())
            if notice and not self.stage.message_visible():
                self.behavior.react("wave", self._now())
                self.say(notice.title, notice.text, [("OK", None)], timeout_s=60)

    # -- messages from hooks and scripts

    def _accept(self) -> None:
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            buffer = bytearray()
            sock.readyRead.connect(lambda sock=sock, buffer=buffer: buffer.extend(bytes(sock.readAll())))
            sock.disconnected.connect(lambda sock=sock, buffer=buffer: self._received(sock, buffer))

    def _received(self, sock, buffer: bytearray) -> None:
        buffer.extend(bytes(sock.readAll()))
        sock.deleteLater()
        for message in events.parse_lines(bytes(buffer)):
            self.handle(message)

    def handle(self, message: dict) -> None:
        kind = message.get("type")
        now = self._now()
        if kind == "event" and message.get("event") in events.EVENTS:
            self._agent_event(message["event"], str(message.get("source") or "agent"), str(message.get("message") or ""))
        elif kind == "say" and message.get("text"):
            self.behavior.wake(now)
            self.behavior.react("talk", now)
            self.say(self.name, str(message["text"]), timeout_s=15)
        elif kind == "remind":
            command = reminders.parse_command("remind me " + str(message.get("text", "")), datetime.now())
            if command and command.kind == "reminder":
                r = self.reminders.add(command.due.timestamp(), command.text)
                self.save()
                self.say("Reminder set", f"{reminders.describe(r.due, time.time())}: {r.text}", timeout_s=6)
        elif kind == "show":
            self.set_hidden(False)
            self.behavior.poke(now)

    def _agent_event(self, event: str, source: str, text: str) -> None:
        now = self._now()
        label = pretty(source)
        key = f"agent:{source}"
        self.behavior.wake(now)
        if event == "working":
            self.agents[source] = ("working", now)
            if self._alert_key == key:
                self.stage.dismiss_message()
        elif event == "needs-you":
            self.agents[source] = ("needs-you", now)
            self.alert(key, f"{label} needs you", text or f"{label} is waiting for you.")
        else:
            self.agents.pop(source, None)
            if self._alert_key == key:
                self.stage.dismiss_message()
            snippet = text if len(text) <= 220 else text[:217].rstrip() + "…"
            if event == "done":
                self.behavior.react("hop", now)
                if not self.ask_box.isVisible():
                    self.say(f"{label} finished", snippet, timeout_s=8)
            elif event == "success":
                self.behavior.react("beam", now)
                self.say(f"{label}: success!", snippet, timeout_s=8)
            elif event == "error":
                self.say(f"{label} hit a problem", snippet or "Take a look when you can.", timeout_s=20)
        self._update_working()

    def _update_working(self) -> None:
        working = any(state == "working" for state, _ in self.agents.values())
        self.behavior.set_working(working, self._now())

    # -- menus

    def show_menu(self, pos: QPoint) -> None:
        self.menu.popup(pos)

    def _tray_clicked(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.set_hidden(not self.behavior.hidden)

    def _fill_menu(self) -> None:
        m = self.menu
        m.clear()
        m.addAction(f"Ask {self.name}…", self.open_ask)
        m.addAction("Remind me…", partial(self.open_ask, "remind me in "))
        focus = self.reminders.focus()
        if focus:
            left = max(1, round((focus.due - time.time()) / 60))
            m.addAction(f"Stop focus ({left} min left)", self.stop_focus)
        else:
            sub = m.addMenu("Focus timer")
            for minutes in sorted({15, 25, 50, int(self.config["focus"]["minutes"])}):
                sub.addAction(f"{minutes} minutes", partial(self.start_focus, minutes))
        upcoming = [r for r in self.reminders.upcoming() if r.kind != "focus"]
        if upcoming:
            sub = m.addMenu(f"Reminders ({len(upcoming)})")
            for r in upcoming:
                sub.addAction(f"✕  {reminders.describe(r.due, time.time())}: {r.text}", partial(self._cancel, r.id))
        m.addSeparator()
        self._brain_menu(m.addMenu("Brain"))
        walk = m.addAction("Walk around")
        walk.setCheckable(True)
        walk.setChecked(self.behavior.walk_enabled)
        walk.toggled.connect(self._set_walk)
        m.addAction("Come out" if self.behavior.hidden else "Hide (peek now and then)", partial(self.set_hidden, not self.behavior.hidden))
        login = m.addAction("Start when I log in")
        login.setCheckable(True)
        login.setChecked(autostart.enabled())
        login.toggled.connect(autostart.set_enabled)
        m.addSeparator()
        m.addAction("Edit settings…", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.config_file()))))
        m.addAction("Reload settings", self.reload)
        m.addAction("Quit", self.quit)

    def _brain_menu(self, sub: QMenu) -> None:
        group = QActionGroup(sub)
        current = self._brain()
        picked = self.state.get("brain")
        auto = sub.addAction(f"Automatic ({current.label if current else 'none found'})")
        auto.setCheckable(True)
        auto.setChecked(not picked)
        auto.triggered.connect(partial(self._pick_brain, None))
        group.addAction(auto)
        sub.addSeparator()
        for brain in self.brains.values():
            ok = brain.available()
            action = sub.addAction(brain.label if ok else f"{brain.label} ({brain.why_not()})")
            action.setCheckable(True)
            action.setEnabled(ok)
            action.setChecked(picked == brain.name)
            action.triggered.connect(partial(self._pick_brain, brain.name))
            group.addAction(action)

    def _pick_brain(self, name: str | None) -> None:
        self.state.set("brain", name)
        self.state.save()

    def _cancel(self, rid: str) -> None:
        self.reminders.cancel(rid)
        self.save()

    def _set_walk(self, on: bool) -> None:
        self.behavior.walk_enabled = on

    def reload(self) -> None:
        self.config, self.config_error = load_config()
        if self.config_error:
            self.say("I couldn't read my settings", f"`{self.config_error}`", timeout_s=30)
            return
        self.brains = brains.load_brains(self.config["ai"])
        self.watcher = self._make_watcher()
        self.breaks.every = float(self.config["breaks"]["every_minutes"]) * 60
        size = int(self.config["size"])
        self.sprites = Sprites(paths.anim_dir(), size)
        self.stage.set_sprites(self.sprites)
        self.behavior.walk_enabled = bool(self.config["walk"])
        self.behavior.sleep_after = float(self.config["sleep_after_minutes"]) * 60
        self.behavior.speed = size * 0.4
        self.say("Settings reloaded", timeout_s=3)

    def quit(self) -> None:
        self.save()
        self.tray.hide()
        self.stage.close_stage()
        self.app.quit()


def run() -> int:
    # On Wayland a window can't place itself or stay above other windows, so
    # the penguin runs through XWayland, where it can.
    if sys.platform.startswith("linux") and os.environ.get("XDG_SESSION_TYPE") == "wayland" and os.environ.get("DISPLAY") and "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "xcb"
    if events.send({"type": "show"}):
        print("The penguin is already running; it says hi.")
        return 0
    app = QApplication(sys.argv[:1])
    app.setApplicationName("penguin-companion")
    app.setApplicationDisplayName("Penguin companion")
    app.setQuitOnLastWindowClosed(False)
    server = QLocalServer()
    name = paths.server_name()
    QLocalServer.removeServer(name)
    if not server.listen(name):
        print(f"Couldn't open {name}: {server.errorString()}. Hooks won't reach the penguin.", file=sys.stderr)
    companion = Companion(app, server)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: companion.quit())
    try:
        return app.exec()
    finally:
        companion.save()
        server.close()
