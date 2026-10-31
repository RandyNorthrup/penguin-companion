import json
import sys
import tomllib

import pytest

from penguin_companion import agents


@pytest.fixture(autouse=True)
def homes(tmp_path, monkeypatch):
    """Every agent's settings live in a temporary home; no real command-line tool is ever run."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / ".state"))
    for var in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "GEMINI_CLI_HOME", "GROK_HOME", "COPILOT_HOME"):
        monkeypatch.delenv(var, raising=False)

    def no_real_tools(argv, what):
        raise AssertionError(f"tried to run {argv}")

    monkeypatch.setattr(agents, "_run_json", no_real_tools)
    monkeypatch.setattr(agents.shutil, "which", lambda name: f"/usr/bin/{name}")
    return tmp_path


def backups(path):
    return sorted(path.parent.glob(path.name + ".penguin-backup-*"))


# -- settings files in Claude Code's shape (Gemini, Qwen, Devin)


def test_gemini_keeps_your_hooks_and_settings():
    gemini = agents.Gemini()
    path = gemini.config_path()
    path.parent.mkdir(parents=True)
    mine = {"type": "command", "command": "my-linter"}
    path.write_text(json.dumps({"security": {"auth": "oauth"}, "hooks": {"AfterAgent": [{"hooks": [mine]}], "BeforeTool": [{"matcher": "x", "hooks": [mine]}]}}))
    gemini.connect()
    data = json.loads(path.read_text())
    assert gemini.connected() and data["security"] == {"auth": "oauth"}
    assert data["hooks"]["BeforeTool"] == [{"matcher": "x", "hooks": [mine]}]
    assert data["hooks"]["AfterAgent"][0] == {"hooks": [mine]} and len(data["hooks"]["AfterAgent"]) == 2
    ours = data["hooks"]["AfterAgent"][1]["hooks"][0]
    assert "notify done --source gemini --stdin" in ours["command"] and ours["timeout"] == 5000 and ours["name"] == "penguin-done"
    assert len(backups(path)) == 1


def test_connect_twice_adds_nothing_and_disconnect_restores():
    qwen = agents.Qwen()
    path = qwen.config_path()
    path.parent.mkdir(parents=True)
    original = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "mine"}]}]}, "theme": "dark"}
    path.write_text(json.dumps(original))
    qwen.connect()
    qwen.connect()
    data = json.loads(path.read_text())
    assert sum(len(v) for v in data["hooks"].values()) == 4
    assert data["hooks"]["Notification"][0]["matcher"] == "permission_prompt"
    qwen.disconnect()
    assert json.loads(path.read_text()) == original and not qwen.connected()


def test_without_a_settings_file():
    devin = agents.Devin()
    devin.connect()
    assert devin.connected()
    devin.disconnect()
    assert json.loads(devin.config_path().read_text()) == {}


def test_broken_json_is_left_alone():
    gemini = agents.Gemini()
    path = gemini.config_path()
    path.parent.mkdir(parents=True)
    path.write_text("{ not json")
    with pytest.raises(agents.AgentError):
        gemini.connect()
    assert path.read_text() == "{ not json" and not backups(path)


# -- Codex's notify line

CODEX = """# my codex settings
model = "gpt-6.1-sol"

[tui]
notifications = true

[mcp_servers.docs]
command = "docs-server"
"""


def test_codex_connect_puts_notify_at_the_top_level():
    codex = agents.Codex()
    path = codex.config_path()
    path.parent.mkdir(parents=True)
    path.write_text(CODEX)
    codex.connect()
    data = tomllib.loads(path.read_text())
    assert data["model"] == "gpt-6.1-sol" and data["tui"] == {"notifications": True} and data["mcp_servers"]["docs"]["command"] == "docs-server"
    assert data["notify"][-4:] == ["notify", "done", "--source", "codex"]
    codex.connect()
    assert path.read_text().count("notify = [") == 1
    codex.disconnect()
    assert tomllib.loads(path.read_text()) == tomllib.loads(CODEX) and not codex.connected()


def test_codex_never_replaces_someone_elses_notify():
    codex = agents.Codex()
    path = codex.config_path()
    path.parent.mkdir(parents=True)
    path.write_text('notify = ["my-notifier"]\n')
    with pytest.raises(agents.AgentError, match="takes only one"):
        codex.connect()
    assert path.read_text() == 'notify = ["my-notifier"]\n' and not backups(path)


# -- files of our own (Grok, Copilot)


@pytest.mark.parametrize("agent", [agents.Grok(), agents.Copilot()], ids=lambda a: a.name)
def test_own_hooks_file(agent):
    neighbour = agent.config_path().with_name("someone-else.json")
    neighbour.parent.mkdir(parents=True)
    neighbour.write_text("{}")
    agent.connect()
    data = json.loads(agent.config_path().read_text())
    assert agent.connected() and f"--source {agent.name}" in json.dumps(data)
    assert {"UserPromptSubmit", "Stop"} <= set(data["hooks"])
    agent.disconnect()
    assert not agent.config_path().exists() and neighbour.exists()


# -- Cursor's flat hooks list


def test_cursor_merges_into_its_hooks_file():
    cursor = agents.Cursor()
    path = cursor.config_path()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"version": 1, "hooks": {"stop": [{"command": "./audit.sh"}]}}))
    cursor.connect()
    data = json.loads(path.read_text())
    assert data["hooks"]["stop"][0] == {"command": "./audit.sh"} and len(data["hooks"]["stop"]) == 2
    assert "notify working --source cursor" in data["hooks"]["beforeSubmitPrompt"][0]["command"]
    cursor.disconnect()
    assert json.loads(path.read_text()) == {"version": 1, "hooks": {"stop": [{"command": "./audit.sh"}]}}


# -- Cline's hook scripts


def test_cline_scripts_and_your_own_are_safe():
    cline = agents.Cline()
    cline.config_path().mkdir(parents=True)
    cline.connect()
    script = cline._file("TaskComplete")
    words = script.read_text().replace("'", "").split()
    assert cline.connected() and words[words.index("notify") :][:4] == ["notify", "done", "--source", "cline"]
    if sys.platform != "win32":
        assert script.stat().st_mode & 0o111
    cline.disconnect()
    assert not script.exists()
    cline._file("TaskComplete").write_text("#!/bin/sh\necho mine\n")
    with pytest.raises(agents.AgentError, match="already have"):
        cline.connect()
    assert cline._file("TaskComplete").read_text() == "#!/bin/sh\necho mine\n" and not cline._file("UserPromptSubmit").exists()


# -- plugins managed by the agent itself (Claude Code, Muse)


class FakeClaude:
    def __init__(self, installed=None, markets=()):
        self.plugins = installed or []
        self.markets = list(markets)
        self.calls = []

    def __call__(self, argv, what):
        self.calls.append(argv[1:4])
        if argv[1:3] == ["plugin", "list"]:
            return self.plugins
        if argv[1:4] == ["plugin", "marketplace", "list"]:
            return [{"name": m} for m in self.markets]
        if argv[1:4] == ["plugin", "marketplace", "add"]:
            self.markets.append("penguin-companion")
        if argv[1:3] == ["plugin", "install"]:
            self.plugins = [{"id": argv[3], "enabled": True}]
        if argv[1:3] == ["plugin", "enable"]:
            self.plugins = [{"id": argv[3], "enabled": True}]
        if argv[1:3] == ["plugin", "uninstall"]:
            self.plugins = []
        return {}


def test_claude_installs_its_plugin(monkeypatch):
    fake = FakeClaude()
    monkeypatch.setattr(agents, "_run_json", fake)
    claude = agents.ClaudeCode()
    assert claude.status() == "found"
    claude.connect()
    assert claude.connected() and ["plugin", "marketplace", "add"] in fake.calls and ["plugin", "install", "penguin-companion@penguin-companion"] in fake.calls
    claude.disconnect()
    assert not claude.connected()


def test_claude_switches_a_switched_off_plugin_back_on(monkeypatch):
    fake = FakeClaude(installed=[{"id": "penguin-companion@penguin-companion", "enabled": False}], markets=["penguin-companion"])
    monkeypatch.setattr(agents, "_run_json", fake)
    claude = agents.ClaudeCode()
    assert claude.status() == "installed but off"
    claude.connect()
    assert claude.connected() and ["plugin", "enable", "penguin-companion@penguin-companion"] in fake.calls
    assert not any(c[:2] == ["plugin", "install"] for c in fake.calls)


def test_claude_needs_the_penguin_on_path(monkeypatch):
    monkeypatch.setattr(agents, "_run_json", FakeClaude())
    monkeypatch.setattr(agents.shutil, "which", lambda name: None if name == "penguin-companion" else f"/usr/bin/{name}")
    with pytest.raises(agents.AgentError, match="PATH"):
        agents.ClaudeCode().connect()


def test_claude_plugin_files_match_the_installer():
    root = agents.ClaudeCode.marketplace_dir()
    market = json.loads((root / ".claude-plugin" / "marketplace.json").read_text())
    plugin_dir = root / market["plugins"][0]["source"]
    hooks = json.loads((plugin_dir / "hooks" / "hooks.json").read_text())["hooks"]
    assert market["name"] == "penguin-companion" and market["plugins"][0]["name"] == "penguin-companion"
    assert set(hooks) == {"UserPromptSubmit", "Notification", "Stop"}
    for groups in hooks.values():
        command = groups[0]["hooks"][0]["command"]
        assert command.startswith("penguin-companion notify ") and command.endswith("|| true")


def test_muse_plugin_manifest():
    manifest = agents.Muse().manifest()
    hooks = manifest["capabilities"]["hooks"]
    assert manifest["name"] == "penguin-companion" and manifest["compat"]["manifestDir"] == ".muse-plugin"
    assert {h["event"] for h in hooks} == {"UserPromptSubmit", "PermissionRequest", "Notification", "Stop", "Interrupt"}
    assert all(h["async"] and "notify" in h["command"] and "muse" in h["command"] for h in hooks)
    assert len({h["id"] for h in hooks}) == len(hooks)


def test_every_agent_explains_itself():
    names = [a.name for a in agents.AGENTS]
    assert len(names) == len(set(names))
    for agent in agents.AGENTS:
        assert agent.label and ("notify" in agent.manual() or "plugin" in agent.manual())
    assert "needs-you" in agents.generic()
