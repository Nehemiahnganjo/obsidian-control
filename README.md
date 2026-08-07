# obsidian-control

> Your terminal, in your pocket.

A Telegram bot that acts as a bridge between your phone and AI coding agents running on your machine. Send a message from Telegram — it lands in `kiro-cli` (or any other backend you configure). The response comes straight back to your chat. No SSH clients, no VPNs, no fumbling with terminals on a phone screen.

---

## How It Works

```
You (Telegram) ──► Bot ──► kiro-cli (or other backend) ──► Your machine
                    ◄──────────────────────────────────────
```

1. You send a message to your private Telegram bot
2. The bridge authenticates you by numeric user ID (nobody else can use it)
3. Your message is forwarded to the configured AI backend as a subprocess call
4. The output is cleaned, optionally trimmed, and sent back as a Telegram message
5. Session state is persisted — context survives restarts

Everything runs as a `systemd` user service. It starts on login, restarts on failure, and logs to journal.

---

## Features

- **Multi-backend** — switch between `kiro-cli`, Claude Code, Aider, Anthropic API, OpenAI-compatible endpoints, Ollama, or a custom CLI template
- **Multi-session** — named sessions with independent context, working directory, and backend per session
- **Session persistence** — `session_state.json` survives restarts; your conversation context is never lost
- **File transfer** — upload files from Telegram to your machine; browse and download files back
- **Inline buttons** — one-tap shortcuts for system status, CPU/RAM, IP address, uptime
- **Response filtering** — `smart` (auto-trim), `verbose` (full output), or `brief` (first line only)
- **Auth guard** — single allowed Telegram user ID; everyone else gets rejected instantly
- **ANSI stripping** — terminal colour codes are cleaned before sending

---

## Backends

| Key | What it runs |
|---|---|
| `kiro` | `kiro-cli chat` (default) |
| `claude_code` | Claude Code CLI (`claude -p`) |
| `aider` | Aider repo-aware coding agent |
| `anthropic_api` | Direct Anthropic API (no CLI needed) |
| `openai` | OpenAI or any OpenAI-compatible endpoint |
| `ollama` | Local Ollama models |
| `custom` | Any CLI via `CUSTOM_CMD_TEMPLATE` in `.env` |

Switch backends per-session with `/backend` in the bot.

---

## Project Layout

```
~/kiro-telegram-bridge/      # engine — code and venv
    main.py
    .venv/

~/obsidian_control/          # your customisations
    .env                     # credentials and config
    session_state.json       # persisted session state
    bridge.log               # runtime logs
```

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/Nehemiahnganjo/obsidian-control.git ~/kiro-telegram-bridge
cd ~/kiro-telegram-bridge
python3 -m venv .venv
.venv/bin/pip install "python-telegram-bot==21.11.1" "python-dotenv==1.0.1" "requests==2.32.3"
```

### 2. Configure

```bash
mkdir -p ~/obsidian_control
cp ~/kiro-telegram-bridge/.env.example ~/obsidian_control/.env
nano ~/obsidian_control/.env
```

Minimum required:

```env
TELEGRAM_BOT_TOKEN=your_token_from_botfather
TELEGRAM_ALLOWED_USER_ID=your_numeric_telegram_id
BRIDGE_DIR=/home/youruser/obsidian_control
KIRO_WORKDIR=/home/youruser
```

Get your bot token from [@BotFather](https://t.me/BotFather).  
Get your user ID from [@userinfobot](https://t.me/userinfobot).

### 3. Systemd service

```bash
mkdir -p ~/.config/systemd/user
cp kiro-bridge.service ~/.config/systemd/user/
# edit the paths inside if needed
systemctl --user daemon-reload
systemctl --user enable --now kiro-bridge.service
```

### 4. Verify

```bash
systemctl --user status kiro-bridge.service
journalctl --user -u kiro-bridge.service -f
```

---

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Show menu with quick-action buttons |
| `/status` | Current session info, backend, working dir |
| `/new <name> [backend] [cwd]` | Create or switch to a named session |
| `/backend [name]` | Switch backend for current session |
| `/files` | Browse and download files in working dir |
| _(any text)_ | Forwarded to the active AI backend |
| _(file upload)_ | Saves file to working dir |

---

## Environment Variables

```env
# Required
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_USER_ID=

# Paths
KIRO_WORKDIR=/home/void
BRIDGE_DIR=/home/void/obsidian_control

# Backend
AGENT_BACKEND=kiro
KIRO_CLI_PATH=/home/void/.local/bin/kiro-cli

# Tuning
AGENT_TIMEOUT=180
RESPONSE_MODE=smart        # smart | verbose | brief
MAX_FILE_SIZE=20971520     # 20MB

# Optional API keys
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.1
```

---

## Logs

```bash
# Live journal
journalctl --user -u kiro-bridge.service -f

# File log
tail -f ~/obsidian_control/bridge.log
```

---

## Requirements

- Python 3.10+
- `python-telegram-bot==21.11.1`
- `requests`
- `python-dotenv`
- A Telegram bot token
- At least one AI backend (e.g. `kiro-cli`)

---

*Built for personal use. One user, one machine, full control.*
