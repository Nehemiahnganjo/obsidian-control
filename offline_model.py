#!/usr/bin/env python3
"""
Offline Model Backend
Runs fine-tuned Llama-3.2-1B locally without external services
Compatible with KiroBackend interface for drop-in replacement
"""

import asyncio
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from datetime import datetime

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

logger = logging.getLogger(__name__)


@dataclass
class OfflineConfig:
    """Configuration for offline model inference"""
    base_model: str = "nztinversive/llama3.2-1b-Uncensored"
    lora_model: Optional[str] = None  # Path to fine-tuned LoRA weights
    device: str = "cpu"  # Always CPU for compatibility
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.95
    top_k: int = 40
    repetition_penalty: float = 1.0


class OfflineBackend:
    """
    Offline inference backend for Llama-3.2-1B
    Loads model once at startup, keeps in RAM
    Provides async send() method compatible with KiroBackend
    """

    def __init__(self, config: Optional[OfflineConfig] = None):
        self.config = config or OfflineConfig()
        self.tokenizer: Optional[AutoTokenizer] = None
        self.model: Optional[AutoModelForCausalLM] = None
        self.ready = False

        logger.info(f"OfflineBackend initialized with config:")
        logger.info(f"  Base model: {self.config.base_model}")
        logger.info(f"  LoRA model: {self.config.lora_model}")
        logger.info(f"  Device: {self.config.device}")

    def load_model(self) -> bool:
        """Load base model and LoRA weights if available"""
        try:
            logger.info(f"Loading model {self.config.base_model}...")
            self.tokenizer = AutoTokenizer.from_pretrained(self.config.base_model)
            
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token

            # Load base model
            self.model = AutoModelForCausalLM.from_pretrained(
                self.config.base_model,
                torch_dtype=torch.float32,
                device_map="auto",
                low_cpu_mem_usage=True,
            )

            # Load LoRA weights if available
            if self.config.lora_model and Path(self.config.lora_model).exists():
                logger.info(f"Loading LoRA weights from {self.config.lora_model}...")
                self.model = PeftModel.from_pretrained(
                    self.model,
                    self.config.lora_model,
                )
                logger.info("LoRA weights loaded successfully")
            else:
                logger.info("No LoRA weights provided, using base model")

            # Move to eval mode
            self.model.eval()
            self.ready = True
            logger.info(f"✅ Model loaded successfully. Total params: {self.model.num_parameters():,}")
            return True

        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            self.ready = False
            return False

    async def send(
        self,
        message: str,
        session_id: Optional[str] = None,
        agent: Optional[str] = None,
        **kwargs,
    ) -> Optional[str]:
        """
        Generate response (async wrapper around sync inference)
        Matches KiroBackend.send() signature for drop-in replacement
        """
        if not self.ready:
            logger.error("Model not loaded. Call load_model() first.")
            return None

        try:
            # Run inference in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                self._generate_response,
                message,
            )
            return response

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return None

    def _generate_response(self, message: str) -> str:
        """Synchronous inference (runs in executor)"""
        start_time = time.time()

        try:
            # Prepare prompt
            system_prompt = "You are a helpful AI assistant."
            formatted_message = f"<s>[INST] {system_prompt}\n\n{message} [/INST]"

            # Tokenize
            inputs = self.tokenizer(
                formatted_message,
                return_tensors="pt",
                truncation=True,
                max_length=self.config.max_tokens,
            )

            # Generate
            with torch.no_grad():
                outputs = self.model.generate(
                    inputs["input_ids"],
                    max_new_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                    top_p=self.config.top_p,
                    top_k=self.config.top_k,
                    repetition_penalty=self.config.repetition_penalty,
                    do_sample=True,
                    pad_token_id=self.tokenizer.eos_token_id,
                )

            # Decode
            response = self.tokenizer.decode(
                outputs[0][inputs["input_ids"].shape[-1] :],
                skip_special_tokens=True,
            ).strip()

            elapsed = time.time() - start_time
            logger.info(f"Generated response in {elapsed:.2f}s ({len(response.split())} words)")

            return response

        except Exception as e:
            logger.error(f"Error in _generate_response: {e}")
            return None

    def unload(self):
        """Unload model from memory"""
        if self.model is not None:
            del self.model
            torch.cuda.empty_cache() if torch.cuda.is_available() else None
        self.ready = False
        logger.info("Model unloaded")


# ─── Testing ──────────────────────────────────────────────────────────

async def test_inference():
    """Quick test of offline inference"""
    config = OfflineConfig(
        base_model="nztinversive/llama3.2-1b-Uncensored",
        lora_model=None,  # Use base model for testing
        max_tokens=256,
    )

    backend = OfflineBackend(config)
    if not backend.load_model():
        logger.error("Failed to load model for testing")
        return

    test_messages = [
        "What is 2+2?",
        "Tell me a joke",
        "Explain quantum computing",
    ]

    logger.info("\n" + "=" * 60)
    logger.info("Testing Offline Model Inference")
    logger.info("=" * 60)

    for msg in test_messages:
        logger.info(f"\n📝 Input: {msg}")
        response = await backend.send(msg)
        logger.info(f"🤖 Response: {response}")

    backend.unload()
    logger.info("\n✅ Testing complete!")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Run test
    asyncio.run(test_inference())
