"""Brains: whichever AI answers the questions you ask the penguin.

A brain is either a command-line tool you're already signed in to (Claude
Code, Codex, Gemini CLI, Grok...) or an HTTP API: the Anthropic Messages API,
or the OpenAI chat completions API that most other providers also speak.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from PyQt6.QtCore import QByteArray, QObject, QProcess, QProcessEnvironment, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from . import paths
from .events import INTERNAL_ENV

# The order "auto" tries them in: the tools you're signed in to first, since
# they cost nothing extra, then the APIs whose key is set.
PRESETS: dict[str, dict] = {
    "claude": {"type": "command", "label": "Claude Code", "command": ["claude", "-p", "--tools", "", "--no-session-persistence"]},
    "codex": {
        "type": "command",
        "label": "Codex",
        "command": ["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only", "--output-last-message", "{output_file}", "-"],
    },
    "gemini": {"type": "command", "label": "Gemini CLI", "command": ["gemini"]},
    "grok": {"type": "command", "label": "Grok", "command": ["grok", "--prompt-file", "{prompt_file}"]},
    "anthropic-api": {"type": "anthropic", "label": "Anthropic API", "model": "claude-opus-5-5", "api_key_env": "ANTHROPIC_API_KEY"},
    "openai-api": {"type": "openai", "label": "OpenAI API", "url": "https://api.openai.com/v1", "model": "gpt-5-mini", "api_key_env": "OPENAI_API_KEY"},
    "gemini-api": {
        "type": "openai",
        "label": "Gemini API",
        "url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.5-flash",
        "api_key_env": "GEMINI_API_KEY",
    },
    "xai-api": {"type": "openai", "label": "xAI API", "url": "https://api.x.ai/v1", "model": "grok-4", "api_key_env": "XAI_API_KEY"},
    "openrouter": {"type": "openai", "label": "OpenRouter", "url": "https://openrouter.ai/api/v1", "model": "openrouter/auto", "api_key_env": "OPENROUTER_API_KEY"},
}

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2026-10-21"
# Models that take server-side refusal fallbacks ("fallbacks": "default").
_FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07")


class BrainError(Exception):
    pass


@dataclass
class Brain:
    name: str
    type: str
    label: str = ""
    command: list[str] = field(default_factory=list)
    url: str = ""
    model: str = ""
    api_key_env: str = ""
    api_key: str = ""
    effort: str = "low"

    def key(self) -> str:
        return self.api_key or (os.environ.get(self.api_key_env, "") if self.api_key_env else "")

    def available(self) -> bool:
        if self.type == "command":
            return bool(self.command) and shutil.which(self.command[0]) is not None
        if self.type in ("anthropic", "openai"):
            return bool(self.key()) or not self.api_key_env
        return False

    def why_not(self) -> str:
        if self.type == "command":
            return f"{self.command[0] if self.command else 'command'} not found"
        return f"{self.api_key_env} not set"


def load_brains(ai_config: dict) -> dict[str, Brain]:
    """The built-in brains with your overrides, then your own, in auto order."""
    user = ai_config.get("brains") or {}
    out: dict[str, Brain] = {}
    for name in list(PRESETS) + [n for n in user if n not in PRESETS]:
        spec = {**PRESETS.get(name, {}), **(user.get(name) or {})}
        if spec.get("type") not in ("command", "anthropic", "openai"):
            continue
        out[name] = Brain(
            name=name,
            type=spec["type"],
            label=spec.get("label") or name,
            command=[str(a) for a in spec.get("command", [])],
            url=spec.get("url", ""),
            model=spec.get("model", ""),
            api_key_env=spec.get("api_key_env", ""),
            api_key=spec.get("api_key", ""),
            effort=spec.get("effort", "low"),
        )
    return out


def choose(brains: dict[str, Brain], configured: str, picked: str | None) -> Brain | None:
    """The brain to ask: the one picked from the menu, else the configured one,
    else the first available."""
    for name in (picked, configured):
        if name and name != "auto" and name in brains and brains[name].available():
            return brains[name]
    return next((b for b in brains.values() if b.available()), None)


def system_prompt(name: str) -> str:
    return (
        f"You are {name}, a small electric-penguin desktop companion. Answer the person's "
        "question helpfully and briefly: a few sentences unless they ask for more. Plain text or "
        "light Markdown. You can't see their screen or files and you can't run anything."
    )


def text_prompt(system: str, history: list[tuple[str, str]], question: str) -> str:
    """One block of text for command-line brains, which take a single prompt."""
    parts = [system]
    if history:
        parts.append("The conversation so far:")
        for q, a in history:
            parts += [f"Person: {q}", f"You: {a}"]
    parts.append(f"Person: {question}")
    return "\n\n".join(parts)


def _messages(history: list[tuple[str, str]], question: str) -> list[dict]:
    out = []
    for q, a in history:
        out += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
    out.append({"role": "user", "content": question})
    return out


def anthropic_request(brain: Brain, system: str, history, question: str) -> tuple[dict, dict]:
    headers = {"x-api-key": brain.key(), "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"}
    body = {
        "model": brain.model,
        "max_tokens": 16000,
        "system": system,
        "messages": _messages(history, question),
        "output_config": {"effort": brain.effort},
    }
    if brain.model in _FALLBACK_MODELS:
        headers["anthropic-beta"] = _FALLBACK_BETA
        body["fallbacks"] = "default"
    return headers, body


def openai_request(brain: Brain, system: str, history, question: str) -> tuple[dict, dict]:
    headers = {"content-type": "application/json"}
    if brain.key():
        headers["authorization"] = f"Bearer {brain.key()}"
    body = {"model": brain.model, "messages": [{"role": "system", "content": system}] + _messages(history, question)}
    return headers, body


def _error_message(data: dict) -> str | None:
    err = data.get("error")
    if isinstance(err, dict):
        return err.get("message") or err.get("type")
    if isinstance(err, str):
        return err
    return None


def parse_anthropic(data: dict) -> str:
    if data.get("type") == "error" or "error" in data:
        raise BrainError(_error_message(data) or "the API returned an error")
    if data.get("stop_reason") == "refusal":
        raise BrainError("it declined to answer that one")
    text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text").strip()
    if not text:
        raise BrainError("the answer came back empty")
    return text


def parse_openai(data: dict) -> str:
    if "error" in data:
        raise BrainError(_error_message(data) or "the API returned an error")
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise BrainError("the answer wasn't in the expected shape") from None
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    text = (content or "").strip()
    if not text:
        raise BrainError("the answer came back empty")
    return text


def clean_output(text: str) -> str:
    return _ANSI.sub("", text).strip()


class Asker(QObject):
    """Asks one brain one question at a time, without blocking the penguin."""

    answered = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)
        self._proc: QProcess | None = None
        self._reply: QNetworkReply | None = None
        self._output_file: Path | None = None
        self._prompt_file: Path | None = None
        self._brain: Brain | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._timed_out)

    def busy(self) -> bool:
        return self._proc is not None or self._reply is not None

    def ask(self, brain: Brain, system: str, history: list[tuple[str, str]], question: str, timeout_s: float) -> None:
        self.cancel()
        self._brain = brain
        self._timer.start(int(timeout_s * 1000))
        if brain.type == "command":
            self._run(brain, text_prompt(system, history, question))
        elif brain.type == "anthropic":
            self._post(brain.url or ANTHROPIC_URL, *anthropic_request(brain, system, history, question))
        else:
            self._post(brain.url.rstrip("/") + "/chat/completions", *openai_request(brain, system, history, question))

    def cancel(self) -> None:
        self._timer.stop()
        if self._proc is not None:
            proc, self._proc = self._proc, None
            proc.finished.disconnect()
            proc.errorOccurred.disconnect()
            proc.kill()
            proc.waitForFinished(1000)
            proc.deleteLater()
        if self._reply is not None:
            reply, self._reply = self._reply, None
            reply.finished.disconnect()
            reply.abort()
            reply.deleteLater()
        self._drop_output_file()

    # -- command-line brains

    def _run(self, brain: Brain, prompt: str) -> None:
        args, use_stdin = [], True
        for arg in brain.command[1:]:
            if "{output_file}" in arg:
                self._output_file = self._temp("answer-")
                arg = arg.replace("{output_file}", str(self._output_file))
            if "{prompt_file}" in arg:
                self._prompt_file = self._temp("question-")
                self._prompt_file.write_text(prompt, encoding="utf-8")
                use_stdin = False
                arg = arg.replace("{prompt_file}", str(self._prompt_file))
            if "{prompt}" in arg:
                use_stdin = False
                arg = arg.replace("{prompt}", prompt)
            args.append(arg)
        proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert(INTERNAL_ENV, "1")
        env.insert("NO_COLOR", "1")
        proc.setProcessEnvironment(env)
        proc.setWorkingDirectory(str(paths.work_dir()))
        proc.finished.connect(self._process_finished)
        proc.errorOccurred.connect(self._process_error)
        self._proc = proc
        proc.start(shutil.which(brain.command[0]) or brain.command[0], args)
        if use_stdin:
            proc.write(prompt.encode("utf-8"))
        proc.closeWriteChannel()

    def _process_finished(self, code: int, _status) -> None:
        proc, self._proc = self._proc, None
        self._timer.stop()
        if proc is None:
            return
        out = bytes(proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        err = clean_output(bytes(proc.readAllStandardError()).decode("utf-8", errors="replace"))
        proc.deleteLater()
        if self._output_file is not None:
            try:
                out = self._output_file.read_text(encoding="utf-8") or out
            except OSError:
                pass
        self._drop_output_file()
        answer = clean_output(out)
        if code == 0 and answer:
            self.answered.emit(answer)
            return
        detail = err.splitlines()[-1] if err else (f"exit code {code}" if code else "no answer")
        self.failed.emit(f"{self._brain.label} didn't answer ({detail}).")

    def _process_error(self, error) -> None:
        if error == QProcess.ProcessError.FailedToStart and self._proc is not None:
            self.cancel()
            self.failed.emit(f"Couldn't start {self._brain.command[0]}.")

    def _temp(self, prefix: str) -> Path:
        fd, name = tempfile.mkstemp(prefix=prefix, suffix=".txt", dir=paths.work_dir())
        os.close(fd)
        return Path(name)

    def _drop_output_file(self) -> None:
        for path in (self._output_file, self._prompt_file):
            if path is not None:
                path.unlink(missing_ok=True)
        self._output_file = self._prompt_file = None

    # -- HTTP brains

    def _post(self, url: str, headers: dict, body: dict) -> None:
        req = QNetworkRequest(QUrl(url))
        for name, value in headers.items():
            req.setRawHeader(name.encode(), value.encode())
        reply = self._nam.post(req, QByteArray(json.dumps(body).encode("utf-8")))
        reply.finished.connect(self._reply_finished)
        self._reply = reply

    def _reply_finished(self) -> None:
        reply, self._reply = self._reply, None
        self._timer.stop()
        if reply is None:
            return
        raw = bytes(reply.readAll())
        network_error = reply.errorString() if reply.error() != QNetworkReply.NetworkError.NoError else None
        reply.deleteLater()
        try:
            data = json.loads(raw) if raw else {}
        except ValueError:
            data = {}
        try:
            if not data and network_error:
                raise BrainError(network_error)
            parse = parse_anthropic if self._brain.type == "anthropic" else parse_openai
            self.answered.emit(parse(data))
        except BrainError as exc:
            self.failed.emit(f"{self._brain.label}: {exc}.")

    def _timed_out(self) -> None:
        label = self._brain.label if self._brain else "The brain"
        self.cancel()
        self.failed.emit(f"{label} took too long to answer.")
