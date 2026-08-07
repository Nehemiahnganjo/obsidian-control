#!/usr/bin/env python3
"""
kiro-telegram-bridge — Multi-backend version
Supports kiro-cli, Claude Code CLI, Anthropic API, Ollama, or any custom CLI agent.
Switch backends per-session via /backend command or AGENT_BACKEND env var.
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

BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
KIRO_WORKDIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


# ── Session model ────────────────────────────────────────────────────────

@dataclass
class Session:
    """A conversation context: which backend, which session/history, which dir."""
    backend: str = DEFAULT_BACKEND
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    cwd: str = str(KIRO_WORKDIR)
    history: List[dict] = field(default_factory=list)  # used by API-style backends
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


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
    """kiro-cli — resume-id based session continuity."""

    name = "kiro"

    async def send(self, message, session):
        agent = os.getenv("KIRO_AGENT", "rick")
        cmd = [
            KIRO_CLI_PATH, "chat",
            "--no-interactive",
            "--trust-all-tools",
            "--wrap", "never",
            "--agent", agent,
            "--resume-id", session.session_id,
            message,
        ]
        return await self._run_subprocess(cmd, session.cwd, AGENT_TIMEOUT)


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
    text = update.message.text
    session = session_mgr.get_current(uid)
    backend = get_backend(session.backend)

    status_msg = await update.message.reply_text(f"⏳ [{session.backend}]…")

    lock = get_lock(uid)
    async with lock:
        output, error = await backend.send(text, session)
        session.updated_at = datetime.now().isoformat()
        session_mgr.save()

    if error:
        await status_msg.edit_text(f"❌ [{session.backend}] Error:\n```\n{error}\n```", parse_mode="Markdown")
        return

    output = filter_response(output)
    if not output:
        await status_msg.edit_text("(no output)")
        return

    chunks = split_message(output)
    await status_msg.edit_text(chunks[0])
    for chunk in chunks[1:]:
        await update.message.reply_text(chunk)


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

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file_upload))
    app.add_handler(CallbackQueryHandler(callback_handler))

    logger.info(f"Starting bridge — default backend: {DEFAULT_BACKEND}")
    logger.info(f"Available backends: {', '.join(BACKENDS.keys())}")
    logger.info(f"Allowed user: {TELEGRAM_ALLOWED_USER_ID}")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
