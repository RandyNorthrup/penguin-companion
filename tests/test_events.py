import json

from penguin_companion import cli, events


def test_aliases():
    assert events.normalize("Stop") == "done"
    assert events.normalize("needs_you") == "needs-you"
    assert events.normalize("nonsense") is None


def test_claude_code_hook_payloads():
    note = events.event_from(None, {"hook_event_name": "Notification", "message": "Claude needs your permission to use Bash"}, source="claude")
    assert note == {"type": "event", "event": "needs-you", "source": "claude", "message": "Claude needs your permission to use Bash"}
    assert events.event_from(None, {"hook_event_name": "UserPromptSubmit", "prompt": "hi"})["event"] == "working"
    assert events.event_from(None, {"hook_event_name": "Stop"})["event"] == "done"
    assert events.event_from(None, {"hook_event_name": "PreToolUse"}) is None


def test_codex_notify_payload():
    payload = {"type": "agent-turn-complete", "last-assistant-message": "All tests pass."}
    msg = events.event_from(None, payload, source="codex")
    assert (msg["event"], msg["message"]) == ("done", "All tests pass.")


def test_explicit_event_wins_and_unknown_is_dropped():
    assert events.event_from("working", {"hook_event_name": "Stop"})["event"] == "working"
    assert events.event_from("bogus") is None


def test_parse_lines_skips_garbage():
    data = b'{"type": "show"}\nnot json\n[1]\n{"type": "say", "text": "hi"}\n'
    assert [m["type"] for m in events.parse_lines(data)] == ["show", "say"]


def test_notify_sends_codex_style_trailing_json(monkeypatch):
    sent = []
    monkeypatch.setattr(events, "send", lambda m, timeout=0.5: sent.append(m) or True)
    monkeypatch.delenv(events.INTERNAL_ENV, raising=False)
    payload = json.dumps({"type": "agent-turn-complete", "last-assistant-message": "Done!"})
    assert cli.notify(["--source", "codex", payload]) == 0
    assert sent == [{"type": "event", "event": "done", "source": "codex", "message": "Done!"}]


def test_notify_ignores_the_companions_own_questions(monkeypatch):
    sent = []
    monkeypatch.setattr(events, "send", lambda m, timeout=0.5: sent.append(m) or True)
    monkeypatch.setenv(events.INTERNAL_ENV, "1")
    assert cli.notify(["done", "--source", "claude"]) == 0
    assert sent == []


def test_send_without_a_running_companion(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert events.send({"type": "show"}) is False


def test_hooks_snippets_are_valid():
    text = cli.hooks("claude")
    config = json.loads(text.split("\n", 1)[1])
    assert set(config["hooks"]) == {"UserPromptSubmit", "Notification", "Stop"}
    assert "notify" in cli.hooks("codex") and "needs-you" in cli.hooks("any")
