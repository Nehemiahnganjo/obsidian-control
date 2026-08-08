#!/usr/bin/env python3
"""
Training data exporter
Converts session history + semantic memory into fine-tuning dataset
Output: conversations.jsonl (one conversation per line)
"""

import json
import logging
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ─── Configuration ────────────────────────────────────────────────────────

BRIDGE_DIR = Path("/home/void/kiro-telegram-bridge")
SESSION_STATE_FILE = BRIDGE_DIR / "session_state.json"
SEMANTIC_MEMORY_FILE = BRIDGE_DIR / "semantic_memory.json"
TRAINING_DATA_DIR = BRIDGE_DIR / "training_data"
OUTPUT_FILE = TRAINING_DATA_DIR / "conversations.jsonl"

TRAINING_DATA_DIR.mkdir(parents=True, exist_ok=True)


class TrainingDataExporter:
    """Export conversations to fine-tuning format"""

    def __init__(self):
        self.session_state = {}
        self.semantic_memory = {}
        self.conversations = []

    def load_session_state(self) -> bool:
        """Load session state from JSON file"""
        if not SESSION_STATE_FILE.exists():
            logger.warning(f"Session state file not found: {SESSION_STATE_FILE}")
            return False

        try:
            with open(SESSION_STATE_FILE, "r") as f:
                self.session_state = json.load(f)
                logger.info(f"Loaded session state with {len(self.session_state)} sessions")
                return True
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse session state: {e}")
            return False

    def load_semantic_memory(self) -> bool:
        """Load semantic facts from memory file"""
        if not SEMANTIC_MEMORY_FILE.exists():
            logger.warning(f"Semantic memory file not found: {SEMANTIC_MEMORY_FILE}")
            return False

        try:
            with open(SEMANTIC_MEMORY_FILE, "r") as f:
                self.semantic_memory = json.load(f)
                logger.info(f"Loaded semantic memory with {len(self.semantic_memory)} facts")
                return True
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse semantic memory: {e}")
            return False

    def extract_conversations(self) -> int:
        """Extract conversations from session state"""
        count = 0

        for session_id, session_data in self.session_state.items():
            if not isinstance(session_data, dict):
                continue

            history = session_data.get("history", [])
            if not history or len(history) < 2:  # Need at least one exchange
                continue

            persona = session_data.get("kiro_agent", "rick")
            mood_state = session_data.get("mood_state", {})
            updated_at = session_data.get("updated_at", datetime.now().isoformat())

            # Build conversation record
            conversation = {
                "session_id": session_id,
                "persona": persona,
                "mood_state": mood_state,
                "timestamp": updated_at,
                "conversation": history,
            }

            self.conversations.append(conversation)
            count += 1

        logger.info(f"Extracted {count} conversations from session state")
        return count

    def validate_and_deduplicate(self) -> int:
        """Remove duplicates and validate conversation quality"""
        original_count = len(self.conversations)

        # Deduplicate by conversation content hash
        seen_hashes = set()
        deduplicated = []

        for conv in self.conversations:
            # Create hash from conversation content
            conv_text = " ".join(
                [msg.get("content", "") for msg in conv.get("conversation", [])]
            )
            conv_hash = hash(conv_text[:200])  # Use first 200 chars

            if conv_hash not in seen_hashes:
                seen_hashes.add(conv_hash)
                deduplicated.append(conv)

        self.conversations = deduplicated
        removed = original_count - len(self.conversations)
        logger.info(f"Deduplication: removed {removed} duplicates, kept {len(self.conversations)}")

        return len(self.conversations)

    def balance_by_persona(self) -> Dict[str, int]:
        """Log persona distribution"""
        persona_counts = {}
        for conv in self.conversations:
            persona = conv.get("persona", "unknown")
            persona_counts[persona] = persona_counts.get(persona, 0) + 1

        logger.info("Persona distribution:")
        for persona, count in persona_counts.items():
            logger.info(f"  {persona}: {count}")

        return persona_counts

    def export_to_jsonl(self) -> Path:
        """Export conversations to JSONL format"""
        with open(OUTPUT_FILE, "w") as f:
            for conv in self.conversations:
                f.write(json.dumps(conv) + "\n")

        logger.info(f"Exported {len(self.conversations)} conversations to {OUTPUT_FILE}")
        return OUTPUT_FILE

    def generate_stats(self) -> Dict:
        """Generate training dataset statistics"""
        stats = {
            "total_conversations": len(self.conversations),
            "timestamp": datetime.now().isoformat(),
            "persona_distribution": self.balance_by_persona(),
            "total_turns": sum(
                len(conv.get("conversation", [])) for conv in self.conversations
            ),
            "avg_conversation_length": (
                sum(len(conv.get("conversation", [])) for conv in self.conversations)
                / max(len(self.conversations), 1)
            ),
        }

        # Calculate message statistics
        all_messages = []
        for conv in self.conversations:
            for msg in conv.get("conversation", []):
                content = msg.get("content", "")
                if content:
                    all_messages.append(len(content.split()))

        if all_messages:
            stats["avg_message_length_words"] = sum(all_messages) / len(all_messages)
            stats["total_words"] = sum(all_messages)

        return stats

    def run(self) -> bool:
        """Run full export pipeline"""
        logger.info("=" * 60)
        logger.info("Training Data Exporter")
        logger.info("=" * 60)

        # Load data
        if not self.load_session_state():
            logger.warning("No session state to export")

        self.load_semantic_memory()

        # Extract and process
        if self.extract_conversations() == 0:
            logger.warning("No conversations found in session state")
            # Create empty JSONL file for training script compatibility
            with open(OUTPUT_FILE, "w") as f:
                pass
            return False

        self.validate_and_deduplicate()
        self.balance_by_persona()

        # Export
        self.export_to_jsonl()

        # Stats
        stats = self.generate_stats()
        stats_file = TRAINING_DATA_DIR / "training_stats.json"
        with open(stats_file, "w") as f:
            json.dump(stats, f, indent=2)

        logger.info("\nTraining Dataset Statistics:")
        logger.info(f"  Total conversations: {stats['total_conversations']}")
        logger.info(f"  Total turns: {stats['total_turns']}")
        logger.info(f"  Avg conversation length: {stats['avg_conversation_length']:.1f} turns")
        if "avg_message_length_words" in stats:
            logger.info(f"  Avg message: {stats['avg_message_length_words']:.1f} words")
            logger.info(f"  Total training words: {stats['total_words']}")

        logger.info(f"\n✅ Export complete!")
        logger.info(f"   Data: {OUTPUT_FILE}")
        logger.info(f"   Stats: {stats_file}")

        return True


if __name__ == "__main__":
    exporter = TrainingDataExporter()
    success = exporter.run()
    exit(0 if success else 1)
