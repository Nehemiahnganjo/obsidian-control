# Architecture Overview

## How It All Fits Together

```
┌─────────────────────────────────────────────────────────────────┐
│                        YOUR PHONE                               │
│                    Telegram App                                 │
│              (send messages, receive responses)                 │
└────────────────────────┬────────────────────────────────────────┘
                         │  HTTPS (Telegram API)
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Telegram Bot API                            │
│              (message routing, file transfer)                   │
└────────────────────────┬────────────────────────────────────────┘
                         │  polling (python-telegram-bot)
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│              main.py  (kiro-bridge.service)                     │
│                                                                 │
│   ┌──────────────┐    ┌───────────────┐    ┌────────────────┐  │
│   │ SessionMgr   │    │ Auth Guard    │    │ Msg Handlers   │  │
│   │              │    │               │    │                │  │
│   │ Persists     │    │ Single user   │    │ /start /new    │  │
│   │ sessions to  │    │ ID whitelist  │    │ /backend       │  │
│   │ session_     │    │ Rejects all   │    │ /files         │  │
│   │ state.json   │    │ others        │    │ text/files     │  │
│   └──────────────┘    └───────────────┘    └────────────────┘  │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │                    Backend Router                        │  │
│   │  kiro │ claude_code │ aider │ anthropic_api │ openai    │  │
│   │                     │ ollama │ custom                    │  │
│   └────────────────────┬────────────────────────────────────┘  │
└────────────────────────┼────────────────────────────────────────┘
                         │  subprocess call
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                   kiro-cli (default backend)                    │
│                                                                 │
│   ┌──────────────────────────────────────────────────────────┐ │
│   │                    rick agent                             │ │
│   │         ~/.kiro/agents/rick.json                         │ │
│   │         (Rick Sanchez personality prompt)                │ │
│   └──────────────────────────────────────────────────────────┘ │
│                                                                 │
│   ┌──────────────────────────────────────────────────────────┐ │
│   │                    MCP Servers                            │ │
│   │  filesystem │ git │ fetch │ github │ sqlite │ puppeteer  │ │
│   │  memory │ brave-search │ sequential-thinking             │ │
│   └──────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## File Layout

```
~/ (home)
├── kiro-telegram-bridge/          # Engine — code, venv, git repo
│   ├── main.py                    # The bridge (all logic)
│   ├── rick.json                  # Rick Sanchez agent definition
│   ├── mcp.json                   # MCP server configurations
│   ├── kiro-bridge.service        # Systemd service template
│   ├── .env.example               # Config template (no secrets)
│   ├── .gitignore                 # Keeps secrets out of git
│   ├── README.md                  # Main documentation
│   ├── docs/                      # Detailed docs (you are here)
│   └── .venv/                     # Python dependencies
│
├── obsidian_control/              # Your customisations — NOT in git
│   ├── .env                       # Real credentials and config
│   ├── session_state.json         # Persisted session state
│   ├── bridge.log                 # Runtime logs
│   └── data.db                    # SQLite database (MCP sqlite server)
│
└── .kiro/                         # kiro-cli config
    ├── agents/
    │   └── rick.json              # Active Rick agent (global)
    └── settings/
        └── mcp.json               # Active MCP server config (global)

~/.config/systemd/user/
└── kiro-bridge.service            # Installed service unit
```

## Request Lifecycle

1. User sends a message in Telegram
2. `python-telegram-bot` receives it via long polling
3. `auth_guard` checks `update.effective_user.id` against `TELEGRAM_ALLOWED_USER_ID`
4. `SessionManager.get_current()` loads the active named session
5. The session's backend is looked up via `get_backend(session.backend)`
6. Backend's `.send(message, session)` is called — for kiro, this spawns:
   ```
   kiro-cli chat --no-interactive --trust-all-tools --wrap never
                 --agent rick --resume-id <uuid> "<message>"
   ```
7. Output is cleaned (ANSI stripped), filtered by `RESPONSE_MODE`, split if >4096 chars
8. Response is sent back to Telegram
9. Session state is saved to `session_state.json`

## Session Model

Each user has a dict of named sessions. Each session tracks:
- `backend` — which AI engine to use
- `session_id` — UUID passed to `--resume-id` for conversation continuity
- `cwd` — working directory for the subprocess
- `history` — message history (used by API backends like anthropic_api, openai, ollama)
- `updated_at` — last activity timestamp
