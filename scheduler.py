#!/usr/bin/env python3
"""
Scheduler for automated fine-tuning pipeline
Triggers: data export → fine-tune → model versioning → evaluation
Runs on schedule (daily/weekly) or on-demand via command
"""

import asyncio
import json
import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import time

logger = logging.getLogger(__name__)

# ─── Configuration ────────────────────────────────────────────────────────

BRIDGE_DIR = Path("/home/void/kiro-telegram-bridge")
TRAINING_EXPORTER = BRIDGE_DIR / "training_exporter.py"
TRAINER_SCRIPT = BRIDGE_DIR / "fine_tuning" / "trainer.py"
MODELS_DIR = BRIDGE_DIR / "models"
LOGS_DIR = BRIDGE_DIR / "training_logs"
TRAINING_DATA = BRIDGE_DIR / "training_data" / "conversations.jsonl"

# Scheduling
CHECK_INTERVAL = 3600  # Check every hour
TRAINING_SCHEDULE = "daily"  # "daily", "weekly", "on-demand"
LAST_TRAINING_FILE = BRIDGE_DIR / ".last_training_timestamp"

LOGS_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)


class TrainingScheduler:
    """Schedule and manage fine-tuning pipeline"""

    def __init__(self):
        self.last_training_time = self._load_last_training_time()
        self.training_in_progress = False
        self.training_history = []

    def _load_last_training_time(self) -> Optional[datetime]:
        """Load last training timestamp"""
        if not LAST_TRAINING_FILE.exists():
            return None

        try:
            with open(LAST_TRAINING_FILE, "r") as f:
                timestamp_str = f.read().strip()
                return datetime.fromisoformat(timestamp_str)
        except Exception as e:
            logger.warning(f"Failed to load last training time: {e}")
            return None

    def _save_last_training_time(self, dt: datetime):
        """Save training timestamp"""
        with open(LAST_TRAINING_FILE, "w") as f:
            f.write(dt.isoformat())

    def should_train(self) -> bool:
        """Determine if training should run based on schedule"""
        if self.training_in_progress:
            logger.info("Training already in progress, skipping...")
            return False

        if self.last_training_time is None:
            logger.info("First training run")
            return True

        now = datetime.now()
        if TRAINING_SCHEDULE == "daily":
            delta = now - self.last_training_time
            if delta >= timedelta(hours=24):
                logger.info(
                    f"Daily training scheduled (last: {self.last_training_time.isoformat()})"
                )
                return True

        elif TRAINING_SCHEDULE == "weekly":
            delta = now - self.last_training_time
            if delta >= timedelta(days=7):
                logger.info(
                    f"Weekly training scheduled (last: {self.last_training_time.isoformat()})"
                )
                return True

        return False

    def export_training_data(self) -> bool:
        """Export conversation data from session state"""
        logger.info("=" * 60)
        logger.info("Step 1: Exporting training data...")
        logger.info("=" * 60)

        try:
            result = subprocess.run(
                ["python3", str(TRAINING_EXPORTER)],
                cwd=str(BRIDGE_DIR),
                capture_output=True,
                text=True,
                timeout=300,
            )

            logger.info(result.stdout)
            if result.stderr:
                logger.warning(result.stderr)

            if result.returncode != 0:
                logger.error(f"Data export failed with code {result.returncode}")
                return False

            # Verify data was created
            if not TRAINING_DATA.exists() or TRAINING_DATA.stat().st_size == 0:
                logger.warning("Training data file is empty")
                return False

            logger.info("✅ Training data exported successfully")
            return True

        except subprocess.TimeoutExpired:
            logger.error("Data export timed out")
            return False
        except Exception as e:
            logger.error(f"Data export failed: {e}")
            return False

    def run_fine_tuning(self) -> Optional[str]:
        """Execute fine-tuning script"""
        logger.info("=" * 60)
        logger.info("Step 2: Running fine-tuning...")
        logger.info("=" * 60)

        if not TRAINING_DATA.exists():
            logger.error("Training data not found, skipping fine-tune")
            return None

        try:
            start_time = time.time()
            result = subprocess.run(
                ["python3", str(TRAINER_SCRIPT)],
                cwd=str(BRIDGE_DIR),
                capture_output=True,
                text=True,
                timeout=86400,  # 24 hour timeout for training
            )

            logger.info(result.stdout)
            if result.stderr:
                logger.warning(result.stderr)

            elapsed = time.time() - start_time
            logger.info(f"Fine-tuning took {elapsed / 3600:.1f} hours")

            if result.returncode != 0:
                logger.error(f"Fine-tuning failed with code {result.returncode}")
                return None

            # Find latest trained model
            model_path = self._find_latest_model()
            if model_path:
                logger.info(f"✅ Fine-tuning complete: {model_path}")
                return model_path
            else:
                logger.error("No trained model found")
                return None

        except subprocess.TimeoutExpired:
            logger.error("Fine-tuning timed out (>24 hours)")
            return None
        except Exception as e:
            logger.error(f"Fine-tuning failed: {e}")
            return None

    def _find_latest_model(self) -> Optional[Path]:
        """Find most recently trained model"""
        if not MODELS_DIR.exists():
            return None

        model_dirs = sorted(
            [d for d in MODELS_DIR.iterdir() if d.is_dir()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        if model_dirs:
            return model_dirs[0]
        return None

    def evaluate_model(self, model_path: Optional[str]) -> dict:
        """Evaluate model quality (heuristic metrics)"""
        logger.info("=" * 60)
        logger.info("Step 3: Evaluating model...")
        logger.info("=" * 60)

        if not model_path:
            logger.warning("No model to evaluate")
            return {}

        metrics = {
            "model_path": model_path,
            "evaluation_date": datetime.now().isoformat(),
            "model_size_mb": (Path(model_path).stat().st_size / 1024 / 1024) if Path(model_path).exists() else 0,
            "status": "trained",
        }

        logger.info(f"Model metrics: {json.dumps(metrics, indent=2)}")
        return metrics

    def save_training_log(self, model_path: Optional[str], metrics: dict):
        """Save training run to history log"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "model_path": model_path,
            "metrics": metrics,
            "schedule": TRAINING_SCHEDULE,
        }

        log_file = LOGS_DIR / "training_history.jsonl"
        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

        logger.info(f"Training log saved to {log_file}")

    async def run_pipeline(self, force: bool = False) -> Optional[str]:
        """Run full training pipeline"""
        if not force and not self.should_train():
            return None

        self.training_in_progress = True
        logger.info("\n" + "🚀 " * 20)
        logger.info("STARTING FINE-TUNING PIPELINE")
        logger.info("🚀 " * 20 + "\n")

        try:
            # Step 1: Export data
            if not self.export_training_data():
                return None

            # Step 2: Fine-tune
            model_path = self.run_fine_tuning()
            if not model_path:
                return None

            # Step 3: Evaluate
            metrics = self.evaluate_model(model_path)

            # Step 4: Log
            self.save_training_log(model_path, metrics)
            self._save_last_training_time(datetime.now())

            logger.info("\n" + "✅ " * 20)
            logger.info("FINE-TUNING PIPELINE COMPLETE")
            logger.info("✅ " * 20)
            logger.info(f"Model saved to: {model_path}")

            return model_path

        finally:
            self.training_in_progress = False

    async def scheduler_loop(self):
        """Run scheduler in background loop"""
        logger.info("Training scheduler started")
        logger.info(f"Schedule: {TRAINING_SCHEDULE}")
        logger.info(f"Check interval: {CHECK_INTERVAL}s")

        while True:
            try:
                if self.should_train():
                    await self.run_pipeline()

                await asyncio.sleep(CHECK_INTERVAL)

            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(CHECK_INTERVAL)


async def main():
    """Run scheduler as standalone service"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(LOGS_DIR / "scheduler.log"),
            logging.StreamHandler(),
        ],
    )

    scheduler = TrainingScheduler()
    await scheduler.scheduler_loop()


if __name__ == "__main__":
    asyncio.run(main())
