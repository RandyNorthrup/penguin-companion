"""The whole companion, headless: build it, poke it, check it reacts."""

import os
import subprocess
import sys
import tempfile
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEventLoop, QTimer  # noqa: E402
from PyQt6.QtNetwork import QLocalServer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


def spin(seconds: float) -> None:
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


@pytest.fixture
def companion(tmp_path, monkeypatch):
    for var in ("XDG_CONFIG_HOME", "XDG_STATE_HOME", "APPDATA"):
        monkeypatch.setenv(var, str(tmp_path / var))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    # socket paths are limited to ~100 characters, so keep this one short
    run = tempfile.mkdtemp(prefix="pc-", dir=None if sys.platform == "win32" else "/tmp")
    monkeypatch.setenv("XDG_RUNTIME_DIR", run)
    from penguin_companion import agents, app as appmod, paths
    from penguin_companion.settings import State

    monkeypatch.setattr(agents, "_run_json", lambda argv, what: [])  # never run a real agent's command line

    State(paths.state_file(), {"name": "Sparky", "x": 600}).save()
    qapp = QApplication.instance() or QApplication([])
    qapp.setQuitOnLastWindowClosed(False)
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    QLocalServer.removeServer(paths.server_name())
    assert server.listen(paths.server_name()), server.errorString()
    c = appmod.Companion(qapp, server)
    yield c
    c.quit()
    server.close()


def test_greets_and_reacts_to_agents(companion):
    c = companion
    spin(1.8)
    assert c.stage.message_visible() and "Sparky" in c.stage.bubble.title
    c.handle({"type": "event", "event": "working", "source": "claude", "message": ""})
    assert c.behavior.working_since is not None
    c.handle({"type": "event", "event": "needs-you", "source": "claude", "message": "Approve the deploy?"})
    assert c.behavior.alert and c.stage.bubble.title == "Claude needs you"
    # something else to say waits until the alert is answered
    c.handle({"type": "event", "event": "done", "source": "codex", "message": "All tests pass."})
    assert c.stage.bubble.title == "Claude needs you" and len(c._waiting) == 1
    c.handle({"type": "event", "event": "done", "source": "claude", "message": "Deployed."})
    assert not c.behavior.alert and c.behavior.working_since is None
    spin(0.6)
    assert c.stage.message_visible()


def test_a_hook_reaches_it(companion):
    """A separate process, as a hook would be, says something and hears back."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]);"
        "from penguin_companion import events;"
        "sys.exit(0 if events.send({'type': 'say', 'text': 'hello from a hook'}, timeout=5) else 1)"
    )
    proc = subprocess.Popen([sys.executable, "-c", code, root])
    deadline = time.monotonic() + 20
    while proc.poll() is None and time.monotonic() < deadline:
        spin(0.05)
    assert proc.returncode == 0
    spin(0.2)
    assert companion.stage.bubble.title == "Sparky" and "hello from a hook" in companion.stage.bubble.doc.toPlainText()


def test_local_commands_and_reminders(companion):
    c = companion
    c.open_ask()
    assert c.ask_box.isVisible()
    c.submit("remind me in 1 second to stretch")
    assert "stretch" in c.ask_box.answer.toPlainText()
    c.submit("status")
    assert "Brain:" in c.ask_box.answer.toPlainText()
    c.ask_box.dismiss()
    spin(5.5)
    assert c.behavior.alert and c.stage.bubble.title == "Reminder"
    c.stage.dismiss_message()
    assert not c.behavior.alert


def test_hide_menu_and_reload(companion):
    c = companion
    c.set_hidden(True)
    spin(1.0)
    assert c.behavior.hidden
    c.set_hidden(False)
    c._fill_menu()
    labels = [a.text() for a in c.menu.actions() if a.text()]
    assert labels[0] == "Ask Sparky…" and "Quit" in labels
    c.reload()
    assert c.stage.message_visible()
