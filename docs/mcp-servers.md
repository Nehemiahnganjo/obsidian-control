# MCP Servers

MCP (Model Context Protocol) servers extend kiro-cli with additional capabilities — tools the AI can call during a conversation. Configuration lives in `~/.kiro/settings/mcp.json`.

## Configured Servers

### filesystem
Gives kiro read/write access to your files with path restrictions.

```json
{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/void"]
}
```

- Scope: everything under `/home/void`
- No extra config needed

---

### git
Git operations without leaving the chat.

```json
{
  "command": "uvx",
  "args": ["mcp-server-git", "--repository", "/home/void"]
}
```

- Capabilities: `git_log`, `git_diff`, `git_status`, `git_commit`, `git_show`
- Scope: repos under `/home/void`

---

### fetch
Fetch and read any URL — web pages, APIs, raw files.

```json
{
  "command": "uvx",
  "args": ["mcp-server-fetch"]
}
```

- No config needed
- Useful for: reading docs, scraping pages, hitting REST APIs

---

### github
Full GitHub API access — issues, PRs, repos, code search.

```json
{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-github"],
  "env": {
    "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"
  }
}
```

- Requires: `GITHUB_TOKEN` in `~/obsidian_control/.env`
- Capabilities: create/read issues, open PRs, search code, manage repos

---

### sqlite
Query SQLite databases directly in conversation.

```json
{
  "command": "uvx",
  "args": ["mcp-server-sqlite", "--db-path", "/home/void/obsidian_control/data.db"]
}
```

- Default DB: `/home/void/obsidian_control/data.db`
- Change `--db-path` to point at any `.db` file

---

### brave-search
Web search via Brave Search API.

```json
{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-brave-search"],
  "env": {
    "BRAVE_API_KEY": ""
  }
}
```

- Requires: `BRAVE_API_KEY` in `~/obsidian_control/.env`
- Get a free key at: https://brave.com/search/api/
- Leave blank to disable

---

### puppeteer
Full headless browser — automate websites, take screenshots, fill forms.

```json
{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-puppeteer"]
}
```

- No config needed
- Useful for: automated testing, scraping JS-heavy sites, screenshots

---

### memory
Persistent key-value store that survives across sessions.

```json
{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-memory"]
}
```

- No config needed
- Use it to store facts, preferences, notes that kiro should always remember

---

### sequential-thinking
Structured step-by-step reasoning for complex multi-part problems.

```json
{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
}
```

- No config needed
- Automatically used when the AI needs to break down a complex problem

---

## Adding a New MCP Server

1. Add it to `~/.kiro/settings/mcp.json`
2. If it belongs in the repo, add it to `~/kiro-telegram-bridge/mcp.json` too (no secrets)
3. Add the server name to `mcpServers` in `~/.kiro/agents/rick.json`
4. Restart kiro-cli (or just start a new session — it reloads on each invocation)

## Enabling brave-search

```bash
# Add to ~/obsidian_control/.env
BRAVE_API_KEY=your_key_here

# Get a free key at:
# https://brave.com/search/api/
```

Then update `~/.kiro/settings/mcp.json`:
```json
"env": {
  "BRAVE_API_KEY": "${BRAVE_API_KEY}"
}
```
