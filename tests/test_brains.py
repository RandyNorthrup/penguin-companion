import pytest

from penguin_companion import brains
from penguin_companion.brains import Brain, BrainError


def test_presets_and_overrides(monkeypatch):
    found = brains.load_brains(
        {"brains": {"grok": {"command": ["grok", "-p", "{prompt}", "--disable-web-search"]}, "mine": {"type": "command", "command": ["my-llm"]}, "broken": {"type": "nope"}}}
    )
    assert list(found)[0] == "claude" and {"codex", "gemini", "grok", "muse"} <= set(found)
    assert found["grok"].command[-1] == "--disable-web-search" and found["grok"].label == "Grok"
    assert "mine" in found and "broken" not in found


@pytest.fixture(autouse=True)
def nothing_running_here(monkeypatch):
    monkeypatch.setattr(brains, "reachable", lambda url, timeout=0.15: False)


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


def test_keys_only_go_over_https_or_to_this_computer():
    for url in ("https://api.example.com/v1", "http://localhost:11434/v1", "http://127.0.0.1:1234/v1", "http://[::1]:8080/v1"):
        brains.check_url(url)
    for url in ("http://api.example.com/v1", "http://192.168.1.5:11434/v1", "ftp://x", "http://localhost.evil.com/v1"):
        with pytest.raises(BrainError):
            brains.check_url(url)


def test_custom_headers_read_keys_from_the_environment(monkeypatch):
    monkeypatch.setenv("AZURE_KEY", "secret")
    brain = brains.load_brains({"brains": {"azure": {"type": "openai", "url": "https://x/v1", "model": "m", "headers": {"api-key": "${AZURE_KEY}"}, "extra": {"temperature": 0.2}}}})["azure"]
    headers, body = brains.openai_request(brain, "S", [], "q")
    assert headers["api-key"] == "secret" and body["temperature"] == 0.2 and "authorization" not in headers


def test_clean_output_strips_terminal_colours():
    assert brains.clean_output("\x1b[1;32mDone\x1b[0m\n") == "Done"


def test_auto_never_picks_a_paid_api(monkeypatch):
    monkeypatch.setattr(brains.shutil, "which", lambda name: None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    found = brains.load_brains({})
    assert found["openai-api"].available() and brains.choose(found, "auto", None) is None
    assert brains.choose(found, "auto", "openai-api").name == "openai-api"
    assert brains.choose(found, "openai-api", None).name == "openai-api"
    custom = brains.load_brains({"brains": {"mine": {"type": "openai", "url": "https://x/v1", "model": "m", "auto": True}}})
    assert brains.choose(custom, "auto", None).name == "mine"


def test_a_running_local_server_is_picked_with_its_own_model(monkeypatch):
    monkeypatch.setattr(brains.shutil, "which", lambda name: None)
    monkeypatch.setattr(brains, "reachable", lambda url, timeout=0.15: "11434" in url)
    found = brains.load_brains({})
    chosen = brains.choose(found, "auto", None)
    assert chosen.name == "ollama" and chosen.model == "auto"
    assert found["lmstudio"].why_not() == "not running"
    assert brains.first_model({"object": "list", "data": [{"id": "qwen3.8:27b"}]}) == "qwen3.8:27b"
    with pytest.raises(BrainError):
        brains.first_model({"data": []})


def test_bedrock_needs_its_region(monkeypatch):
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "t")
    monkeypatch.delenv("AWS_REGION", raising=False)
    bedrock = brains.load_brains({})["bedrock-api"]
    assert not bedrock.available() and "AWS_REGION" in bedrock.why_not()
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    assert bedrock.available()
    assert brains.endpoint(bedrock)[0] == "https://bedrock-runtime.us-west-2.amazonaws.com/openai/v1/chat/completions"


def test_responses_api():
    brain = Brain("x", "responses", url="https://api.x.ai/v1", model="grok-4.7", api_key="k")
    url, request, parse = brains.endpoint(brain)
    headers, body = request(brain, "SYS", [("hi", "hello")], "and?")
    assert url == "https://api.x.ai/v1/responses" and body["instructions"] == "SYS" and body["input"][-1] == {"role": "user", "content": "and?"}
    reply = {"output": [{"type": "reasoning"}, {"type": "message", "content": [{"type": "output_text", "text": " Hi! "}]}]}
    assert parse(reply) == "Hi!" and parse({"output_text": "yo"}) == "yo"
    with pytest.raises(BrainError, match="quota"):
        parse({"error": {"message": "quota"}})


def test_every_preset_is_well_formed():
    for brain in brains.load_brains({}).values():
        assert brain.label and brain.type in brains.TYPES
        if brain.type == "command":
            assert brain.command
        else:
            assert (brain.url or brain.type == "anthropic") and brain.model
            if not brain.local and brain.url:
                brains.check_url(brains.expand(brain.url).replace("..", ".x."))
                assert brain.api_key_env
