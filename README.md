# Penguin companion

An electric penguin that lives along the bottom of your screen. It wanders
about, naps when you ignore it, peeks out from behind the taskbar, and helps:

- **Ask it anything.** Click it and type. It answers with the AI you already
  use: an AI command-line tool you're signed in to (Claude Code, Codex, Gemini
  CLI, Muse Code, Grok, GitHub Copilot CLI), a model server on your own
  computer (Ollama, LM Studio, llama.cpp, vLLM), or an API: Anthropic, OpenAI,
  Gemini, xAI, Meta, Mistral, DeepSeek, Groq, Together, Fireworks, Cerebras,
  Perplexity, OpenRouter, Amazon Bedrock, Azure, or anything else that speaks
  the OpenAI or Anthropic API.
- **Keeps an eye on your coding agents.** It thinks while an agent works,
  charges up on long jobs, flaps for attention when one needs your approval,
  and hops when it's done. It connects to Claude Code, Codex, Gemini CLI, Muse
  Code, Grok, GitHub Copilot CLI, Cursor, Cline, Qwen Code and Devin, and to
  anything else that can run a command.
- **Reminders and timers**, typed the way you'd say them: *remind me in 20m to
  stretch*, *remind me at 3pm to call Sam*, *timer 10 min for the pasta*,
  *focus 50*. No AI needed.
- **Breaks.** A nudge after an hour at the screen; locking the screen for five
  minutes counts as a break.
- **Heads-ups.** A low battery, a disk filling up, system updates waiting.

It runs on Linux, Windows and macOS.

## Install

You need Python 3.11 or newer.

```sh
pipx install git+https://github.com/RandyNorthrup/penguin-companion
penguin-companion
```

Without pipx: `python3 -m pip install --user git+https://github.com/RandyNorthrup/penguin-companion`.
Or run it from a clone, with PyQt6 installed (`python3 -m pip install PyQt6`, or
`sudo apt install python3-pyqt6` on Debian and Ubuntu):

```sh
git clone https://github.com/RandyNorthrup/penguin-companion
cd penguin-companion
./penguin-companion          # Windows: py penguin-companion
```

Agent hooks call `penguin-companion` by name, so if you run it from a clone,
put the launcher on your PATH: `ln -s "$PWD/penguin-companion" ~/.local/bin/`.
For battery levels on Windows and macOS, also install `psutil`.

The first time, it asks what it should be called. Right-click it and tick
**Start when I log in** to keep it around.

## Using it

| You                              | It                                                       |
| -------------------------------- | -------------------------------------------------------- |
| Click it                         | Opens the ask box (or wakes up, or answers an alert)     |
| Drag it                          | Comes along; let go and it drops back to the taskbar    |
| Right-click it, or the tray icon | The menu: ask, remind, focus timer, reminders, brain, AI agents, walk, hide, settings |
| Click the tray icon              | Hides it, or brings it back                              |

Besides questions, the ask box understands *help*, *status* (battery, disks,
reminders), *hide*, *new chat*, and the reminder, timer and focus phrases above.

## Brains: what answers your questions

**Automatic** (the default) uses the first of these it finds:

- an AI command-line tool you're signed in to: `claude`, `codex`, `gemini`,
  `muse`, `grok`, `copilot`. It runs in an empty folder of its own with its
  tools off or read-only, so a question can't touch your files;
- a model server running on this computer: Ollama, LM Studio, llama.cpp or
  vLLM, with whichever model it has loaded.

**APIs are billed per question, so Automatic never picks one**, even if its key
is set. Pick it under **Brain** in the menu, or name it in the settings:

| Brain            | Key in                     | Default model                |
| ---------------- | -------------------------- | ---------------------------- |
| `anthropic-api`  | `ANTHROPIC_API_KEY`        | `claude-opus-5-5`            |
| `openai-api`     | `OPENAI_API_KEY`           | `gpt-6.1-sol` (Responses API) |
| `gemini-api`     | `GEMINI_API_KEY`           | `gemini-3.8-flash`           |
| `xai-api`        | `XAI_API_KEY`              | `grok-4.7` (Responses API)   |
| `meta-api`       | `MODEL_API_KEY`            | `muse-spark-1.3`             |
| `mistral-api`    | `MISTRAL_API_KEY`          | `mistral-small-latest`       |
| `deepseek-api`   | `DEEPSEEK_API_KEY`         | `deepseek-v4-pro`            |
| `groq-api`       | `GROQ_API_KEY`             | `openai/gpt-oss-120b`        |
| `together-api`   | `TOGETHER_API_KEY`         | `moonshotai/Kimi-K3`         |
| `fireworks-api`  | `FIREWORKS_API_KEY`        | `accounts/fireworks/models/glm-5p3` |
| `cerebras-api`   | `CEREBRAS_API_KEY`         | `gpt-oss-120b`               |
| `perplexity-api` | `PERPLEXITY_API_KEY`       | `perplexity/sonar`, with web search |
| `openrouter`     | `OPENROUTER_API_KEY`       | `openrouter/auto`            |
| `bedrock-api`    | `AWS_BEARER_TOKEN_BEDROCK` and `AWS_REGION` | `global.openai.gpt-6.1-sol` |

Change any model, or add your own brain (any command that reads a question and
prints an answer, or any endpoint for the Anthropic Messages, OpenAI Responses
or OpenAI Chat Completions API, Azure included) in the settings file, which
has examples. The model names above were current in October 2026.

The Claude Code and Grok brains have been tried; the others follow their
tools' documented options.

## AI agents: let them tell the penguin what they're doing

Right-click the penguin, open **AI agents**, and tick the ones you use; or from
a terminal:

```sh
penguin-companion hooks                 # what's here and what's connected
penguin-companion hooks connect claude  # or: codex, gemini, muse, grok, copilot, cursor, cline, qwen, devin, all
penguin-companion hooks disconnect claude
penguin-companion hooks show cursor     # how to do it by hand
```

| Agent              | How it's connected                                                    |
| ------------------ | --------------------------------------------------------------------- |
| Claude Code        | A Claude Code plugin, installed with `claude plugin`                  |
| Codex              | Its `notify` program, in `~/.codex/config.toml`                       |
| Gemini CLI         | Hooks in `~/.gemini/settings.json`                                    |
| Muse Code          | A Muse plugin, installed and approved with `muse plugins`             |
| Grok               | Its own file, `~/.grok/hooks/penguin-companion.json`                  |
| GitHub Copilot CLI | Its own file, `~/.copilot/hooks/penguin-companion.json`               |
| Cursor             | Hooks in `~/.cursor/hooks.json`                                       |
| Cline              | Hook scripts in `~/Documents/Cline/Hooks` (turn on Cline's "Enable Hooks") |
| Qwen Code          | Hooks in `~/.qwen/settings.json`                                      |
| Devin CLI          | Hooks in `~/.config/devin/config.json`                                |

In Claude Code you can also add the plugin yourself:
`/plugin install penguin-companion --marketplace RandyNorthrup/penguin-companion`.

For anything else (Aider, Kiro, OpenCode, Amp, a CI script), have it run
`penguin-companion notify working|needs-you|done|success|error --source NAME`;
`penguin-companion hooks show any` has the details.

| Event       | The penguin                                                        |
| ----------- | ------------------------------------------------------------------ |
| `working`   | Thinks; after a minute, charges up                                 |
| `needs-you` | Flaps and says what the agent is waiting for, until you click OK   |
| `done`      | Hops and says it finished                                          |
| `success`   | Fires a little beam                                                |
| `error`     | Says something went wrong                                          |

`penguin-companion say TEXT` and `penguin-companion remind in 10m to stretch`
work from any script too.

## Privacy and security

- **Nothing is collected.** No telemetry, no accounts, no network calls of its
  own. The only thing that leaves your computer is a question you type, sent
  to the brain you chose. Conversations live in memory and are gone when the
  penguin quits or after 15 minutes idle.
- **Agents' replies stay off the screen** unless you set
  `agents.show_replies = true`; they can hold code or secrets you'd rather not
  have on show during a screen share. The penguin shows what an agent is
  waiting for, and never your prompts.
- **Connecting an agent is always your choice.** Each connection backs up the
  file it changes first (`<file>.penguin-backup-<time>`), touches only entries
  that run `penguin-companion`, refuses to edit a file it can't parse, never
  replaces something of yours (Codex allows only one `notify` program, Cline
  one script per event), and comes out again with `hooks disconnect`.
- **Hooks can't get in an agent's way.** `notify` prints nothing, always
  succeeds, finishes within about a second even if the agent never closes its
  input, and returns at once if the penguin isn't running. The AI tools the penguin runs for your own
  questions carry `PENGUIN_COMPANION_INTERNAL=1`, so their hooks don't make it
  react to itself.
- **Only you can talk to it.** Hooks reach it through a local socket (a named
  pipe on Windows) open to your user account alone; messages are size-limited.
- **Keys** are read from environment variables (or `${VAR}` in a header) and
  are never written to logs. API keys only travel over HTTPS; plain HTTP is
  allowed only to a server on this computer. Settings and state files are
  readable by you alone.
- **Links** in answers open in your browser only if they're web or mail
  links.

Found a security problem? Please open a private
[security advisory](https://github.com/RandyNorthrup/penguin-companion/security/advisories/new).

## Settings

`config.toml`, created on first run with every setting explained: the name,
size, walking, how soon it naps, brains, whether agents' replies show, break and
focus lengths, and heads-up thresholds. **Edit settings…** in the menu opens it;
**Reload settings** applies it. It lives in `~/.config/penguin-companion/` on
Linux, `~/Library/Application Support/penguin-companion/` on macOS and
`%APPDATA%\penguin-companion\` on Windows. Next to it, `state.json` keeps the
name, reminders and the penguin's spot on the screen.

## How it's put together

The penguin and its message bubbles are drawn inside one see-through window over
the screen, so moving them never moves a window: no lag, no trails. Clicks go
through that window everywhere except the penguin and its bubble (an X input
shape on X11, mouse tracking on Windows and macOS). On Wayland desktops it runs
through XWayland, since Wayland doesn't let a window place itself or stay above
the others. The ask box is a small window of its own, as it needs the keyboard.

| File                              | What                                                   |
| --------------------------------- | ------------------------------------------------------ |
| `penguin_companion/behavior.py`   | What it does from moment to moment (no Qt; tested)     |
| `penguin_companion/penguin.py`    | The stage window: drawing and the mouse                |
| `penguin_companion/bubble.py`     | Message bubbles and the ask box                        |
| `penguin_companion/app.py`        | Ties it together: menu, tray, reminders, heads-ups, hooks |
| `penguin_companion/brains.py`     | The AI brains                                          |
| `penguin_companion/agents.py`     | Connecting coding agents                               |
| `penguin_companion/integrations/` | The Claude Code plugin                                 |
| `art/`                            | The character, its image prompts and the slicing tools ([art/README.md](art/README.md)) |

Tested on KDE Plasma 6.4 (Wayland); CI runs the tests, including a headless run
of the whole app, on Linux, Windows and macOS with Python 3.11 and 3.15.

```sh
python3 -m pip install pytest ruff
python3 -m pytest && ruff check .
```

## License

MIT, for the code and the art. See [LICENSE](LICENSE).
