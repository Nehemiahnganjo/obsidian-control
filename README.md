# obsidian-control

> Your terminal, in your pocket.

A Telegram bot that bridges your phone to AI coding agents running on your machine. Send a message — it lands in `kiro-cli`. The response comes back to your chat. No SSH clients, no VPNs, no fumbling with terminals on glass.

```
You (Telegram) ──► Bot ──► kiro-cli (Rick agent) ──► Your machine
                    ◄──────────────────────────────────────────────
```

---

## Features

- **Multi-backend** — kiro-cli, Claude Code, Aider, Anthropic API, OpenAI-compatible, Ollama, custom CLI
- **Multi-session** — named sessions with independent context, working dir, and backend
- **Rick Sanchez agent** — real answers, zero patience, actually useful
- **9 MCP servers** — filesystem, git, fetch, GitHub, SQLite, Puppeteer, memory, Brave search, sequential thinking
- **File transfer** — upload files to your machine from Telegram; browse and download back
- **Session persistence** — context survives restarts via `session_state.json`
- **Inline buttons** — one-tap shortcuts for system status, CPU, IP, uptime
- **Single-user auth** — numeric Telegram user ID whitelist, everyone else rejected instantly
- **Systemd managed** — starts on login, restarts on failure, logs to journal

---

## Documentation

| Doc | Description |
|---|---|
| [Docs Index](docs/README.md) | Overview of all guides |
| [Architecture](docs/architecture.md) | How all the pieces connect, file layout, request lifecycle |
| [Setup](docs/setup.md) | Full installation guide from scratch |
| [Configuration](docs/configuration.md) | Every `.env` variable explained |
| [MCP Servers](docs/mcp-servers.md) | All 9 MCP servers — what they do and how to configure them |
| [Agents](docs/agents.md) | Rick agent, built-in agents, creating your own |
| [Troubleshooting](docs/troubleshooting.md) | Common issues and fixes |

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/Nehemiahnganjo/obsidian-control.git ~/kiro-telegram-bridge
cd ~/kiro-telegram-bridge

# 2. Python deps
python3 -m venv .venv
.venv/bin/pip install "python-telegram-bot==21.11.1" "python-dotenv==1.0.1" "requests==2.32.3"

# 3. Config
mkdir -p ~/obsidian_control
cp .env.example ~/obsidian_control/.env
chmod 600 ~/obsidian_control/.env
nano ~/obsidian_control/.env   # set TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USER_ID

# 4. Agent
mkdir -p ~/.kiro/agents && cp rick.json ~/.kiro/agents/rick.json

# 5. MCP servers
mkdir -p ~/.kiro/settings && cp mcp.json ~/.kiro/settings/mcp.json

# 6. Service
cp kiro-bridge.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now kiro-bridge.service
```

Full guide: [docs/setup.md](docs/setup.md)

---

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Menu with quick-action buttons |
| `/status` | Current session, backend, working dir |
| `/new <name> [backend] [cwd]` | Create or switch to a named session |
| `/backend [name]` | Switch AI backend for current session |
| `/files` | Browse and download files in working dir |
| _(any text)_ | Sent to the active AI backend |
| _(file upload)_ | Saved to working directory |

---

## Backends

| Key | What runs |
|---|---|
| `kiro` | kiro-cli (default) |
| `claude_code` | Claude Code CLI |
| `aider` | Aider coding agent |
| `anthropic_api` | Direct Anthropic API |
| `openai` | OpenAI or compatible endpoint |
| `ollama` | Local Ollama models |
| `custom` | Any CLI via `CUSTOM_CMD_TEMPLATE` |

---

## Project Layout

```
~/kiro-telegram-bridge/    ← engine (this repo)
    main.py                ← bridge logic
    rick.json              ← Rick agent definition
    mcp.json               ← MCP server config template
    kiro-bridge.service    ← systemd service template
    .env.example           ← config template
    docs/                  ← full documentation

~/obsidian_control/        ← your config (NOT in git)
    .env                   ← credentials and settings
    session_state.json     ← persisted session state
    bridge.log             ← runtime logs
    data.db                ← SQLite database

~/.kiro/agents/rick.json   ← active agent (global kiro config)
~/.kiro/settings/mcp.json  ← active MCP config (global kiro config)
```

---

## Requirements

- Python 3.10+
- Node.js + npm (MCP servers)
- `uv` / `uvx` (Python MCP servers)
- `python-telegram-bot==21.11.1`
- `requests`, `python-dotenv`
- kiro-cli
- A Telegram bot token

---

*Built for personal use. One user, one machine, full control.*
