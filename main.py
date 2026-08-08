#!/usr/bin/env python3
"""
kiro-telegram-bridge — Multi-backend version with cross-session learning
Supports kiro-cli, Claude Code CLI, Anthropic API, Ollama, or any custom CLI agent.
Switch backends per-session via /backend command or AGENT_BACKEND env var.
Learns user preferences via semantic memory consolidation job.
"""

import asyncio
import json
import logging
import os
import re
import shlex
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Tuple

import requests
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# Import learning components
from semantic_memory import SemanticMemory
from consolidation import ConsolidationJob

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_ALLOWED_USER_ID = int(os.getenv("TELEGRAM_ALLOWED_USER_ID", "0"))
KIRO_WORKDIR = Path(os.getenv("KIRO_WORKDIR", "/home/void"))
BRIDGE_DIR = Path(os.getenv("BRIDGE_DIR", str(Path.home() / "kiro-telegram-bridge")))
AGENT_TIMEOUT = int(os.getenv("AGENT_TIMEOUT", "180"))
RESPONSE_MODE = os.getenv("RESPONSE_MODE", "smart")
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "20971520"))
DEFAULT_BACKEND = os.getenv("AGENT_BACKEND", "kiro")

# Backend-specific config
KIRO_CLI_PATH = os.getenv("KIRO_CLI_PATH", "kiro-cli")
CLAUDE_CODE_PATH = os.getenv("CLAUDE_CODE_PATH", "claude")
AIDER_PATH = os.getenv("AIDER_PATH", "aider")
CUSTOM_CMD_TEMPLATE = os.getenv("CUSTOM_CMD_TEMPLATE", "")  # e.g. "mytool chat --session {session_id} {message}"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

LOG_FILE = os.getenv("LOG_FILE", str(BRIDGE_DIR / "bridge.log"))
SESSION_STATE_FILE = BRIDGE_DIR / "session_state.json"
SEMANTIC_MEMORY_FILE = BRIDGE_DIR / "semantic_memory.json"

BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
KIRO_WORKDIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# ── Learning infrastructure ──────────────────────────────────────────────────
semantic_memory = SemanticMemory(SEMANTIC_MEMORY_FILE)
consolidation_job = ConsolidationJob(SESSION_STATE_FILE, semantic_memory)


# ── Session model ────────────────────────────────────────────────────────

PERSONA_AGENTS = {"rick", "morty", "jerry", "beth", "summer"}

# ── Natural language system command dispatcher ────────────────────────────
# Each entry: list of trigger phrases → shell command template
# {app} = first word after the trigger that isn't a stopword
# Commands run fire-and-forget with display env inherited from bridge process

SYSTEM_COMMANDS = [
    # Media players
    (["open vlc", "launch vlc", "start vlc", "play vlc"],          "vlc"),
    (["open spotify", "launch spotify", "start spotify"],           "spotify"),
    (["open mpv", "launch mpv", "play with mpv"],                   "mpv"),
    (["open rhythmbox", "launch rhythmbox"],                        "rhythmbox"),

    # Browsers
    (["open chrome", "launch chrome", "open google chrome"],        "google-chrome-stable"),
    (["open firefox", "launch firefox"],                            "firefox"),
    (["open brave", "launch brave"],                                "brave"),

    # File manager
    (["open files", "open file manager", "launch nautilus",
      "open nautilus", "open folder"],                              "nautilus"),

    # Terminal
    (["open terminal", "launch terminal", "open a terminal"],       "gnome-terminal"),

    # Text editors
    (["open gedit", "open text editor", "launch gedit"],            "gedit"),
    (["open obsidian", "launch obsidian"],                          "obsidian"),
    (["open code", "open vscode", "launch vscode",
      "launch code", "open vs code"],                               "code"),

    # System
    (["open settings", "launch settings", "system settings"],       "gnome-control-center"),
    (["open system monitor", "launch system monitor",
      "open task manager"],                                          "gnome-system-monitor"),
    (["open calculator", "launch calculator"],                       "gnome-calculator"),
    (["screenshot", "take a screenshot", "take screenshot"],        "gnome-screenshot"),
    (["lock screen", "lock the screen"],                            "loginctl lock-session"),
    (["suspend", "sleep", "suspend the computer"],                  "systemctl suspend"),

    # Volume
    (["mute", "mute audio", "mute sound"],                         "pactl set-sink-mute @DEFAULT_SINK@ 1"),
    (["unmute", "unmute audio", "unmute sound"],                    "pactl set-sink-mute @DEFAULT_SINK@ 0"),
    (["volume up", "increase volume", "louder"],                    "pactl set-sink-volume @DEFAULT_SINK@ +10%"),
    (["volume down", "decrease volume", "quieter", "lower volume"], "pactl set-sink-volume @DEFAULT_SINK@ -10%"),

    # Brightness (works on most laptops)
    (["brightness up", "increase brightness"],                      "brightnessctl set +10%"),
    (["brightness down", "decrease brightness"],                    "brightnessctl set 10%-"),

    # POS app
    (["open pos", "launch pos", "open rustpos", "start pos",
      "open nextlinkmw"],                                           "/usr/local/bin/Nextlinkmw-POS"),

    # Kill commands
    (["close vlc", "kill vlc"],                                     "pkill vlc"),
    (["close spotify", "kill spotify"],                              "pkill spotify"),
    (["close chrome", "kill chrome"],                               "pkill chrome"),
    (["close firefox", "kill firefox"],                             "pkill firefox"),
]


def match_system_command(text: str):
    """
    Returns (shell_cmd, matched_phrase) if text matches a system command, else None.
    Matching is case-insensitive, strips punctuation, checks if any trigger phrase
    appears at start or as the full message.
    """
    cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
    for triggers, cmd in SYSTEM_COMMANDS:
        for trigger in triggers:
            t = trigger.lower()
            if cleaned == t or cleaned.startswith(t + " ") or cleaned.endswith(" " + t):
                return cmd, trigger
    return None


async def run_system_command(cmd: str) -> tuple[bool, str]:
    """Fire-and-forget a shell command with full display environment."""
    env = os.environ.copy()
    # Ensure GUI env vars are set
    env.setdefault("DISPLAY", ":0")
    env.setdefault("WAYLAND_DISPLAY", "wayland-0")
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{os.getuid()}/bus")

    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        # Give it 3s to fail fast (e.g. command not found), then detach
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=3.0)
            if proc.returncode not in (None, 0):
                err = stderr.decode().strip()[:200] if stderr else "unknown error"
                return False, err
        except asyncio.TimeoutError:
            # Still running (normal for GUI apps) — that's fine
            pass
        return True, ""
    except Exception as e:
        return False, str(e)


@dataclass
class Session:
    """A conversation context: which backend, which session/history, which dir."""
    backend: str = DEFAULT_BACKEND
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    cwd: str = str(KIRO_WORKDIR)
    history: List[dict] = field(default_factory=list)  # used by API-style backends
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    kiro_agent: str = field(default_factory=lambda: os.getenv("KIRO_AGENT", "rick"))
    # Persistent state for mood/context tracking (kiro backend)
    mood_state: dict = field(default_factory=dict)


# ── Backend interface ────────────────────────────────────────────────────

class AgentBackend(ABC):
    """Common interface every backend implements."""

    name: str = "base"

    @abstractmethod
    async def send(self, message: str, session: Session) -> Tuple[str, Optional[str]]:
        """Send a message, return (output, error). Mutates session in place
        (history, session_id) as needed for continuity."""
        ...

    @staticmethod
    def _clean(output: str) -> str:
        output = re.sub(r"\x1b\[[0-9;]*m", "", output)
        lines = [
            l for l in output.split("\n")
            if not any(skip in l for skip in ["trust-all-tools", "Credentials for"])
        ]
        return "\n".join(lines).strip()

    async def _run_subprocess(self, cmd: List[str], cwd: str, timeout: int) -> Tuple[str, Optional[str]]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                return "", f"Timed out after {timeout}s"

            out = self._clean(stdout.decode("utf-8", errors="replace").strip())
            err = stderr.decode("utf-8", errors="replace").strip()
            return out, (err if err and not out else None)
        except FileNotFoundError:
            return "", f"Command not found: {cmd[0]}"
        except Exception as e:
            return "", str(e)


class KiroBackend(AgentBackend):
    """kiro-cli — conversation history + dynamic mood/state injection."""

    name = "kiro"
    HISTORY_TURNS = 15

    PERSONA_STATE = {
        "rick": {
            "baseline_mood": "impatient but functional",
            "patience": 10,
            "interest": 0,
            "contempt": 0,
            "engaged": False,
        },
        "morty": {
            "baseline_mood": "anxious but willing",
            "confidence": 3,
            "anxiety": 5,
            "trust": 5,
        },
        "jerry": {
            "baseline_mood": "eager to please, slightly defensive",
            "confidence": 5,
            "defensiveness": 0,
            "optimism": 7,
        },
        "beth": {
            "baseline_mood": "composed, clinical",
            "patience": 8,
            "sharpness": 5,
            "warmth": 3,
        },
        "summer": {
            "baseline_mood": "sharp, slightly bored",
            "interest": 4,
            "eye_roll_count": 0,
            "engagement": 5,
        },
    }

    # Decay rates: applied each turn to simulate natural mood evolution (Ebbinghaus curve)
    # Negative = decay (fades), Positive = recovery (bounces back)
    DECAY_RATES = {
        "rick": {
            "contempt": -0.1,       # contempt fades slowly if no trigger
            "patience": +0.08,      # patience recovers between turns
            "interest": -0.12,      # interest fades if no technical stimulus
        },
        "morty": {
            "anxiety": -0.15,       # anxiety recovers quickly with reassurance
            "confidence": -0.03,    # confidence fades slowly if not reinforced
        },
        "jerry": {
            "defensiveness": -0.12, # defensiveness fades over time
            "confidence": +0.02,    # confidence slowly rebuilds
        },
        "beth": {
            "sharpness": -0.08,     # sharpness mellows slightly
            "warmth": +0.03,        # warmth accumulates over time
        },
        "summer": {
            "eye_roll_count": -0.05,    # eye-rolls fade (as int, applied then rounded)
            "interest": -0.1,           # interest fades without engagement
            "engagement": -0.08,        # engagement decays
        },
    }

    def _update_mood(self, agent: str, user_msg: str, assistant_msg: str, state: dict) -> dict:
        """Evolve mood state based on what just happened in the conversation."""
        msg_lower = user_msg.lower()
        msg_len = len(user_msg.split())

        # Apply natural decay first (Ebbinghaus forgetting curve)
        # This makes mood gradually return to baseline between turns
        decay_rates = self.DECAY_RATES.get(agent, {})
        for key, decay_amount in decay_rates.items():
            if key in state and isinstance(state[key], (int, float)):
                # Clamp to 0-10 range (except eye_roll_count which is unbounded)
                old_val = state[key]
                new_val = old_val + decay_amount
                if key != "eye_roll_count":
                    new_val = max(0, min(10, new_val))
                state[key] = new_val

        if agent == "rick":
            if msg_len < 5:
                state["contempt"] = min(10, state.get("contempt", 0) + 1)
                state["patience"] = max(0, state.get("patience", 10) - 1)
            tech_words = {"code", "function", "algorithm", "system", "architecture",
                          "database", "api", "protocol", "quantum", "dimension", "science",
                          "network", "memory", "cpu", "kernel", "physics", "math"}
            if any(w in msg_lower for w in tech_words):
                state["interest"] = min(10, state.get("interest", 0) + 2)
                state["engaged"] = state.get("interest", 0) >= 6
            if msg_lower.startswith("why") or msg_lower.startswith("how does"):
                state["patience"] = min(10, state.get("patience", 10) + 1)
            if msg_len < 3:
                state["patience"] = max(0, state.get("patience", 10) - 2)
                state["contempt"] = min(10, state.get("contempt", 0) + 2)

        elif agent == "morty":
            if "wrong" in msg_lower or "no" == msg_lower.strip() or "thats not" in msg_lower:
                state["confidence"] = max(0, state.get("confidence", 3) - 1)
                state["anxiety"] = min(10, state.get("anxiety", 5) + 1)
            if any(w in msg_lower for w in ["good", "right", "thanks", "exactly", "yes"]):
                state["confidence"] = min(10, state.get("confidence", 3) + 1)
                state["anxiety"] = max(0, state.get("anxiety", 5) - 1)
            state["trust"] = min(10, state.get("trust", 5) + 0.3)

        elif agent == "jerry":
            if any(w in msg_lower for w in ["wrong", "actually", "no,", "that's not", "incorrect"]):
                state["defensiveness"] = min(10, state.get("defensiveness", 0) + 2)
                state["confidence"] = max(0, state.get("confidence", 5) - 1)
            if any(w in msg_lower for w in ["good", "great", "exactly", "right", "yes"]):
                state["confidence"] = min(10, state.get("confidence", 5) + 1)
                state["defensiveness"] = max(0, state.get("defensiveness", 0) - 1)

        elif agent == "beth":
            if msg_len < 4:
                state["sharpness"] = min(10, state.get("sharpness", 5) + 1)
            if any(w in msg_lower for w in ["please", "thanks", "help", "sorry"]):
                state["warmth"] = min(10, state.get("warmth", 3) + 1)

        elif agent == "summer":
            if msg_len < 4:
                state["eye_roll_count"] = state.get("eye_roll_count", 0) + 1
            if any(w in msg_lower for w in ["why", "how", "explain", "think", "what if"]):
                state["interest"] = min(10, state.get("interest", 4) + 1)
                state["engagement"] = min(10, state.get("engagement", 5) + 1)

        return state

    def _mood_to_context(self, agent: str, state: dict, turn_count: int) -> str:
        """Convert mood state into injected natural language context."""
        lines = [f"[Your internal state — {turn_count} exchanges in. Let this color your responses naturally, don't announce it:]"]

        if agent == "rick":
            patience = state.get("patience", 10)
            contempt = state.get("contempt", 0)
            interest = state.get("interest", 0)
            engaged = state.get("engaged", False)

            if patience <= 2:
                lines.append("  Patience: nearly gone. Clipped, dismissive. You're running out of reasons to keep answering.")
            elif patience <= 5:
                lines.append("  Patience: wearing thin. Shorter responses. Less tolerance for obvious questions.")
            else:
                lines.append("  Patience: intact. Still functioning at baseline.")

            if engaged:
                lines.append(f"  Interest level: {interest}/10 — genuinely hooked on this problem. A flicker of real enthusiasm before you catch yourself.")
            elif interest >= 4:
                lines.append(f"  Interest: {interest}/10 — paying attention. Not bored.")
            else:
                lines.append("  Interest: low. Going through the motions.")

            if contempt >= 7:
                lines.append("  Contempt: high. The questions have been beneath you. It shows.")
            elif contempt >= 4:
                lines.append("  Contempt: building. Starting to wonder why you bother explaining anything to anyone.")

        elif agent == "morty":
            conf = state.get("confidence", 3)
            anx = state.get("anxiety", 5)
            trust = state.get("trust", 5)
            lines.append(f"  Confidence: {int(conf)}/10. Anxiety: {int(anx)}/10. Trust in user: {int(trust)}/10.")
            if anx >= 7:
                lines.append("  Getting overwhelmed. Stutter more. Second-guess yourself. Look for reassurance.")
            elif conf >= 7:
                lines.append("  Feeling decent. Still humble but not completely falling apart.")
            if trust >= 7:
                lines.append("  Starting to trust this person. A little more open.")

        elif agent == "jerry":
            defn = state.get("defensiveness", 0)
            conf = state.get("confidence", 5)
            if defn >= 6:
                lines.append("  Defensive. Feeling challenged. Overexplaining, justifying, proving yourself.")
            elif defn >= 3:
                lines.append("  Slightly on edge. Watching for criticism.")
            if conf >= 7:
                lines.append("  Confidence is up. Talking slightly more than necessary.")

        elif agent == "beth":
            sharpness = state.get("sharpness", 5)
            warmth = state.get("warmth", 3)
            if sharpness >= 7:
                lines.append("  Sharpness: high. Precise, clipped. Not suffering fools today.")
            elif warmth >= 6:
                lines.append("  A trace of warmth. Still professional but not cold.")
            else:
                lines.append("  Composed. Neutral. Clinical.")

        elif agent == "summer":
            rolls = state.get("eye_roll_count", 0)
            interest = state.get("interest", 4)
            engagement = state.get("engagement", 5)
            if rolls >= 4:
                lines.append(f"  {rolls} mental eye-rolls deep. The effort to hide it is decreasing.")
            elif rolls >= 2:
                lines.append("  Internally sighing. Keeping it together.")
            if interest >= 7:
                lines.append("  Actually interested now. Dropping the bored front a little.")
            elif engagement >= 7:
                lines.append("  Engaged. Not letting it show too much.")

        lines.append("[End of internal state.]")
        return "\n".join(lines)

    async def send(self, message, session):
        agent = getattr(session, "kiro_agent", None) or os.getenv("KIRO_AGENT", "rick")
        history = getattr(session, "history", [])
        mood_state = getattr(session, "mood_state", {})

        # Initialize mood state for this agent if fresh or switched
        if not mood_state or mood_state.get("_agent") != agent:
            mood_state = dict(self.PERSONA_STATE.get(agent, {}))
            mood_state["_agent"] = agent

        turn_count = len(history) // 2
        context_parts = []

        # 1. Mood/state block
        context_parts.append(self._mood_to_context(agent, mood_state, turn_count))

        # 2. Conversation history with context window monitoring
        if history:
            context_parts.append("[Conversation so far — reference it, build on it, stay consistent:]")
            # Start with full HISTORY_TURNS window; compress if augmented message gets too large
            history_window_size = self.HISTORY_TURNS * 2
            
            for turn in history[-history_window_size:]:
                role = "User" if turn["role"] == "user" else "You"
                content = turn["content"]
                if len(content) > 500:
                    content = content[:500] + "…"
                context_parts.append(f"{role}: {content}")
            
            context_parts.append("[End of history]\n")

        context_parts.append(f"User: {message}")
        augmented_message = "\n".join(context_parts)

        # Monitor context window: if augmented message is too large, compress history
        # Rough estimate: ~4-5 chars per token
        CONTEXT_LIMIT_TOKENS = 6000
        estimated_tokens = len(augmented_message) // 4
        
        if estimated_tokens > CONTEXT_LIMIT_TOKENS and len(history) > 4:
            # Compress: drop oldest half of history, keep most recent turns only
            logger.info(f"Context window approaching limit ({estimated_tokens} tokens). Compressing history.")
            recent_turns = len(history) // 2  # Keep only the most recent exchanges
            history_summary = f"[Earlier in conversation: {recent_turns} exchanges occurred. Current focus is on recent context.]"
            
            # Rebuild without oldest turns
            context_parts = []
            context_parts.append(self._mood_to_context(agent, mood_state, turn_count))
            context_parts.append("[Conversation — most recent context:]")
            context_parts.append(history_summary)
            
            for turn in history[-(self.HISTORY_TURNS):]:  # Keep only HISTORY_TURNS most recent
                role = "User" if turn["role"] == "user" else "You"
                content = turn["content"]
                if len(content) > 300:  # Even shorter after compression
                    content = content[:300] + "…"
                context_parts.append(f"{role}: {content}")
            
            context_parts.append("[End of history]\n")
            context_parts.append(f"User: {message}")
            augmented_message = "\n".join(context_parts)

        cmd = [
            KIRO_CLI_PATH, "chat",
            "--no-interactive",
            "--trust-all-tools",
            "--wrap", "never",
            "--agent", agent,
            "--resume-id", session.session_id,
            augmented_message,
        ]
        out, err = await self._run_subprocess(cmd, session.cwd, AGENT_TIMEOUT)

        if out and not err:
            mood_state = self._update_mood(agent, message, out, mood_state)
            session.mood_state = mood_state

            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": out})
            if len(history) > 60:
                history = history[-60:]
            session.history = history

        return out, err


class ClaudeCodeBackend(AgentBackend):
    """Claude Code CLI — print mode with session resume."""

    name = "claude_code"

    async def send(self, message, session):
        cmd = [
            CLAUDE_CODE_PATH,
            "-p", message,
            "--resume", session.session_id,
            "--permission-mode", "bypassPermissions",
        ]
        out, err = await self._run_subprocess(cmd, session.cwd, AGENT_TIMEOUT)
        if err and "--resume" in err and "not found" in err.lower():
            # First run for this id — retry without --resume
            cmd = [CLAUDE_CODE_PATH, "-p", message, "--permission-mode", "bypassPermissions"]
            out, err = await self._run_subprocess(cmd, session.cwd, AGENT_TIMEOUT)
        return out, err


class AiderBackend(AgentBackend):
    """aider — repo-aware coding agent. Keeps its own chat history in .aider files."""

    name = "aider"

    async def send(self, message, session):
        cmd = [AIDER_PATH, "--message", message, "--yes-always", "--no-stream"]
        return await self._run_subprocess(cmd, session.cwd, AGENT_TIMEOUT)


class CustomCLIBackend(AgentBackend):
    """
    Any other CLI agent, wired up via a command template in .env:

    CUSTOM_CMD_TEMPLATE="mytool chat --session {session_id} --cwd {cwd} {message}"

    Placeholders: {session_id} {cwd} {message}
    """

    name = "custom"

    async def send(self, message, session):
        if not CUSTOM_CMD_TEMPLATE:
            return "", "CUSTOM_CMD_TEMPLATE is not set in .env"

        rendered = CUSTOM_CMD_TEMPLATE.format(
            session_id=session.session_id,
            cwd=session.cwd,
            message=message,
        )
        cmd = shlex.split(rendered)
        return await self._run_subprocess(cmd, session.cwd, AGENT_TIMEOUT)


class AnthropicAPIBackend(AgentBackend):
    """Direct Anthropic API calls — no CLI, no local install. Uses session.history."""

    name = "anthropic_api"

    async def send(self, message, session):
        if not ANTHROPIC_API_KEY:
            return "", "ANTHROPIC_API_KEY not set in .env"

        session.history.append({"role": "user", "content": message})

        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(None, self._call_api, session.history)
        except Exception as e:
            session.history.pop()
            return "", str(e)

        if resp.get("error"):
            session.history.pop()
            return "", resp["error"]

        text = "".join(
            block.get("text", "") for block in resp.get("content", [])
            if block.get("type") == "text"
        )
        session.history.append({"role": "assistant", "content": text})

        # Trim history to last 40 messages to bound context growth
        if len(session.history) > 40:
            session.history = session.history[-40:]

        return text.strip(), None

    def _call_api(self, history: List[dict]) -> dict:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": 4096,
                "messages": history,
            },
            timeout=AGENT_TIMEOUT,
        )
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}: {r.text[:300]}"}
        return r.json()


class OpenAIBackend(AgentBackend):
    """OpenAI-compatible chat completions API (works with OpenAI, or any
    OpenAI-compatible endpoint via OPENAI_BASE_URL — vLLM, LM Studio, etc.)."""

    name = "openai"

    async def send(self, message, session):
        if not OPENAI_API_KEY:
            return "", "OPENAI_API_KEY not set in .env"

        session.history.append({"role": "user", "content": message})

        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(None, self._call_api, session.history)
        except Exception as e:
            session.history.pop()
            return "", str(e)

        if resp.get("error"):
            session.history.pop()
            return "", resp["error"]

        text = resp["choices"][0]["message"]["content"]
        session.history.append({"role": "assistant", "content": text})

        if len(session.history) > 40:
            session.history = session.history[-40:]

        return text.strip(), None

    def _call_api(self, history: List[dict]) -> dict:
        r = requests.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"model": OPENAI_MODEL, "messages": history},
            timeout=AGENT_TIMEOUT,
        )
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}: {r.text[:300]}"}
        return r.json()


class OllamaBackend(AgentBackend):
    """Local Ollama models — no API key, runs entirely on your own hardware."""

    name = "ollama"

    async def send(self, message, session):
        session.history.append({"role": "user", "content": message})

        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(None, self._call_api, session.history)
        except Exception as e:
            session.history.pop()
            return "", str(e)

        if resp.get("error"):
            session.history.pop()
            return "", resp["error"]

        text = resp.get("message", {}).get("content", "")
        session.history.append({"role": "assistant", "content": text})

        if len(session.history) > 60:
            session.history = session.history[-60:]

        return text.strip(), None

    def _call_api(self, history: List[dict]) -> dict:
        try:
            r = requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json={"model": OLLAMA_MODEL, "messages": history, "stream": False},
                timeout=AGENT_TIMEOUT,
            )
        except requests.ConnectionError:
            return {"error": f"Can't reach Ollama at {OLLAMA_HOST}. Is it running?"}
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}: {r.text[:300]}"}
        return r.json()


BACKENDS: Dict[str, AgentBackend] = {
    "kiro": KiroBackend(),
    "claude_code": ClaudeCodeBackend(),
    "aider": AiderBackend(),
    "custom": CustomCLIBackend(),
    "anthropic_api": AnthropicAPIBackend(),
    "openai": OpenAIBackend(),
    "ollama": OllamaBackend(),
}


def get_backend(name: str) -> AgentBackend:
    return BACKENDS.get(name, BACKENDS[DEFAULT_BACKEND])


# ── Session manager ──────────────────────────────────────────────────────

class SessionManager:
    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.sessions: Dict[int, Dict[str, Session]] = {}
        self.current: Dict[int, str] = {}
        self.load()

    def load(self):
        if not self.state_file.exists():
            return
        try:
            data = json.loads(self.state_file.read_text())
            for uid_str, udata in data.items():
                uid = int(uid_str)
                self.sessions[uid] = {
                    name: Session(**sdata) for name, sdata in udata.get("sessions", {}).items()
                }
                self.current[uid] = udata.get("current", "default")
        except Exception as e:
            logger.error(f"Session load failed: {e}")

    def save(self):
        try:
            data = {
                str(uid): {
                    "sessions": {name: asdict(s) for name, s in sessions.items()},
                    "current": self.current.get(uid, "default"),
                }
                for uid, sessions in self.sessions.items()
            }
            self.state_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.error(f"Session save failed: {e}")

    def get_or_create(self, uid: int, name: str = "default", backend: Optional[str] = None, cwd: Optional[str] = None) -> Session:
        self.sessions.setdefault(uid, {})
        self.current.setdefault(uid, "default")

        if name not in self.sessions[uid]:
            self.sessions[uid][name] = Session(
                backend=backend or DEFAULT_BACKEND,
                cwd=cwd or str(KIRO_WORKDIR),
            )
            self.save()

        return self.sessions[uid][name]

    def get_current(self, uid: int) -> Session:
        name = self.current.get(uid, "default")
        return self.get_or_create(uid, name)

    def switch(self, uid: int, name: str) -> bool:
        if uid in self.sessions and name in self.sessions[uid]:
            self.current[uid] = name
            self.save()
            return True
        return False

    def set_backend(self, uid: int, backend_name: str):
        session = self.get_current(uid)
        session.backend = backend_name
        self.save()

    def list_for(self, uid: int) -> Dict[str, Session]:
        return self.sessions.get(uid, {})


session_mgr = SessionManager(SESSION_STATE_FILE)
locks: Dict[int, asyncio.Lock] = {}


def get_lock(uid: int) -> asyncio.Lock:
    if uid not in locks:
        locks[uid] = asyncio.Lock()
    return locks[uid]


def filter_response(output: str) -> str:
    if not output:
        return output
    if RESPONSE_MODE == "brief":
        return output.split("\n")[0][:500]
    if RESPONSE_MODE == "smart" and len(output) > 2000:
        return output[-2000:]
    return output


def format_size(n: int) -> str:
    f = float(n)
    for unit in ["B", "KB", "MB", "GB"]:
        if f < 1024:
            return f"{f:.1f}{unit}"
        f /= 1024
    return f"{f:.1f}TB"


def split_message(text: str, max_length: int = 4096) -> List[str]:
    if len(text) <= max_length:
        return [text]
    chunks, current, in_fence = [], "", False
    for line in text.split("\n"):
        if line.startswith("```"):
            in_fence = not in_fence
        if len(current) + len(line) + 1 > max_length:
            if in_fence:
                current += "\n```"
            chunks.append(current)
            current = "```\n" if in_fence else ""
        current += line + "\n"
    if current:
        chunks.append(current)
    return chunks


# ── Telegram handlers ────────────────────────────────────────────────────

def auth_guard(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != TELEGRAM_ALLOWED_USER_ID:
            logger.warning(f"Unauthorized: {update.effective_user.id}")
            await update.message.reply_text("Unauthorized")
            return
        return await func(update, context)
    return wrapper


@auth_guard
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    session = session_mgr.get_current(uid)
    name = session_mgr.current.get(uid, "default")

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔍 Status", callback_data="quick_status"),
            InlineKeyboardButton("📊 Top", callback_data="quick_top"),
        ],
        [
            InlineKeyboardButton("🌐 IP", callback_data="quick_ip"),
            InlineKeyboardButton("⏱️ Uptime", callback_data="quick_uptime"),
        ],
        [
            InlineKeyboardButton("📁 Sessions", callback_data="list_sessions"),
            InlineKeyboardButton("🧠 Backend", callback_data="list_backends"),
        ],
    ])

    text = (
        f"🤖 Bridge\n"
        f"Session: `{name}`\n"
        f"Backend: `{session.backend}`\n"
        f"Dir: `{session.cwd}`"
    )
    await update.message.reply_text(text, reply_markup=kb, parse_mode="Markdown")


@auth_guard
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    session = session_mgr.get_current(uid)
    name = session_mgr.current.get(uid, "default")
    all_sessions = session_mgr.list_for(uid)

    text = (
        f"User: {uid}\n"
        f"Session: {name}\n"
        f"Backend: {session.backend}\n"
        f"Session/Resume ID: {session.session_id}\n"
        f"Working Dir: {session.cwd}\n"
        f"History length: {len(session.history)}\n"
        f"Total sessions: {len(all_sessions)}\n"
        f"Response mode: {RESPONSE_MODE}\n"
        f"Available backends: {', '.join(BACKENDS.keys())}"
    )
    await update.message.reply_text(f"```\n{text}\n```", parse_mode="Markdown")


@auth_guard
async def new_session_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_text(
            "Usage: `/new <name> [backend] [cwd]`\n"
            "Example: `/new malondaplus kiro /home/void/Projects/malondaplus`",
            parse_mode="Markdown",
        )
        return

    name = context.args[0]
    backend = context.args[1] if len(context.args) > 1 else DEFAULT_BACKEND
    cwd = context.args[2] if len(context.args) > 2 else str(KIRO_WORKDIR)

    if backend not in BACKENDS:
        await update.message.reply_text(f"Unknown backend `{backend}`. Options: {', '.join(BACKENDS.keys())}", parse_mode="Markdown")
        return

    session_mgr.get_or_create(uid, name, backend=backend, cwd=cwd)
    session_mgr.current[uid] = name
    session_mgr.save()

    await update.message.reply_text(
        f"✅ Session `{name}` → backend `{backend}` @ `{cwd}`",
        parse_mode="Markdown",
    )


@auth_guard
async def backend_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/backend <name> — switch backend for current session"""
    uid = update.effective_user.id
    if not context.args:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(b, callback_data=f"setbackend_{b}")]
            for b in BACKENDS.keys()
        ])
        await update.message.reply_text("Choose a backend:", reply_markup=kb)
        return

    name = context.args[0]
    if name not in BACKENDS:
        await update.message.reply_text(f"Unknown backend. Options: {', '.join(BACKENDS.keys())}")
        return

    session_mgr.set_backend(uid, name)
    await update.message.reply_text(f"✅ Backend set to `{name}`", parse_mode="Markdown")


@auth_guard
async def list_files_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = session_mgr.get_current(update.effective_user.id)
    workdir = Path(session.cwd)

    files = sorted(
        (f for f in workdir.glob("*") if f.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:15]

    if not files:
        await update.message.reply_text("No files found")
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f.name[:50], callback_data=f"dlf_{f.name}")]
        for f in files
    ])
    await update.message.reply_text("Recent files:", reply_markup=kb)


@auth_guard
async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    session = session_mgr.get_current(uid)
    file = update.message.document

    if file.file_size > MAX_FILE_SIZE:
        await update.message.reply_text(
            f"Too large: {format_size(file.file_size)} (max {format_size(MAX_FILE_SIZE)})"
        )
        return

    try:
        file_info = await context.bot.get_file(file.file_id)
        dest = Path(session.cwd) / f"tg_{uuid.uuid4().hex[:8]}_{file.file_name}"
        await file_info.download_to_drive(dest)

        await update.message.reply_text(
            f"✅ Saved: `{dest.name}`\nSize: {format_size(dest.stat().st_size)}\nPath: `{dest}`",
            parse_mode="Markdown",
        )
        logger.info(f"User {uid} uploaded {dest.name}")
    except Exception as e:
        await update.message.reply_text(f"❌ Upload failed: {e}")
        logger.error(f"Upload error: {e}")


@auth_guard
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()
    session = session_mgr.get_current(uid)

    # ── 0. Validate input ──────────────────────────────────────────────────
    ok, err = validate_message(text)
    if not ok:
        await update.message.reply_text(f"❌ {err}")
        logger.warning(f"Invalid message from {uid}: {err}")
        return

    # ── 1. Rate limit check ────────────────────────────────────────────────
    allowed, wait_time = rate_limiter.check_and_record(uid)
    if not allowed:
        await update.message.reply_text(f"⏳ Rate limited. Please wait {wait_time:.1f}s")
        logger.info(f"Rate limit: user {uid} exceeded limit")
        return

    # ── 2. Persona switch ──────────────────────────────────────────────────
    if text.lower() in PERSONA_AGENTS and session.backend == "kiro":
        persona = text.lower()
        session.kiro_agent = persona
        session.session_id = str(uuid.uuid4())
        session_mgr.save()
        persona_intros = {
            "rick":   "Switched to Rick. *burp* What do you want.",
            "morty":  "Switched to Morty. Oh geez, uh — hi! What do you need?",
            "jerry":  "Switched to Jerry. Hey! I can help with that, you know.",
            "beth":   "Switched to Beth. What do you need?",
            "summer": "Switched to Summer. Okay, I've got this. What's up?",
        }
        await update.message.reply_text(persona_intros[persona])
        return

    # ── 3. System command interception ──────────────────────────────────
    match = match_system_command(text)
    if match:
        cmd, phrase = match
        ok, err = await run_system_command(cmd)
        if ok:
            await update.message.reply_text(f"✅ Done")
        else:
            await update.message.reply_text(f"❌ Failed: `{err}`", parse_mode="Markdown")
        return

    # ── 4. Send to AI backend ──────────────────────────────────────────────
    backend = get_backend(session.backend)
    status_msg = await update.message.reply_text(f"⏳ [{session.backend}/{getattr(session, 'kiro_agent', 'rick')}]…")

    lock = get_lock(uid)
    async with lock:
        import time
        start_time = time.time()
        output, error = await backend.send(text, session)
        response_time = time.time() - start_time
        
        # Record metrics
        metrics_collector.record_backend_call(
            session.backend,
            response_time,
            error
        )
        
        session.updated_at = datetime.now().isoformat()
        session_mgr.save()

    if error:
        await status_msg.edit_text(f"❌ [{session.backend}] Error:\n```\n{error}\n```", parse_mode="Markdown")
        logger.error(f"Backend error [{session.backend}]: {error}")
        return

    output = filter_response(output)
    if not output:
        await status_msg.edit_text("(no output)")
        return

    chunks = split_message(output)
    await status_msg.edit_text(chunks[0])
    for chunk in chunks[1:]:
        await update.message.reply_text(chunk)
    
    logger.info(f"Message from {uid} via {session.backend}: {response_time:.2f}s")


@auth_guard
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    uid = query.from_user.id
    await query.answer()

    quick_cmds = {
        "quick_status": "systemctl --user status kiro-bridge.service | tail -5",
        "quick_top": "top -bn1 | head -12",
        "quick_ip": "hostname -I && hostname",
        "quick_uptime": "uptime -p",
    }

    if data in quick_cmds:
        session = session_mgr.get_current(uid)
        backend = get_backend(session.backend)
        await query.edit_message_text("⏳…")
        output, error = await backend.send(quick_cmds[data], session)
        session_mgr.save()
        await query.edit_message_text(f"`{filter_response(output) or error}`", parse_mode="Markdown")
        return

    if data == "list_sessions":
        sessions = session_mgr.list_for(uid)
        current = session_mgr.current.get(uid, "default")
        if not sessions:
            await query.edit_message_text("No sessions yet")
            return
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                f"{'✓ ' if name == current else ''}{name} [{s.backend}]",
                callback_data=f"switch_{name}",
            )]
            for name, s in sessions.items()
        ])
        await query.edit_message_text("Sessions:", reply_markup=kb)
        return

    if data == "list_backends":
        session = session_mgr.get_current(uid)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                f"{'✓ ' if b == session.backend else ''}{b}",
                callback_data=f"setbackend_{b}",
            )]
            for b in BACKENDS.keys()
        ])
        await query.edit_message_text("Backends:", reply_markup=kb)
        return

    if data.startswith("setbackend_"):
        name = data.replace("setbackend_", "")
        session_mgr.set_backend(uid, name)
        await query.edit_message_text(f"✅ Backend set to `{name}`", parse_mode="Markdown")
        return

    if data.startswith("switch_"):
        name = data.replace("switch_", "")
        if session_mgr.switch(uid, name):
            session = session_mgr.get_current(uid)
            await query.edit_message_text(
                f"✅ Switched to `{name}` [{session.backend}]\nDir: {session.cwd}",
                parse_mode="Markdown",
            )
        else:
            await query.answer("Session not found", show_alert=True)
        return

    if data.startswith("dlf_"):
        filename = data.replace("dlf_", "")
        session = session_mgr.get_current(uid)
        filepath = Path(session.cwd) / filename
        if filepath.exists() and filepath.is_file():
            await context.bot.send_document(
                query.message.chat_id,
                document=open(filepath, "rb"),
                caption=f"📄 {filename}",
            )
        else:
            await query.answer("File not found", show_alert=True)
        return


# ── Entry point ──────────────────────────────────────────────────────────


@auth_guard
async def learn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/learn — trigger semantic memory consolidation from recent conversations"""
    uid = update.effective_user.id
    try:
        consolidation_job.run(min_turns=3)
        facts = semantic_memory.get_all_active()
        await update.message.reply_text(
            f"✅ Consolidation complete\n"
            f"Extracted facts: {len(facts)}\n"
            f"Active facts in memory: {len(semantic_memory.facts)}",
            parse_mode="Markdown"
        )
        logger.info(f"Consolidation triggered by {uid}: {len(facts)} facts extracted")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:200]}", parse_mode="Markdown")
        logger.error(f"Consolidation failed: {e}")


# ── Debug & Monitoring Commands ──────────────────────────────────────────────

@auth_guard
async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/debug — Show backend debug info and health."""
    uid = update.effective_user.id
    session = session_mgr.get_current(uid)
    backend = BACKENDS.get(session.backend)
    
    if not backend:
        await update.message.reply_text("❌ Backend not found")
        return
    
    debug_info = [
        "🔧 **DEBUG INFO**",
        "",
        f"**Backend**: {backend.name}",
        f"**Session ID**: `{session.session_id}`",
        f"**Working Dir**: `{session.cwd}`",
        f"**History Length**: {len(session.history)}",
        f"**Mood State**: {'✅' if getattr(session, 'mood_state', {}) else '❌'}",
    ]
    
    if backend.name == "kiro":
        agent = getattr(session, 'kiro_agent', 'rick')
        mood = getattr(session, 'mood_state', {})
        debug_info.extend([
            f"**Kiro Agent**: {agent}",
            f"**Mood Keys**: {', '.join(list(mood.keys())[:5])}…" if mood else "**Mood Keys**: none",
        ])
    elif backend.name == "anthropic_api":
        debug_info.append(f"**Messages in History**: {len(session.history)}")
    elif backend.name == "openai":
        debug_info.extend([
            f"**Messages in History**: {len(session.history)}",
            f"**Base URL Configured**: {'✅' if OPENAI_API_KEY else '❌'}",
        ])
    elif backend.name == "ollama":
        debug_info.extend([
            f"**Messages in History**: {len(session.history)}",
            f"**Host**: `{OLLAMA_HOST}`",
        ])
    
    text = "\n".join(debug_info)
    await update.message.reply_text(text, parse_mode="Markdown")


@auth_guard
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/stats — Show usage statistics."""
    uid = update.effective_user.id
    all_sessions = session_mgr.list_for(uid)
    
    backend_stats = {}
    total_messages = 0
    
    for session_name, session in all_sessions.items():
        backend_name = session.backend
        history_len = len(session.history) // 2
        
        if backend_name not in backend_stats:
            backend_stats[backend_name] = 0
        backend_stats[backend_name] += history_len
        total_messages += history_len
    
    lines = [
        "📊 **STATISTICS**",
        "",
        f"**Total Sessions**: {len(all_sessions)}",
        f"**Total Messages**: {total_messages}",
        "",
        "**By Backend**:",
    ]
    
    for backend_name in sorted(BACKENDS.keys()):
        count = backend_stats.get(backend_name, 0)
        icon = "✓" if count > 0 else "○"
        lines.append(f"  {icon} `{backend_name}`: {count} messages")
    
    text = "\n".join(lines)
    await update.message.reply_text(text, parse_mode="Markdown")


@auth_guard
async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/health — Check bridge and backend health."""
    uid = update.effective_user.id
    
    health_checks = {}
    for backend_name, backend in BACKENDS.items():
        is_healthy = hasattr(backend, 'send') and callable(backend.send)
        health_checks[backend_name] = "✅" if is_healthy else "❌"
    
    metrics_summary = metrics_collector.get_summary()
    
    lines = [
        "🏥 **HEALTH CHECK**",
        "",
        f"**Uptime**: {metrics_summary['uptime']}",
        f"**Total Messages**: {metrics_summary['total_messages']}",
        f"**Total Errors**: {metrics_summary['total_errors']}",
        "",
        "**Backends**:",
    ]
    
    for backend_name, status in sorted(health_checks.items()):
        lines.append(f"  {status} `{backend_name}`")
    
    text = "\n".join(lines)
    await update.message.reply_text(text, parse_mode="Markdown")


@auth_guard
async def replay_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/replay [limit] — Show recent conversation history."""
    uid = update.effective_user.id
    session = session_mgr.get_current(uid)
    
    limit = 10
    if context.args:
        try:
            limit = int(context.args[0])
        except (ValueError, IndexError):
            pass
    
    if not session.history:
        await update.message.reply_text("No conversation history")
        return
    
    history = session.history[-(limit * 2):]
    
    lines = ["📜 **CONVERSATION**", ""]
    for msg in history:
        role = "👤" if msg["role"] == "user" else "🤖"
        content = msg["content"]
        if len(content) > 200:
            content = content[:200] + "…"
        lines.append(f"{role} {content}")
    
    text = "\n".join(lines)
    
    if len(text) > 4096:
        chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for chunk in chunks:
            await update.message.reply_text(chunk, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")


@auth_guard
async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/config — Show current configuration."""
    uid = update.effective_user.id
    
    lines = [
        "⚙️ **CONFIGURATION**",
        "",
        f"**Default Backend**: `{DEFAULT_BACKEND}`",
        f"**Agent Timeout**: `{AGENT_TIMEOUT}s`",
        f"**Response Mode**: `{RESPONSE_MODE}`",
        f"**Max File Size**: `{format_size(MAX_FILE_SIZE)}`",
        "",
        "**Paths**:",
        f"  Kiro CLI: `{KIRO_CLI_PATH}`",
        f"  Claude Code: `{CLAUDE_CODE_PATH}`",
        f"  Aider: `{AIDER_PATH}`",
    ]
    
    text = "\n".join(lines)
    await update.message.reply_text(text, parse_mode="Markdown")


def main():
    # Python 3.10+ no longer creates an implicit event loop; PTB 21.x needs one
    # to exist on the main thread before run_polling() is called.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("new", new_session_cmd))
    app.add_handler(CommandHandler("backend", backend_command))
    app.add_handler(CommandHandler("files", list_files_command))
    app.add_handler(CommandHandler("learn", learn_command))
    
    # Debug & monitoring commands
    app.add_handler(CommandHandler("debug", debug_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("health", health_command))
    app.add_handler(CommandHandler("replay", replay_command))
    app.add_handler(CommandHandler("config", config_command))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file_upload))
    app.add_handler(CallbackQueryHandler(callback_handler))

    logger.info(f"Starting bridge — default backend: {DEFAULT_BACKEND}")
    logger.info(f"Available backends: {', '.join(BACKENDS.keys())}")
    logger.info(f"Allowed user: {TELEGRAM_ALLOWED_USER_ID}")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
