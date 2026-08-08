"""
Consolidation Job — extract facts from session_state.json conversations.

Runs after conversations end, identifies learnable patterns, deduplicates, resolves contradictions.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


class ConsolidationJob:
    """Extract semantic facts from session history via LLM reflection (or pattern matching)."""
    
    def __init__(self, session_state_path: Path, semantic_memory):
        self.session_state_path = session_state_path
        self.memory = semantic_memory
    
    def run(self, min_turns: int = 5):
        """
        Process recent conversations, extract facts, update semantic memory.
        Only processes sessions with at least min_turns exchanges.
        """
        if not self.session_state_path.exists():
            logger.warning("No session state file found")
            return
        
        try:
            data = json.loads(self.session_state_path.read_text())
        except Exception as e:
            logger.error(f"Failed to read session state: {e}")
            return
        
        total_extracted = 0
        for uid_str, udata in data.items():
            for session_name, session_data in udata.get("sessions", {}).items():
                history = session_data.get("history", [])
                session_id = session_data.get("session_id", "unknown")
                
                if len(history) < min_turns:
                    continue
                
                # Extract facts from this conversation
                facts = self._extract_facts(history, session_id)
                for fact_content, category in facts:
                    self.memory.add_fact(fact_content, category, session_id)
                    total_extracted += 1
        
        # Prune old facts
        self.memory.prune_stale(days=30)
        self.memory.save()
        logger.info(f"Consolidation complete: extracted {total_extracted} facts")
    
    def _extract_facts(self, history: List[dict], session_id: str) -> List[tuple]:
        """
        Extract learnable patterns from conversation history.
        Returns list of (fact_content, category) tuples.
        
        Patterns:
        - User message length trends → preference for verbosity
        - Technical topic interest → topic_history
        - Response patterns → interaction_pattern
        - Explicit statements → user_preference
        """
        facts = []
        
        if len(history) < 2:
            return facts
        
        # Analyze message length trend
        user_msgs = [turn["content"] for turn in history if turn["role"] == "user"]
        avg_len = sum(len(m.split()) for m in user_msgs) / len(user_msgs)
        
        if avg_len < 5:
            facts.append(("User tends to keep messages brief and direct", "interaction_pattern"))
        elif avg_len > 30:
            facts.append(("User provides detailed context and context in messages", "user_preference"))
        
        # Topic analysis: keywords in user messages
        all_user_text = " ".join(user_msgs).lower()
        tech_keywords = {"code", "api", "database", "algorithm", "system", "function", 
                        "query", "debug", "optimize", "architecture", "deploy"}
        tech_count = sum(1 for kw in tech_keywords if kw in all_user_text)
        
        if tech_count >= 3:
            facts.append(("User frequently asks technical/coding questions", "topic_history"))
        
        # Look for explicit preferences in conversation
        if any(phrase in all_user_text for phrase in ["short answer", "brief", "tl;dr", "quickly"]):
            facts.append(("User prefers concise, quick answers", "user_preference"))
        
        if any(phrase in all_user_text for phrase in ["explain", "why", "how", "details"]):
            facts.append(("User likes detailed explanations and reasoning", "user_preference"))
        
        # Interaction pattern: response to corrections
        last_assistant = history[-2]["content"] if len(history) >= 2 and history[-2]["role"] == "assistant" else ""
        last_user = history[-1]["content"] if history[-1]["role"] == "user" else ""
        
        if any(phrase in last_user.lower() for phrase in ["right", "correct", "thanks", "good", "perfect"]):
            facts.append(("User acknowledges correct answers positively", "interaction_pattern"))
        
        if any(phrase in last_user.lower() for phrase in ["wrong", "no", "incorrect", "that's not"]):
            facts.append(("User corrects inaccurate information directly", "interaction_pattern"))
        
        # Deduplication happens in SemanticMemory.add_fact via _hash_fact
        return facts
