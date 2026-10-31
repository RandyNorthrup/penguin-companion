# Penguin companion

An electric penguin that lives along the bottom of your screen. It wanders
about, naps when you ignore it, peeks out from behind the taskbar, and helps:

- **Ask it anything.** Click it and type. It answers with whichever AI you
  already use: Claude Code, Codex, Gemini CLI or Grok through their own
  command-line tools (your login, no extra keys), or the Anthropic, OpenAI,
  Gemini, xAI or OpenRouter APIs, or anything that speaks the OpenAI API.
- **Keeps an eye on your AI agents.** It thinks while an agent works,
  charges up on long jobs, flaps for attention when one needs your approval,
  and hops when it's done. Any agent that can run a command from a hook works.
- **Reminders and timers**, typed the way you'd say them: *remind me in 20m to
  stretch*, *remind me at 3pm to call Sam*, *timer 10 min for the pasta*,
  *focus 50*. No AI needed.
- **Breaks.** A nudge after an hour at the screen. Locking the screen for five
  minutes counts as a break.
- **Heads-ups.** A low battery, a disk filling up, system updates waiting.

It runs on Linux, Windows and macOS (Python and Qt).

## Run it

You need Python 3.11 or newer and PyQt6:

```sh
git clone https://github.com/RandyNorthrup/penguin-companion
cd penguin-companion
python3 -m pip install PyQt6 psutil   # or on Debian/Ubuntu: sudo apt install python3-pyqt6 python3-psutil
./penguin-companion                   # Windows: py penguin-companion
```

`psutil` is optional; it reads the battery on Windows and macOS. To run it from
anywhere, install it with `pipx install .`, or on Linux and macOS link the
launcher onto your PATH: `ln -s "$PWD/penguin-companion" ~/.local/bin/`.

The first time, it asks what it should be called. To start it when you log in,
right-click it and tick **Start when I log in**.

## Using it

| You                        | It                                                                  |
| -------------------------- | ------------------------------------------------------------------- |
| Click it                   | Opens the ask box (or wakes up, or answers an alert)                |
| Drag it                    | Comes along; let go and it drops back to the taskbar               |
| Right-click it, or the tray icon | The menu: ask, remind, focus timer, reminders, brain, walk, hide, settings |
| Click the tray icon        | Hides it, or brings it back                                         |

In the ask box, besides questions, it understands *help*, *status* (battery,
disks, reminders), *hide*, *new chat*, and the reminder, timer and focus
phrases above.

## Brains

| Name            | What                                     | Needs                                  |
| --------------- | ---------------------------------------- | -------------------------------------- |
| `claude`        | Claude Code, `claude -p`                 | Claude Code installed and signed in    |
| `codex`         | Codex, `codex exec`                      | Codex installed and signed in          |
| `gemini`        | Gemini CLI                               | Gemini CLI installed and signed in     |
| `grok`          | Grok CLI, `grok --prompt-file`           | Grok CLI installed and signed in       |
| `anthropic-api` | Anthropic Messages API (`claude-opus-5-5`) | `ANTHROPIC_API_KEY`                  |
| `openai-api`    | OpenAI API                               | `OPENAI_API_KEY`                       |
| `gemini-api`    | Gemini API                               | `GEMINI_API_KEY`                       |
| `xai-api`       | xAI API                                  | `XAI_API_KEY`                          |
| `openrouter`    | OpenRouter                               | `OPENROUTER_API_KEY`                   |

With `brain = "auto"` it uses the first one available, in that order; the
**Brain** menu picks one for good. Add your own in the settings: any command
that reads a question and prints an answer, or any HTTP endpoint that speaks
the Anthropic or OpenAI API, with its own model.

Command-line brains run in an empty folder of their own, with Claude Code's
tools turned off and Codex in its read-only sandbox, so a question can't touch
your files. The Codex and Gemini CLI presets follow those tools' documented
flags but haven't been tried yet; the Claude Code and Grok ones have. The API
models are the defaults in the settings file; change `model` to pick another.

A program started at login may not see API keys set in your shell's startup
file. Put them where your desktop session reads them (`~/.profile` on most
Linux desktops), or set `api_key` for that brain in the settings.

## Agent reactions

Agents tell the penguin what they're doing with `penguin-companion notify`.
Print the setup for yours with `penguin-companion hooks claude`, `hooks codex`,
or `hooks any`:

- **Claude Code** runs it from its `UserPromptSubmit`, `Notification` and
  `Stop` hooks, and passes along what it's waiting for ("Claude needs your
  permission to use Bash").
- **Codex** calls it through `notify` when a turn finishes.
- **Anything else** (Gemini CLI, Grok, Aider, a CI script): run
  `penguin-companion notify working|needs-you|done|success|error --source NAME`.

| Event       | The penguin                                                        |
| ----------- | ------------------------------------------------------------------ |
| `working`   | Thinks; after a minute, charges up                                 |
| `needs-you` | Flaps and says so until you click OK                               |
| `done`      | Hops and says it finished, with the agent's last words if it sent them |
| `success`   | Fires a little beam                                               |
| `error`     | Says something went wrong                                         |

If the penguin isn't running, `notify` does nothing and returns at once, so
hooks never slow an agent down. The AI tools the penguin runs for your own
questions carry `PENGUIN_COMPANION_INTERNAL=1`, so their hooks don't make it
react to itself.

`penguin-companion say TEXT` and `penguin-companion remind in 10m to stretch`
work from any script too.

## Settings

`config.toml`, created on first run, with every setting explained: the name,
the penguin's size, walking, how soon it naps, brains, break and focus
lengths, and the heads-up thresholds. **Edit settings…** in the menu opens it,
and **Reload settings** applies it. It lives in `~/.config/penguin-companion/`
on Linux, `~/Library/Application Support/penguin-companion/` on macOS and
`%APPDATA%\penguin-companion\` on Windows, next to `state.json`, where it keeps
its name, reminders and spot on the screen.

## How it's put together

The penguin and its message bubbles are drawn inside one see-through window
over the screen, so moving them never moves a window. Clicks go through it
everywhere except the penguin and its bubble: on X11 through an input shape, on
Windows and macOS by letting the window take the mouse only while the pointer
is over them. On Wayland desktops it runs through XWayland, since Wayland
doesn't let a window place itself or stay above the others. The ask box is a
small window of its own, as it needs the keyboard.

| File                          | What                                                     |
| ----------------------------- | -------------------------------------------------------- |
| `penguin_companion/behavior.py` | What it does from moment to moment (no Qt; tested)     |
| `penguin_companion/penguin.py`  | The stage window: drawing, the mouse                   |
| `penguin_companion/bubble.py`   | Message bubbles and the ask box                        |
| `penguin_companion/app.py`      | Ties it together: menu, tray, reminders, heads-ups, hooks |
| `penguin_companion/brains.py`   | The AI brains                                          |
| `penguin_companion/reminders.py`, `heads_up.py`, `events.py` | Reminders and breaks, system checks, the hook protocol |
| `art/`                        | The character sheet, the image prompts and the slicing tools ([art/README.md](art/README.md)) |

Tested on KDE Plasma 6.4 (Wayland). Windows and macOS run the same code and
its tests in CI; a look on a real Windows or Mac desktop is still to come.

```sh
python3 -m pip install pytest
python3 -m pytest
```
