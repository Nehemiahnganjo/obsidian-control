#!/bin/bash
# Setup script for fine-tuning pipeline

set -e

BRIDGE_DIR="/home/void/kiro-telegram-bridge"
PYTHON="python3"

echo "🚀 Setting up Llama-3.2-1B fine-tuning pipeline..."
echo

# 1. Check Python
echo "✓ Checking Python..."
$PYTHON --version

# 2. Create directories
echo "✓ Creating directories..."
mkdir -p "$BRIDGE_DIR/models"
mkdir -p "$BRIDGE_DIR/training_data"
mkdir -p "$BRIDGE_DIR/training_logs"
mkdir -p "$BRIDGE_DIR/fine_tuning"

# 3. Install dependencies
echo "✓ Installing fine-tuning dependencies..."
cd "$BRIDGE_DIR"
$PYTHON -m pip install -q -r requirements-finetuning.txt

# 4. Verify imports
echo "✓ Verifying imports..."
$PYTHON -c "
import torch
import transformers
import peft
import datasets
print('  torch:', torch.__version__)
print('  transformers:', transformers.__version__)
print('  peft:', peft.__version__)
print('  datasets:', datasets.__version__)
"

# 5. Download base model
echo "✓ Downloading base model (this may take 5-10 min)..."
$PYTHON -c "
from transformers import AutoTokenizer, AutoModelForCausalLM
print('  Downloading tokenizer...')
AutoTokenizer.from_pretrained('nztinversive/llama3.2-1b-Uncensored')
print('  Downloading model (2.5GB, first time only)...')
AutoModelForCausalLM.from_pretrained('nztinversive/llama3.2-1b-Uncensored', torch_dtype='auto', device_map='auto')
print('  ✅ Base model cached locally')
"

# 6. Create training directory structure
echo "✓ Initializing training directories..."
touch "$BRIDGE_DIR/training_data/.gitkeep"
touch "$BRIDGE_DIR/training_logs/.gitkeep"

echo
echo "✅ Setup complete!"
echo
echo "Next steps:"
echo "  1. Export training data: python3 training_exporter.py"
echo "  2. Start fine-tuning: python3 fine_tuning/trainer.py"
echo "  3. Test model: python3 offline_model.py"
echo
echo "See FINE_TUNING.md for detailed documentation"
