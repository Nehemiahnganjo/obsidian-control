#!/usr/bin/env python3
"""
Fine-tuning trainer for Llama-3.2-1B-Uncensored with LoRA
Trains on conversation data from Telegram bridge
Optimized for CPU-only inference (Intel i5-6300U, 32GB RAM)
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional
from datetime import datetime
import torch
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling,
)
from datasets import Dataset
from peft import LoraConfig, get_peft_model, TaskType

# ─── Configuration ────────────────────────────────────────────────────────

BASE_MODEL = "nztinversive/llama3.2-1b-Uncensored"
OUTPUT_DIR = Path("/home/void/kiro-telegram-bridge/models")
TRAINING_DATA_FILE = Path("/home/void/kiro-telegram-bridge/training_data/conversations.jsonl")
LOGS_DIR = Path("/home/void/kiro-telegram-bridge/training_logs")

# Model size constraints (32GB RAM, Intel i5-6300U)
MAX_SEQ_LENGTH = 512
BATCH_SIZE = 1  # CPU training: tiny batch
GRADIENT_ACCUMULATION_STEPS = 4  # Accumulate 4 steps = effective batch 4
EPOCHS = 3
LEARNING_RATE = 2e-4
WARMUP_STEPS = 100
WEIGHT_DECAY = 0.01

# LoRA config
LORA_R = 8
LORA_ALPHA = 16
LORA_DROPOUT = 0.05
LORA_TARGET_MODULES = ["q_proj", "v_proj"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class ConversationDataset(Dataset):
    """Load conversation data from JSONL training file"""

    @staticmethod
    def load_from_file(filepath: Path, tokenizer, max_length: int = 512):
        """Load and tokenize conversations"""
        conversations = []
        
        if not filepath.exists():
            logger.warning(f"Training file not found: {filepath}")
            return None

        with open(filepath, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        data = json.loads(line)
                        conversations.append(data)
                    except json.JSONDecodeError:
                        logger.warning(f"Skipping malformed JSON: {line[:50]}")
                        continue

        if not conversations:
            logger.warning("No conversations loaded from training file")
            return None

        # Format conversations as chat sequences
        texts = []
        for conv in conversations:
            # Extract conversation history
            history = conv.get("conversation", [])
            if not history:
                continue

            # Build text from alternating user/assistant messages
            text = ""
            for msg in history:
                role = msg.get("role", "user")
                content = msg.get("content", "").strip()
                if role == "user":
                    text += f"\nUser: {content}\n"
                elif role == "assistant":
                    text += f"Assistant: {content}\n"

            if text:
                texts.append(text)

        logger.info(f"Loaded {len(texts)} conversation sequences")

        # Tokenize
        encodings = tokenizer(
            texts,
            truncation=True,
            max_length=max_length,
            padding="max_length",
            return_tensors="pt",
        )

        dataset = Dataset.from_dict(encodings)
        return dataset


def train_model(
    training_data_file: Path,
    output_dir: Path,
    resume_from_checkpoint: Optional[str] = None,
) -> str:
    """Fine-tune Llama-3.2-1B with LoRA"""

    logger.info(f"Starting fine-tuning of {BASE_MODEL}")
    logger.info(f"Training data: {training_data_file}")
    logger.info(f"Output directory: {output_dir}")

    # Create output dirs
    output_dir.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Load tokenizer and model
    logger.info("Loading tokenizer and base model...")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.float32,  # CPU-friendly
        device_map="auto",
        low_cpu_mem_usage=True,
    )
    logger.info(f"Model loaded. Total params: {model.num_parameters():,}")

    # Load training data
    logger.info("Loading and tokenizing training data...")
    train_dataset = ConversationDataset.load_from_file(
        training_data_file, tokenizer, MAX_SEQ_LENGTH
    )

    if train_dataset is None or len(train_dataset) == 0:
        logger.error("No training data available!")
        return None

    logger.info(f"Training dataset size: {len(train_dataset)}")

    # Setup LoRA
    logger.info("Setting up LoRA...")
    lora_config = LoraConfig(
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
        target_modules=LORA_TARGET_MODULES,
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Training arguments (CPU-optimized)
    training_args = TrainingArguments(
        output_dir=str(output_dir / "checkpoints"),
        num_train_epochs=EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRADIENT_ACCUMULATION_STEPS,
        learning_rate=LEARNING_RATE,
        warmup_steps=WARMUP_STEPS,
        weight_decay=WEIGHT_DECAY,
        logging_dir=str(LOGS_DIR),
        logging_steps=10,
        save_strategy="epoch",
        save_total_limit=3,
        disable_tqdm=False,
        fp16=False,  # CPU doesn't support fp16
        bf16=False,
        optim="adamw_torch",
        seed=42,
        dataloader_num_workers=0,  # CPU-safe
        remove_unused_columns=True,
    )

    # Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        data_collator=DataCollatorForLanguageModeling(tokenizer, mlm=False),
    )

    # Train
    logger.info("Starting training...")
    try:
        trainer.train(resume_from_checkpoint=resume_from_checkpoint)
        logger.info("Training completed!")
    except Exception as e:
        logger.error(f"Training failed: {e}")
        raise

    # Save final model
    final_model_path = output_dir / f"llama-3.2-1b-uncensored-lora-v1"
    logger.info(f"Saving model to {final_model_path}")
    model.save_pretrained(final_model_path)
    tokenizer.save_pretrained(final_model_path)

    # Save training metadata
    metadata = {
        "base_model": BASE_MODEL,
        "training_date": datetime.now().isoformat(),
        "model_path": str(final_model_path),
        "lora_config": {
            "r": LORA_R,
            "alpha": LORA_ALPHA,
            "dropout": LORA_DROPOUT,
            "target_modules": LORA_TARGET_MODULES,
        },
        "training_config": {
            "epochs": EPOCHS,
            "batch_size": BATCH_SIZE,
            "learning_rate": LEARNING_RATE,
            "max_seq_length": MAX_SEQ_LENGTH,
        },
        "training_samples": len(train_dataset),
    }

    metadata_path = output_dir / "training_metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"Metadata saved to {metadata_path}")
    logger.info(f"✅ Fine-tuning complete! Model: {final_model_path}")

    return str(final_model_path)


if __name__ == "__main__":
    # Check training data exists
    if not TRAINING_DATA_FILE.exists():
        logger.error(
            f"Training data not found: {TRAINING_DATA_FILE}\n"
            f"Run: python3 training_exporter.py first"
        )
        exit(1)

    # Run training
    model_path = train_model(TRAINING_DATA_FILE, OUTPUT_DIR)
    if model_path:
        logger.info(f"✅ Model saved at: {model_path}")
