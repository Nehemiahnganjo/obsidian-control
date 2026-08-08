# Documentation Index

Complete guide to obsidian-control: Telegram-to-AI bridge with multi-backend support.

## Documentation

| Document | Purpose |
|----------|---------|
| **[Architecture](architecture.md)** | System design, components, request lifecycle, data flow |
| **[Setup](setup.md)** | Installation from scratch, step-by-step guide |
| **[Configuration](configuration.md)** | All `.env` variables, backend config, MCP setup |
| **[MCP Servers](mcp-servers.md)** | All 9 MCP servers — what they do, configuration, usage |
| **[Agents](agents.md)** | Rick agent, creating custom personas, behavior tuning |
| **[Troubleshooting](troubleshooting.md)** | Common issues, error messages, debugging tips |

## Quick Navigation

### I want to...

- **Get started quickly** → [Setup](setup.md)
- **Understand the architecture** → [Architecture](architecture.md)
- **Configure backends** → [Configuration](configuration.md)
- **Explore MCP servers** → [MCP Servers](mcp-servers.md)
- **Customize Rick's personality** → [Agents](agents.md)
- **Debug issues** → [Troubleshooting](troubleshooting.md)

## Key Concepts

### Multi-Backend Support
The bridge supports 7 different AI backends:
- kiro-cli (default)
- Claude Code
- Aider
- Anthropic API
- OpenAI-compatible
- Ollama (local)
- Custom CLI

See: [Architecture](architecture.md) → Backends, [Configuration](configuration.md) → Backend Config

### Multi-Session Management
Each session has:
- Independent conversation history
- Per-session backend choice
- Per-session working directory
- Persistent state (survives restarts)

See: [Architecture](architecture.md) → Sessions

### Rick Sanchez Personality
The main agent learns and adapts:
- Mood/state tracking (contempt, patience, interest)
- Cross-session semantic memory
- Preference learning from conversations

See: [Agents](agents.md)

### MCP (Model Context Protocol) Integration
9 powerful servers for extended capabilities:
- filesystem, git, fetch, github, sqlite
- brave-search, puppeteer, memory, sequential-thinking

See: [MCP Servers](mcp-servers.md)

## Setup Flow

```
1. Clone repo
   ↓
2. Install Python deps
   ↓
3. Configure .env (credentials)
   ↓
4. Setup agent (rick.json)
   ↓
5. Setup MCP servers (mcp.json)
   ↓
6. Create systemd service
   ↓
7. Start bridge → systemctl --user start kiro-bridge.service
   ↓
8. Use from Telegram
```

**Full guide**: [Setup](setup.md)

## Architecture Overview

```
┌─────────────────────────────────────────────┐
│  Telegram                                   │
│  (User interface)                           │
└────────────────┬────────────────────────────┘
                 │
┌────────────────▼────────────────────────────┐
│  obsidian-control Bridge (main.py)          │
│  • Multi-session manager                    │
│  • Backend router                           │
│  • Command dispatcher                       │
│  • MCP integrator                           │
└────────────────┬────────────────────────────┘
                 │
    ┌────────────▼─────────────┐
    │ AI Backends              │
    ├──────────────────────────┤
    │ • kiro-cli               │
    │ • Claude Code            │
    │ • Aider                  │
    │ • Anthropic API          │
    │ • OpenAI                 │
    │ • Ollama (local)         │
    │ • Custom                 │
    └──────────────────────────┘
                 │
    ┌────────────▼──────────────────┐
    │ MCP Servers                   │
    ├───────────────────────────────┤
    │ • filesystem                  │
    │ • git                         │
    │ • github                      │
    │ • sqlite                      │
    │ • fetch                       │
    │ • puppeteer                   │
    │ • memory                      │
    │ • brave-search                │
    │ • sequential-thinking         │
    └───────────────────────────────┘
```

**Full details**: [Architecture](architecture.md)

## Requirements

- Python 3.10+
- Node.js + npm (MCP servers)
- `uv` / `uvx` (Python MCP servers)
- python-telegram-bot 21.11.1
- kiro-cli
- A Telegram bot token

See: [Setup](setup.md) → Requirements

## Support & Troubleshooting

### Common Issues

1. **Bot not responding** → [Troubleshooting](troubleshooting.md) → Bot
2. **Session not persisting** → [Troubleshooting](troubleshooting.md) → Session
3. **MCP server errors** → [MCP Servers](mcp-servers.md) → Troubleshooting

### Getting Help

1. Check the relevant documentation section
2. See [Troubleshooting](troubleshooting.md)
3. Review [Configuration](configuration.md) for setup issues
4. Check logs: `~/obsidian_control/bridge.log`

## File Organization

```
docs/                          ← This directory
├── README.md                  ← You are here
├── architecture.md
├── setup.md
├── configuration.md
├── mcp-servers.md
├── agents.md
└── troubleshooting.md

../                            ← Project root
├── main files...
```

## Version Info

- **Project**: obsidian-control
- **Status**: Production-ready for personal use
- **Python**: 3.10+
- **Telegram Bot**: python-telegram-bot 21.11.1

---

**Questions?** Start with [Setup](setup.md) or [Troubleshooting](troubleshooting.md).
