import pytest

from penguin_companion import brains
from penguin_companion.brains import Brain, BrainError


def test_presets_and_overrides(monkeypatch):
    found = brains.load_brains(
        {"brains": {"grok": {"command": ["grok", "-p", "{prompt}", "--disable-web-search"]}, "mine": {"type": "command", "command": ["my-llm"]}, "broken": {"type": "nope"}}}
    )
    assert list(found)[:4] == ["claude", "codex", "gemini", "grok"]
    assert found["grok"].command[-1] == "--disable-web-search" and found["grok"].label == "Grok"
    assert "mine" in found and "broken" not in found


def test_choose_prefers_picked_then_configured_then_first(monkeypatch):
    monkeypatch.setattr(brains.shutil, "which", lambda name: f"/bin/{name}" if name in ("grok", "my-llm") else None)
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    found = brains.load_brains({"brains": {"mine": {"type": "command", "command": ["my-llm"]}}})
    assert brains.choose(found, "auto", None).name == "grok"
    assert brains.choose(found, "mine", None).name == "mine"
    assert brains.choose(found, "mine", "grok").name == "grok"
    assert brains.choose(found, "claude", None).name == "grok"  # configured one missing: fall back
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert found["openai-api"].available()


def test_no_brain_at_all(monkeypatch):
    monkeypatch.setattr(brains.shutil, "which", lambda name: None)
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert brains.choose(brains.load_brains({}), "auto", None) is None


def test_text_prompt_carries_the_conversation():
    text = brains.text_prompt("SYS", [("hi", "hello!")], "and you?")
    assert text.startswith("SYS") and "Person: hi\n\nYou: hello!" in text and text.endswith("Person: and you?")


def test_anthropic_request_shape():
    brain = Brain("a", "anthropic", model="claude-opus-5-5", api_key="k")
    headers, body = brains.anthropic_request(brain, "SYS", [("q1", "a1")], "q2")
    assert headers["x-api-key"] == "k" and headers["anthropic-version"] == brains.ANTHROPIC_VERSION
    assert headers["anthropic-beta"] == "server-side-fallback-2026-07-01" and body["fallbacks"] == "default"
    assert body["system"] == "SYS" and [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]
    assert body["output_config"] == {"effort": "low"}
    _, other = brains.anthropic_request(Brain("h", "anthropic", model="claude-haiku-5-5", api_key="k"), "S", [], "q")
    assert "fallbacks" not in other


def test_parse_anthropic():
    data = {"content": [{"type": "thinking", "thinking": ""}, {"type": "text", "text": " Hi! "}], "stop_reason": "end_turn"}
    assert brains.parse_anthropic(data) == "Hi!"
    with pytest.raises(BrainError, match="declined"):
        brains.parse_anthropic({"content": [], "stop_reason": "refusal"})
    with pytest.raises(BrainError, match="bad key"):
        brains.parse_anthropic({"type": "error", "error": {"type": "authentication_error", "message": "bad key"}})


def test_openai_request_and_parse():
    headers, body = brains.openai_request(Brain("o", "openai", model="m", api_key="k"), "SYS", [], "q")
    assert headers["authorization"] == "Bearer k" and body["messages"][0] == {"role": "system", "content": "SYS"}
    assert "authorization" not in brains.openai_request(Brain("l", "openai", model="m"), "S", [], "q")[0]
    assert brains.parse_openai({"choices": [{"message": {"content": "yo"}}]}) == "yo"
    assert brains.parse_openai({"choices": [{"message": {"content": [{"type": "text", "text": "a"}, {"text": "b"}]}}]}) == "ab"
    with pytest.raises(BrainError):
        brains.parse_openai({"error": {"message": "quota"}})


def test_clean_output_strips_terminal_colours():
    assert brains.clean_output("\x1b[1;32mDone\x1b[0m\n") == "Done"
