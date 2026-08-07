# Configuration Reference

All configuration lives in `~/obsidian_control/.env`. This file is gitignored — it never touches the repo.

## Required

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_ALLOWED_USER_ID` | Your numeric Telegram user ID (get from [@userinfobot](https://t.me/userinfobot)) |

## Paths

| Variable | Default | Description |
|---|---|---|
| `KIRO_WORKDIR` | `/home/void` | Default working directory for sessions |
| `BRIDGE_DIR` | `/home/void/obsidian_control` | Where session state and logs are stored |

## Backend Selection

| Variable | Default | Description |
|---|---|---|
| `AGENT_BACKEND` | `kiro` | Default backend for new sessions |
| `KIRO_CLI_PATH` | `/home/void/.local/bin/kiro-cli` | Path to kiro-cli binary |
| `KIRO_AGENT` | `rick` | Agent/personality for kiro backend |

### Available backends

| Key | Requires |
|---|---|
| `kiro` | kiro-cli installed |
| `claude_code` | Claude Code CLI (`claude`) |
| `aider` | Aider installed |
| `anthropic_api` | `ANTHROPIC_API_KEY` |
| `openai` | `OPENAI_API_KEY` |
| `ollama` | Ollama running locally |
| `custom` | `CUSTOM_CMD_TEMPLATE` set |

## Tuning

| Variable | Default | Description |
|---|---|---|
| `AGENT_TIMEOUT` | `180` | Seconds before a command times out |
| `RESPONSE_MODE` | `smart` | `smart` (trim to 2000), `verbose` (full), `brief` (first line) |
| `MAX_FILE_SIZE` | `20971520` | Max upload size in bytes (20MB) |

## Optional API Backends

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Key for direct Anthropic API calls |
| `ANTHROPIC_MODEL` | Model to use (default: `claude-sonnet-4-6`) |
| `OPENAI_API_KEY` | Key for OpenAI or compatible endpoint |
| `OPENAI_MODEL` | Model to use (default: `gpt-4o`) |
| `OPENAI_BASE_URL` | Base URL (swap for vLLM, LM Studio, etc.) |
| `OLLAMA_HOST` | Ollama endpoint (default: `http://localhost:11434`) |
| `OLLAMA_MODEL` | Model to use (default: `llama3.1`) |
| `CLAUDE_CODE_PATH` | Path to Claude Code CLI binary |
| `AIDER_PATH` | Path to Aider binary |
| `CUSTOM_CMD_TEMPLATE` | Command template, e.g. `mytool --session {session_id} {message}` |

## Services & Integrations

| Variable | Description |
|---|---|
| `GITHUB_TOKEN` | GitHub PAT — used by the MCP github server |
| `BRAVE_API_KEY` | Brave Search API key — used by MCP brave-search server |

## Logging

| Variable | Default | Description |
|---|---|---|
| `LOG_FILE` | `/home/void/obsidian_control/bridge.log` | Path to log file |

## Applying Changes

After editing `.env`:

```bash
systemctl --user restart kiro-bridge.service
```

Verify:
```bash
systemctl --user status kiro-bridge.service
journalctl --user -u kiro-bridge.service -f
```
