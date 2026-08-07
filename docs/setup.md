# Setup & Installation

## Prerequisites

- Linux (systemd user services)
- Python 3.10+
- Node.js + npm (for MCP servers)
- `uv` / `uvx` (for Python MCP servers)
- kiro-cli installed at `~/.local/bin/kiro-cli`
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- Your numeric Telegram user ID (from [@userinfobot](https://t.me/userinfobot))

---

## Step 1 — Clone the repo

```bash
git clone https://github.com/Nehemiahnganjo/obsidian-control.git ~/kiro-telegram-bridge
cd ~/kiro-telegram-bridge
```

---

## Step 2 — Python venv + dependencies

```bash
python3 -m venv .venv
.venv/bin/pip install \
  "python-telegram-bot==21.11.1" \
  "python-dotenv==1.0.1" \
  "requests==2.32.3"
```

---

## Step 3 — Config directory

```bash
mkdir -p ~/obsidian_control
cp .env.example ~/obsidian_control/.env
chmod 600 ~/obsidian_control/.env
nano ~/obsidian_control/.env
```

Set at minimum:
```env
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_ALLOWED_USER_ID=your_numeric_id
BRIDGE_DIR=/home/youruser/obsidian_control
KIRO_WORKDIR=/home/youruser
GITHUB_TOKEN=your_github_pat   # optional, for MCP github server
```

---

## Step 4 — Rick agent

```bash
mkdir -p ~/.kiro/agents
cp rick.json ~/.kiro/agents/rick.json
```

Validate:
```bash
kiro-cli agent validate --path ~/.kiro/agents/rick.json
```

---

## Step 5 — MCP servers

```bash
mkdir -p ~/.kiro/settings
cp mcp.json ~/.kiro/settings/mcp.json
```

Edit `~/.kiro/settings/mcp.json` and replace `${GITHUB_TOKEN}` with your actual token, or set `GITHUB_TOKEN` as an environment variable.

---

## Step 6 — Systemd service

```bash
mkdir -p ~/.config/systemd/user

# Copy and edit the service file
cp kiro-bridge.service ~/.config/systemd/user/kiro-bridge.service
nano ~/.config/systemd/user/kiro-bridge.service
# Replace /home/youruser with your actual home path

systemctl --user daemon-reload
systemctl --user enable --now kiro-bridge.service
```

---

## Step 7 — Verify

```bash
# Check it's running
systemctl --user status kiro-bridge.service

# Watch live logs
journalctl --user -u kiro-bridge.service -f
```

Then send `/start` to your bot in Telegram. You should see the menu.

---

## Updating

```bash
cd ~/kiro-telegram-bridge
git pull
systemctl --user restart kiro-bridge.service
```

---

## Uninstalling

```bash
systemctl --user stop kiro-bridge.service
systemctl --user disable kiro-bridge.service
rm ~/.config/systemd/user/kiro-bridge.service
systemctl --user daemon-reload
rm -rf ~/kiro-telegram-bridge
rm -rf ~/obsidian_control   # WARNING: deletes your config and logs
```
