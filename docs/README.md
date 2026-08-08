# Documentation Index

Complete guide to obsidian-control: Telegram-to-AI bridge with multi-backend support and fine-tuning capabilities.

## Core Documentation

| Document | Purpose |
|----------|---------|
| **[Architecture](architecture.md)** | System design, components, request lifecycle, data flow |
| **[Setup](setup.md)** | Installation from scratch, step-by-step guide |
| **[Configuration](configuration.md)** | All `.env` variables, backend config, MCP setup |
| **[MCP Servers](mcp-servers.md)** | All 9 MCP servers — what they do, configuration, usage |
| **[Agents](agents.md)** | Rick agent, creating custom personas, behavior tuning |
| **[Troubleshooting](troubleshooting.md)** | Common issues, error messages, debugging tips |

## Fine-Tuning Pipeline

Train custom models locally with LoRA fine-tuning on CPU:

| Document | Purpose |
|----------|---------|
| **[FINETUNING_SETUP.md](../FINETUNING_SETUP.md)** | Quick start (5 minutes) — setup and first training run |
| **[FINE_TUNING.md](../FINE_TUNING.md)** | Complete technical guide — architecture, performance, monitoring |
| **[CHECKLIST.md](../CHECKLIST.md)** | Setup verification, troubleshooting, quality expectations |

## Quick Navigation

### I want to...

- **Get started quickly** → [Setup](setup.md)
- **Understand the architecture** → [Architecture](architecture.md)
- **Configure backends** → [Configuration](configuration.md)
- **Explore MCP servers** → [MCP Servers](mcp-servers.md)
- **Customize Rick's personality** → [Agents](agents.md)
- **Fine-tune a custom model** → [FINETUNING_SETUP.md](../FINETUNING_SETUP.md)
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
- Fine-tuned offline model support

See: [Agents](agents.md), [FINE_TUNING.md](../FINE_TUNING.md)

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

## Fine-Tuning Flow

```
1. Run setup script
   ↓
2. Collect 50+ conversations
   ↓
3. Export training data
   ↓
4. Fine-tune (30-60 min)
   ↓
5. Test offline model
   ↓
6. Enable scheduler (optional)
   ↓
7. Continuous improvement
```

**Full guide**: [FINETUNING_SETUP.md](../FINETUNING_SETUP.md)

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
└────────────┬──────────────────┬─────────────┘
             │                  │
    ┌────────▼─────────┐  ┌─────▼──────────────┐
    │ AI Backends      │  │ MCP Servers        │
    ├─────────────────┤  ├───────────────────┤
    │ • kiro-cli      │  │ • filesystem      │
    │ • Claude Code   │  │ • git             │
    │ • Aider         │  │ • github          │
    │ • Anthropic API │  │ • sqlite          │
    │ • OpenAI        │  │ • fetch           │
    │ • Ollama (local)│  │ • puppeteer       │
    │ • Custom        │  │ • memory          │
    └─────────────────┘  │ • brave-search    │
                         │ • sequential-thinking
                         └───────────────────┘
```

**Full details**: [Architecture](architecture.md)

## Requirements

- Python 3.10+
- Node.js + npm (MCP servers)
- `uv` / `uvx` (Python MCP servers)
- python-telegram-bot 21.11.1
- kiro-cli
- A Telegram bot token

For fine-tuning:
- PyTorch (CPU)
- transformers, peft, datasets
- 32GB RAM recommended

See: [Setup](setup.md) → Requirements

## Support & Troubleshooting

### Common Issues

1. **Bot not responding** → [Troubleshooting](troubleshooting.md) → Bot
2. **Session not persisting** → [Troubleshooting](troubleshooting.md) → Session
3. **MCP server errors** → [MCP Servers](mcp-servers.md) → Troubleshooting
4. **Fine-tuning crashes** → [FINE_TUNING.md](../FINE_TUNING.md) → Troubleshooting

### Getting Help

1. Check the relevant documentation section
2. See [Troubleshooting](troubleshooting.md)
3. Review [Configuration](configuration.md) for setup issues
4. Check logs: `~obsidian_control/bridge.log`

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
├── FINE_TUNING.md             ← Technical guide
├── FINETUNING_SETUP.md        ← Quick start
├── CHECKLIST.md               ← Verification
└── main files...
```

## Contributing

To improve documentation:
1. Edit the relevant `.md` file
2. Keep formatting consistent
3. Update this README if adding new docs
4. Submit a pull request

## Version Info

- **Project**: obsidian-control
- **Status**: Production-ready for personal use
- **Latest**: Commit 47b9865 (FreeCAD purged, fine-tuning complete)
- **Python**: 3.10+
- **Telegram Bot**: python-telegram-bot 21.11.1

---

**Questions?** Start with [Setup](setup.md) or [Troubleshooting](troubleshooting.md).

**Ready to fine-tune?** See [FINETUNING_SETUP.md](../FINETUNING_SETUP.md).
