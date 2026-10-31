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


def test_clean_keeps_only_known_short_strings():
    big = "x" * 10_000
    cleaned = events.clean({"type": "say", "text": big, "evil": {"nested": 1}, "source": 5})
    assert cleaned == {"type": "say", "text": "x" * 2000}


def test_notify_never_waits_on_an_open_stdin(monkeypatch):
    import os
    import time

    sent = []
    monkeypatch.setattr(events, "send", lambda m, timeout=0.5: sent.append(m) or True)
    monkeypatch.delenv(events.INTERNAL_ENV, raising=False)
    read_end, write_end = os.pipe()  # a hook runner that never closes stdin
    monkeypatch.setattr("sys.stdin", os.fdopen(read_end, "r"))
    started = time.monotonic()
    assert cli.notify(["done", "--source", "x", "--stdin"]) == 0
    assert time.monotonic() - started < 2 and sent[0]["event"] == "done"
    os.close(write_end)


def test_payload_messages_from_other_agents():
    assert events.event_from("done", {"lastAssistantMessage": "grok says"})["message"] == "grok says"
    assert events.event_from("done", {"prompt_response": "gemini says"})["message"] == "gemini says"
    assert events.event_from("needs-you", {"notification": {"message": "cline says"}})["message"] == "cline says"
    assert events.event_from("working", {"prompt": "my secret prompt"})["message"] == ""


def test_helpers_inside_an_agent_are_ignored():
    assert events.event_from("done", {"subagentType": "explore"}) is None


def test_borrowed_claude_hooks_are_relabelled(monkeypatch):
    monkeypatch.setenv("GROK_HOOK_EVENT", "stop")
    assert cli._real_source("claude") == "grok" and cli._real_source("codex") == "codex"
    monkeypatch.delenv("GROK_HOOK_EVENT")
    assert cli._real_source("claude") == "claude"
