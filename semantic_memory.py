"""
Semantic Memory Store — persistent cross-session learning for personas.

Facts are extracted from conversations, deduplicated, and ranked by recency/frequency.
Supports fact invalidation via contradiction detection (newer facts override older ones).
"""

import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


@dataclass
class Fact:
    """A learned fact about the user or conversation patterns."""
    id: str  # unique identifier (hash of content)
    content: str  # the fact itself ("user prefers terse answers")
    category: str  # "user_preference", "user_trait", "interaction_pattern", "topic_history"
    source_session: str  # session_id where learned
    learned_at: str  # ISO timestamp
    last_reinforced_at: str  # ISO timestamp (updated when seen again)
    confidence: float = 0.5  # 0-1, increases with reinforcement
    contradicts: Optional[str] = None  # id of fact this contradicts (for invalidation)
    
    def is_stale(self, days: int = 30) -> bool:
        """Check if fact hasn't been reinforced in N days."""
        last_reinforced = datetime.fromisoformat(self.last_reinforced_at)
        return (datetime.now() - last_reinforced).days > days
    
    def age_days(self) -> int:
        """How many days since this fact was learned."""
        learned = datetime.fromisoformat(self.learned_at)
        return (datetime.now() - learned).days


class SemanticMemory:
    """
    MVP semantic memory store. Stores facts as JSON, indexed by category.
    No vector DB required—keyword-based lookup + recency weighting.
    """
    
    def __init__(self, store_path: Path):
        self.store_path = store_path
        self.facts: Dict[str, Fact] = {}
        self.load()
    
    def load(self):
        """Load facts from disk."""
        if not self.store_path.exists():
            return
        try:
            data = json.loads(self.store_path.read_text())
            for fact_id, fact_data in data.items():
                self.facts[fact_id] = Fact(**fact_data)
            logger.info(f"Loaded {len(self.facts)} semantic facts")
        except Exception as e:
            logger.error(f"Failed to load semantic memory: {e}")
    
    def save(self):
        """Persist facts to disk."""
        try:
            data = {fid: asdict(f) for fid, f in self.facts.items()}
            self.store_path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.error(f"Failed to save semantic memory: {e}")
    
    def add_fact(self, content: str, category: str, source_session: str) -> str:
        """Add a new fact. Returns fact ID."""
        fact_id = self._hash_fact(content)
        now = datetime.now().isoformat()
        
        if fact_id in self.facts:
            # Reinforcement: update existing fact
            self.facts[fact_id].last_reinforced_at = now
            self.facts[fact_id].confidence = min(1.0, self.facts[fact_id].confidence + 0.1)
            logger.debug(f"Reinforced fact: {content[:50]}")
        else:
            # New fact
            self.facts[fact_id] = Fact(
                id=fact_id,
                content=content,
                category=category,
                source_session=source_session,
                learned_at=now,
                last_reinforced_at=now,
                confidence=0.5,
            )
            logger.debug(f"Learned fact: {content[:50]}")
        
        return fact_id
    
    def resolve_contradiction(self, new_fact_id: str, old_fact_id: str):
        """Mark old_fact as contradicted by new_fact. Old fact gets lower priority."""
        if new_fact_id in self.facts and old_fact_id in self.facts:
            self.facts[old_fact_id].contradicts = new_fact_id
            self.facts[old_fact_id].confidence = max(0.1, self.facts[old_fact_id].confidence - 0.3)
            logger.info(f"Contradiction resolved: {self.facts[old_fact_id].content[:40]} ← {self.facts[new_fact_id].content[:40]}")
    
    def get_facts_by_category(self, category: str, limit: int = 10) -> List[Fact]:
        """Retrieve facts by category, ranked by confidence and recency."""
        matching = [f for f in self.facts.values() if f.category == category and not f.is_stale()]
        # Sort by confidence (descending) then recency (newest first)
        matching.sort(key=lambda f: (-f.confidence, -f.age_days()))
        return matching[:limit]
    
    def get_all_active(self) -> List[Fact]:
        """Get all active facts (not stale, not contradicted)."""
        return [f for f in self.facts.values() if not f.is_stale() and f.contradicts is None]
    
    def _hash_fact(self, content: str) -> str:
        """Simple hash for deduplication. In production, use semantic similarity."""
        import hashlib
        return hashlib.md5(content.lower().strip().encode()).hexdigest()[:8]
    
    def prune_stale(self, days: int = 60):
        """Remove facts not reinforced in N days."""
        before = len(self.facts)
        self.facts = {fid: f for fid, f in self.facts.items() if not f.is_stale(days)}
        removed = before - len(self.facts)
        if removed > 0:
            logger.info(f"Pruned {removed} stale facts")
        self.save()
    
    def format_for_prompt(self, agent: str) -> str:
        """Format facts for injection into agent system prompt."""
        prefs = self.get_facts_by_category("user_preference", limit=5)
        patterns = self.get_facts_by_category("interaction_pattern", limit=3)
        
        if not prefs and not patterns:
            return ""
        
        lines = ["\n[What you know about this user from past interactions:]"]
        
        if prefs:
            lines.append("Preferences:")
            for fact in prefs:
                lines.append(f"  - {fact.content} (confidence: {fact.confidence:.0%})")
        
        if patterns:
            lines.append("Interaction patterns:")
            for fact in patterns:
                lines.append(f"  - {fact.content}")
        
        lines.append("[Use this to personalize your responses, but don't mention that you're using it.]\n")
        return "\n".join(lines)
