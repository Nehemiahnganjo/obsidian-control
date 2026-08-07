# Troubleshooting

## Service won't start

```bash
journalctl --user -u kiro-bridge.service -n 50 --no-pager
```

**`No module named telegram`**
```bash
cd ~/kiro-telegram-bridge
.venv/bin/pip install "python-telegram-bot==21.11.1"
systemctl --user restart kiro-bridge.service
```

**`RuntimeError: There is no current event loop`**
Python 3.10+ doesn't create an implicit event loop. Fixed in `main.py` — ensure you have the latest version:
```bash
cd ~/kiro-telegram-bridge && git pull
systemctl --user restart kiro-bridge.service
```

**`EnvironmentFile not found`**
```bash
ls ~/obsidian_control/.env
# If missing:
cp ~/kiro-telegram-bridge/.env.example ~/obsidian_control/.env
chmod 600 ~/obsidian_control/.env
nano ~/obsidian_control/.env   # fill in your token and user ID
```

---

## Bot not responding

**Check it's running:**
```bash
systemctl --user status kiro-bridge.service
```

**Check your user ID matches:**
```bash
grep TELEGRAM_ALLOWED_USER_ID ~/obsidian_control/.env
```
Get your real ID from [@userinfobot](https://t.me/userinfobot).

**Check the token is correct:**
```bash
grep TELEGRAM_BOT_TOKEN ~/obsidian_control/.env
```
Regenerate at [@BotFather](https://t.me/BotFather) with `/token` if needed.

---

## kiro-cli not found

```bash
which kiro-cli
ls ~/.local/bin/kiro-cli
```

If missing, install kiro-cli. Then update `.env`:
```env
KIRO_CLI_PATH=/path/to/kiro-cli
```

---

## kiro times out on every message

Increase the timeout:
```env
AGENT_TIMEOUT=300
```

Check kiro-cli works standalone:
```bash
kiro-cli chat --no-interactive --agent rick "hello"
```

---

## Agent not loading

```bash
kiro-cli agent list
kiro-cli agent validate --path ~/.kiro/agents/rick.json
```

If rick isn't listed, copy it:
```bash
cp ~/kiro-telegram-bridge/rick.json ~/.kiro/agents/rick.json
```

---

## Lost session context

Check session state file:
```bash
cat ~/obsidian_control/session_state.json
```

If it's empty or corrupted, delete it — a new one is created on first message:
```bash
rm ~/obsidian_control/session_state.json
```

---

## MCP server not working

Test the server directly:
```bash
# filesystem
npx -y @modelcontextprotocol/server-filesystem /home/void

# git
uvx mcp-server-git --repository /home/void

# fetch
uvx mcp-server-fetch
```

Check kiro picks up the config:
```bash
cat ~/.kiro/settings/mcp.json
kiro-cli agent list   # should show no errors
```

---

## Viewing logs

```bash
# Live systemd journal
journalctl --user -u kiro-bridge.service -f

# File log
tail -f ~/obsidian_control/bridge.log

# Last 100 lines
tail -100 ~/obsidian_control/bridge.log
```

---

## Common commands

```bash
# Restart
systemctl --user restart kiro-bridge.service

# Stop
systemctl --user stop kiro-bridge.service

# Start
systemctl --user start kiro-bridge.service

# Full status
systemctl --user status kiro-bridge.service --no-pager
```
