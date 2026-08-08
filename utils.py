#!/usr/bin/env python3
"""
Utility functions for retry logic, validation, and metrics.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Tuple, Optional, Any, Dict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


# ── Retry Logic ──────────────────────────────────────────────────────────

@dataclass
class RetryConfig:
    """Configurable retry behavior."""
    max_retries: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 30.0  # max backoff
    backoff_multiplier: float = 2.0
    jitter: bool = True


async def retry_async(
    func: Callable,
    *args,
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable] = None,
    **kwargs
) -> Tuple[Any, Optional[str]]:
    """
    Execute an async function with exponential backoff retry.
    
    Returns: (result, error)
    - If successful: (result, None)
    - If all retries exhausted: (None, error_message)
    """
    config = config or RetryConfig()
    last_error = None
    
    for attempt in range(config.max_retries + 1):
        try:
            result = await func(*args, **kwargs)
            if attempt > 0:
                logger.info(f"Recovered after {attempt} retries: {func.__name__}")
            return result, None
        except Exception as e:
            last_error = str(e)
            if attempt < config.max_retries:
                delay = min(
                    config.base_delay * (config.backoff_multiplier ** attempt),
                    config.max_delay
                )
                if config.jitter:
                    import random
                    delay = delay * (0.5 + random.random())
                
                logger.warning(
                    f"Attempt {attempt + 1}/{config.max_retries + 1} failed for {func.__name__}: {e}. "
                    f"Retrying in {delay:.1f}s"
                )
                
                if on_retry:
                    await on_retry(attempt, delay, e)
                
                await asyncio.sleep(delay)
            else:
                logger.error(f"All {config.max_retries + 1} attempts failed for {func.__name__}: {e}")
    
    return None, last_error


# ── Input Validation ─────────────────────────────────────────────────────

MAX_MESSAGE_LENGTH = 4000
MAX_SESSION_NAME_LENGTH = 50
MAX_COMMAND_LENGTH = 500

def validate_message(message: str) -> Tuple[bool, Optional[str]]:
    """Validate user message."""
    if not message:
        return False, "Empty message"
    if len(message) > MAX_MESSAGE_LENGTH:
        return False, f"Message too long (max {MAX_MESSAGE_LENGTH} chars)"
    return True, None


def validate_session_name(name: str) -> Tuple[bool, Optional[str]]:
    """Validate session name."""
    if not name:
        return False, "Empty session name"
    if len(name) > MAX_SESSION_NAME_LENGTH:
        return False, f"Session name too long (max {MAX_SESSION_NAME_LENGTH} chars)"
    if not name.replace("_", "").replace("-", "").isalnum():
        return False, "Session name can only contain alphanumeric, - and _"
    return True, None


def sanitize_command(cmd: str) -> str:
    """Remove potentially dangerous characters from commands."""
    # Remove null bytes and control characters
    return "".join(c for c in cmd if ord(c) >= 32 or c in "\t\n\r")


# ── Metrics Collection ───────────────────────────────────────────────────

@dataclass
class BackendMetrics:
    """Metrics for a single backend."""
    name: str
    message_count: int = 0
    error_count: int = 0
    total_time: float = 0.0  # seconds
    last_error: Optional[str] = None
    last_used: Optional[datetime] = None
    response_times: list = field(default_factory=list)  # recent response times for percentile calc
    
    def record_success(self, response_time: float):
        """Record a successful message."""
        self.message_count += 1
        self.total_time += response_time
        self.response_times.append(response_time)
        self.last_used = datetime.now()
        # Keep only last 100 response times
        if len(self.response_times) > 100:
            self.response_times = self.response_times[-100:]
    
    def record_error(self, error: str):
        """Record an error."""
        self.error_count += 1
        self.last_error = error
        self.last_used = datetime.now()
    
    def avg_response_time(self) -> float:
        """Average response time."""
        if self.message_count == 0:
            return 0.0
        return self.total_time / self.message_count
    
    def p95_response_time(self) -> float:
        """95th percentile response time."""
        if len(self.response_times) < 2:
            return self.avg_response_time()
        sorted_times = sorted(self.response_times)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[idx]
    
    def error_rate(self) -> float:
        """Error rate (0.0 to 1.0)."""
        total = self.message_count + self.error_count
        if total == 0:
            return 0.0
        return self.error_count / total
    
    def to_dict(self) -> Dict:
        """Serialize for logging."""
        return {
            "name": self.name,
            "messages": self.message_count,
            "errors": self.error_count,
            "error_rate": f"{self.error_rate() * 100:.1f}%",
            "avg_response_time": f"{self.avg_response_time():.2f}s",
            "p95_response_time": f"{self.p95_response_time():.2f}s",
            "last_error": self.last_error,
            "last_used": self.last_used.isoformat() if self.last_used else None,
        }


class MetricsCollector:
    """Collect and manage metrics across all backends."""
    
    def __init__(self):
        self.backends: Dict[str, BackendMetrics] = {}
        self.start_time = datetime.now()
    
    def get_metrics(self, backend_name: str) -> BackendMetrics:
        """Get or create metrics for a backend."""
        if backend_name not in self.backends:
            self.backends[backend_name] = BackendMetrics(name=backend_name)
        return self.backends[backend_name]
    
    def record_backend_call(
        self,
        backend_name: str,
        response_time: float,
        error: Optional[str] = None
    ):
        """Record a backend call."""
        metrics = self.get_metrics(backend_name)
        if error:
            metrics.record_error(error)
        else:
            metrics.record_success(response_time)
    
    def get_summary(self) -> Dict:
        """Get overall metrics summary."""
        uptime = datetime.now() - self.start_time
        total_messages = sum(m.message_count for m in self.backends.values())
        total_errors = sum(m.error_count for m in self.backends.values())
        
        return {
            "uptime": str(uptime).split('.')[0],  # HH:MM:SS format
            "total_messages": total_messages,
            "total_errors": total_errors,
            "backends": {
                name: metrics.to_dict()
                for name, metrics in self.backends.items()
            },
        }
    
    def log_summary(self):
        """Log metrics summary."""
        summary = self.get_summary()
        logger.info(
            f"Metrics — Uptime: {summary['uptime']}, "
            f"Messages: {summary['total_messages']}, "
            f"Errors: {summary['total_errors']}"
        )
        for backend_name, metrics in summary['backends'].items():
            if metrics['messages'] > 0:
                logger.info(
                    f"  {backend_name}: {metrics['messages']} msgs, "
                    f"{metrics['error_rate']} error rate, "
                    f"avg {metrics['avg_response_time']} / p95 {metrics['p95_response_time']}"
                )


# ── Rate Limiting ────────────────────────────────────────────────────────

@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    max_messages_per_second: float = 5.0
    window_size: float = 1.0  # seconds


class RateLimiter:
    """Per-user rate limiter using sliding window."""
    
    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        self.user_windows: Dict[int, list] = {}  # user_id -> list of timestamps
    
    def check_and_record(self, user_id: int) -> Tuple[bool, float]:
        """
        Check if user can send a message.
        
        Returns: (allowed, wait_seconds)
        - allowed=True: user can send immediately
        - allowed=False, wait_seconds > 0: user should wait before sending
        """
        now = time.time()
        if user_id not in self.user_windows:
            self.user_windows[user_id] = []
        
        window = self.user_windows[user_id]
        cutoff = now - self.config.window_size
        
        # Remove old entries outside window
        window[:] = [ts for ts in window if ts > cutoff]
        
        # Check if limit exceeded
        if len(window) >= self.config.max_messages_per_second:
            # Calculate wait time
            wait_until = window[0] + self.config.window_size
            wait_seconds = max(0, wait_until - now)
            return False, wait_seconds
        
        # Record this message
        window.append(now)
        return True, 0.0


# ── Session Cleanup ──────────────────────────────────────────────────────

@dataclass
class SessionCleanupConfig:
    """Session cleanup configuration."""
    inactive_timeout: timedelta = field(default_factory=lambda: timedelta(hours=1))
    check_interval: timedelta = field(default_factory=lambda: timedelta(minutes=5))


class SessionCleaner:
    """Periodic session cleanup."""
    
    def __init__(self, config: Optional[SessionCleanupConfig] = None):
        self.config = config or SessionCleanupConfig()
        self.last_cleanup = datetime.now()
    
    def should_cleanup(self) -> bool:
        """Check if cleanup is due."""
        return (datetime.now() - self.last_cleanup) >= self.config.check_interval
    
    def should_remove_session(self, last_activity: datetime) -> bool:
        """Check if a session should be removed."""
        inactive_duration = datetime.now() - last_activity
        return inactive_duration >= self.config.inactive_timeout
    
    def mark_cleanup_done(self):
        """Mark cleanup as completed."""
        self.last_cleanup = datetime.now()


# ── Health Checks ────────────────────────────────────────────────────────

@dataclass
class HealthStatus:
    """Health status of the bridge."""
    healthy: bool
    uptime: str
    message_count: int
    error_count: int
    error_rate: float
    backends_available: int
    backends_total: int
    issues: list = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "healthy": self.healthy,
            "uptime": self.uptime,
            "message_count": self.message_count,
            "error_count": self.error_count,
            "error_rate": f"{self.error_rate * 100:.1f}%",
            "backends_available": f"{self.backends_available}/{self.backends_total}",
            "issues": self.issues,
        }


async def check_backend_health(backend) -> bool:
    """Async check if a backend is responsive."""
    try:
        # This is a placeholder — actual implementation depends on backend type
        # For now, we just check if the backend object exists
        return hasattr(backend, 'send') and callable(backend.send)
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return False
