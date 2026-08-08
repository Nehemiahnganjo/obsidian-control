#!/usr/bin/env python3
"""
Debug and monitoring commands for the bridge.
"""

import logging
import asyncio
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def auth_guard(func):
    """Decorator to check user authorization."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        # Import here to avoid circular imports
        from main import TELEGRAM_ALLOWED_USER_ID
        if update.effective_user.id != TELEGRAM_ALLOWED_USER_ID:
            logger.warning(f"Unauthorized: {update.effective_user.id}")
            await update.message.reply_text("Unauthorized")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


@auth_guard
async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/debug — Show backend debug info and health."""
    from main import session_mgr, BACKENDS, BACKENDS
    
    uid = update.effective_user.id
    session = session_mgr.get_current(uid)
    backend = BACKENDS.get(session.backend)
    
    if not backend:
        await update.message.reply_text("❌ Backend not found")
        return
    
    debug_info = [
        f"🔧 DEBUG INFO",
        f"",
        f"**Backend**: {backend.name}",
        f"**Session ID**: {session.session_id}",
        f"**Working Dir**: {session.cwd}",
        f"**History Length**: {len(session.history)}",
        f"**Mood State**: {bool(getattr(session, 'mood_state', {}))}",
    ]
    
    # Backend-specific debug info
    if backend.name == "kiro":
        agent = getattr(session, 'kiro_agent', 'rick')
        mood = getattr(session, 'mood_state', {})
        debug_info.extend([\n",
            f"**Kiro Agent**: {agent}",
            f"**Mood Keys**: {', '.join(mood.keys()) if mood else 'none'}",
        ])
    
    elif backend.name == "anthropic_api":
        debug_info.append(f"**Messages in History**: {len(session.history)}")
    
    elif backend.name == "openai":
        debug_info.extend([\n",
            f"**Messages in History**: {len(session.history)}",
            f"**Base URL Configured**: {bool(context.user_data.get('openai_base_url'))}",
        ])
    
    elif backend.name == "ollama":
        debug_info.extend([\n",
            f"**Messages in History**: {len(session.history)}",
            f"**Host**: {context.user_data.get('ollama_host', 'http://localhost:11434')}",
        ])
    
    text = "\n".join(debug_info)
    await update.message.reply_text(text, parse_mode="Markdown")


@auth_guard
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/stats — Show usage statistics."""
    from main import session_mgr, BACKENDS
    
    uid = update.effective_user.id
    all_sessions = session_mgr.list_for(uid)
    
    # Count messages by backend
    backend_stats = {}
    total_messages = 0
    
    for session_name, session in all_sessions.items():
        backend_name = session.backend
        history_len = len(session.history) // 2  # Each exchange = 2 entries
        
        if backend_name not in backend_stats:
            backend_stats[backend_name] = 0
        backend_stats[backend_name] += history_len
        total_messages += history_len
    
    # Build response
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
        lines.append(f"  {icon} {backend_name}: {count} messages")
    
    text = "\n".join(lines)
    await update.message.reply_text(text, parse_mode="Markdown")


@auth_guard
async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/health — Check bridge and backend health."""
    from main import session_mgr, BACKENDS
    
    uid = update.effective_user.id
    
    # Check each backend for basic health
    health_checks = {}
    for backend_name, backend in BACKENDS.items():
        # Simple check: backend object has send method
        is_healthy = hasattr(backend, 'send') and callable(backend.send)
        health_checks[backend_name] = "✅ OK" if is_healthy else "❌ FAIL"
    
    lines = [
        "🏥 **HEALTH CHECK**",
        "",
        "**Backends**:",
    ]
    
    for backend_name, status in sorted(health_checks.items()):
        lines.append(f"  {status} {backend_name}")
    
    text = "\n".join(lines)
    await update.message.reply_text(text, parse_mode="Markdown")


@auth_guard
async def replay_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/replay [limit] — Show recent conversation history."""
    from main import session_mgr
    
    uid = update.effective_user.id
    session = session_mgr.get_current(uid)
    
    # Parse limit
    limit = 10  # default: last 10 exchanges
    if context.args:
        try:
            limit = int(context.args[0])
        except (ValueError, IndexError):
            pass
    
    if not session.history:
        await update.message.reply_text("No conversation history")
        return
    
    # Show last N exchanges
    history = session.history[-(limit * 2):]  # Each exchange = user + assistant
    
    lines = ["📜 **CONVERSATION**", ""]
    for i, msg in enumerate(history):
        role = "👤" if msg["role"] == "user" else "🤖"
        content = msg["content"]
        # Truncate long messages
        if len(content) > 200:
            content = content[:200] + "…"
        lines.append(f"{role} {content}")
    
    text = "\n".join(lines)
    
    # Split into chunks if too long
    if len(text) > 4096:
        chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for chunk in chunks:
            await update.message.reply_text(chunk, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")


@auth_guard
async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/config — Show current configuration."""
    from main import (
        DEFAULT_BACKEND, AGENT_TIMEOUT, RESPONSE_MODE, MAX_FILE_SIZE,
        KIRO_CLI_PATH, CLAUDE_CODE_PATH, AIDER_PATH
    )
    
    lines = [
        "⚙️ **CONFIGURATION**",
        "",
        f"**Default Backend**: {DEFAULT_BACKEND}",
        f"**Agent Timeout**: {AGENT_TIMEOUT}s",
        f"**Response Mode**: {RESPONSE_MODE}",
        f"**Max File Size**: {MAX_FILE_SIZE} bytes",
        "",
        "**Paths**:",
        f"  Kiro CLI: {KIRO_CLI_PATH}",
        f"  Claude Code: {CLAUDE_CODE_PATH}",
        f"  Aider: {AIDER_PATH}",
    ]
    
    text = "\n".join(lines)
    await update.message.reply_text(text, parse_mode="Markdown")
