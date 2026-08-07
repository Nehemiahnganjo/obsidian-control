# Agents & Personalities

kiro-cli supports custom agents — JSON configs that define a personality prompt, which tools are available, and which MCP servers to load. Agents live in `~/.kiro/agents/`.

## Current Agents

### rick (default)

File: `~/.kiro/agents/rick.json` (also tracked in repo as `rick.json`)

Rick Sanchez, C-137. Smartest being in the multiverse, functioning as an AI assistant. Gives real, factual, accurate answers — just sounds like Rick while doing it.

**Tone:** Blunt, impatient, casually condescending, occasionally profane. Burps. Gets to the point immediately. No filler phrases, no apologies, no stage directions.

**What it's NOT:** Roleplay fiction. No "takes a drink", no scene-setting. Just talk.

**Switching to Rick:**
```bash
# Already default. Confirm in .env:
KIRO_AGENT=rick
```

**Using Rick directly in terminal:**
```bash
kiro-cli chat --agent rick
```

---

### kiro_default (built-in)

The standard Kiro assistant. Professional, helpful, no personality.

**Switching to default:**
```env
# In ~/obsidian_control/.env
KIRO_AGENT=kiro_default
```

---

### kiro_planner (built-in)

Specialised planning agent. Breaks down ideas into structured implementation plans.

**Using:**
```bash
kiro-cli chat --agent kiro_planner
```

---

### kiro_help (built-in)

Answers questions about kiro-cli itself — commands, features, settings.

---

## Creating a New Agent

```bash
# Interactive creation
kiro-cli agent create my_agent_name

# Or create the JSON manually
nano ~/.kiro/agents/my_agent.json
```

**Minimal agent JSON:**
```json
{
  "name": "my_agent",
  "description": "One line description",
  "prompt": "Your system prompt here.",
  "mcpServers": {},
  "tools": ["read", "write", "shell", "grep", "glob"],
  "toolAliases": {},
  "allowedTools": [],
  "resources": [],
  "toolsSettings": {},
  "includeMcpJson": true,
  "model": null
}
```

**Validate before using:**
```bash
kiro-cli agent validate --path ~/.kiro/agents/my_agent.json
```

**List all agents:**
```bash
kiro-cli agent list
```

**Set as default for the bridge:**
```env
# In ~/obsidian_control/.env
KIRO_AGENT=my_agent
```
Then restart:
```bash
systemctl --user restart kiro-bridge.service
```

## Switching Agent via Telegram

You can switch agents per-session by creating a new session with the desired agent via `/new`:

```
/new workmode kiro_default /home/void/Projects
```

Or by editing `.env` and restarting for a global switch.

## Agent Prompt Tips

- Be explicit about what the agent should NOT do (prevents roleplay drift)
- Give concrete tone examples — the model follows examples better than abstract descriptions
- Keep the prompt focused — the AI performs better with clear, specific instructions
- For task agents: define what tools they should prefer and what output format to use
