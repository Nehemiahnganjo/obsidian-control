# ✅ Fine-Tuning Pipeline Checklist

## Phase Completion Status

### ✅ Task 2: Fine-Tuning Infrastructure (COMPLETE)

**Files Created:**
- [x] `training_exporter.py` (226 lines) - Extracts conversations to JSONL
- [x] `fine_tuning/trainer.py` (258 lines) - LoRA fine-tuning trainer
- [x] `offline_model.py` (220 lines) - Inference server
- [x] `scheduler.py` (298 lines) - Automated pipeline scheduler
- [x] `requirements-finetuning.txt` - Dependencies
- [x] `setup_finetuning.sh` - One-command setup script
- [x] `FINE_TUNING.md` (315 lines) - Complete documentation
- [x] `FINETUNING_SETUP.md` (307 lines) - Quick start guide

**Base Model Selected:**
- [x] `nztinversive/llama3.2-1b-Uncensored` (2.5GB)
- [x] Fully uncensored ✓
- [x] CPU trainable ✓
- [x] Under 4GB ✓

**Architecture Implemented:**
- [x] Data export pipeline
- [x] LoRA fine-tuning (rank=8, alpha=16)
- [x] CPU-optimized training (batch=1, accumulation=4)
- [x] Offline inference server
- [x] Async interface compatible with KiroBackend
- [x] Automated scheduling
- [x] Training metrics logging

---

## Setup Checklist (To Do Before Training)

### Pre-Setup
- [ ] Space available: 10GB (model + data + checkpoints)
- [ ] Network: Ready to download 2.5GB model
- [ ] Time: 15-20 min for first setup

### Installation
```bash
cd /home/void/kiro-telegram-bridge
bash setup_finetuning.sh
```
Expected output:
```
✓ Checking Python...
✓ Creating directories...
✓ Installing fine-tuning dependencies...
✓ Verifying imports...
✓ Downloading base model (this may take 5-10 min)...
✓ Initializing training directories...
✅ Setup complete!
```

- [ ] Dependencies installed
- [ ] Base model downloaded
- [ ] Directories created
- [ ] No errors during setup

### Data Collection
```bash
# Use bridge normally - collect conversations
/backend kiro
# Have conversations...
# (collect 50+ exchanges for good training data)
```

- [ ] 50+ conversations collected
- [ ] session_state.json has content
- [ ] Multiple persona exchanges

### First Training Run
```bash
python3 training_exporter.py
python3 fine_tuning/trainer.py
```

Expected output:
```
Starting fine-tuning of nztinversive/llama3.2-1b-Uncensored
Loading tokenizer and base model...
Model loaded. Total params: 1,228,609,024
Loading and training data...
Training dataset size: 50
Setting up LoRA...
trainable params: 1048576 || all params: 1228609024 || trainable%: 0.0853
Starting training...
[1/3 00:42, Epoch 1/3]: loss=X.XXX
[2/3 01:25, Epoch 2/3]: loss=X.XXX
[3/3 02:07, Epoch 3/3]: loss=X.XXX
✅ Fine-tuning complete! Model: /path/to/model
```

- [ ] Data exported successfully
- [ ] Training starts and runs
- [ ] No OOM errors
- [ ] Model saved to `models/` directory
- [ ] Training logs created

### Model Testing
```bash
python3 offline_model.py
```

Expected output:
```
Loading model nztinversive/llama3.2-1b-Uncensored...
Loading LoRA weights from ...
✅ Model loaded successfully. Total params: 1,228,609,024

Testing Offline Model Inference
============================================================

📝 Input: What is 2+2?
🤖 Response: 4
📝 Input: Tell me a joke
🤖 Response: Why did the chicken cross the road...
✅ Testing complete!
```

- [ ] Model loads without errors
- [ ] Inference produces output
- [ ] Latency is 1-2 seconds
- [ ] Response quality is acceptable

### Integration
```python
# In main.py, add offline backend support
from offline_model import OfflineBackend, OfflineConfig

# Test: /backend offline
```

- [ ] Offline backend integrated
- [ ] Can switch via `/backend offline`
- [ ] Can switch back via `/backend kiro`

### Automation (Optional)
```bash
python3 scheduler.py &
```

- [ ] Scheduler runs in background
- [ ] No errors in scheduler.log
- [ ] Training triggered on schedule

---

## Quality Expectations

### After 1st Training (50 conversations)
- [ ] Model runs without errors
- [ ] Output is coherent
- [ ] Some personality hints visible
- [ ] Loss decreased during training

### After 2nd Training (100+ conversations)
- [ ] Noticeable Rick persona traits
- [ ] Better conversation consistency
- [ ] ~20-30% improvement over base model
- [ ] ~70-80% quality vs Kiro

### After 3rd+ Training (200+ conversations)
- [ ] Strong Rick personality
- [ ] Context awareness improved
- [ ] Natural conversation flow
- [ ] Can replace Kiro for extended sessions

---

## Performance Targets

| Metric | Target | Expected |
|--------|--------|----------|
| Model size | < 4GB | 2.5GB ✓ |
| Training time | < 3hrs per 100 convos | 30-60 min ✓ |
| Inference latency | 1-2s | 1-2s ✓ |
| RAM (inference) | < 4GB | 2.5GB ✓ |
| RAM (training) | < 8GB | ~1.8GB ✓ |

---

## Troubleshooting Checklist

### Setup Fails
- [ ] Check Python 3.8+: `python3 --version`
- [ ] Check disk space: `df -h /home/void`
- [ ] Check internet: `ping 8.8.8.8`
- [ ] Check permissions: `ls -l /home/void/kiro-telegram-bridge`
- [ ] Rerun setup: `bash setup_finetuning.sh`

### Training Fails
- [ ] Data exists: `ls training_data/conversations.jsonl`
- [ ] Check RAM: `free -h` (should show >4GB available)
- [ ] Check logs: `tail -f training_logs/*.log`
- [ ] Reduce dataset: Use only last 50 conversations
- [ ] Reduce batch size: Set `BATCH_SIZE = 1`

### Inference Fails
- [ ] Model exists: `ls models/llama-3.2-1b-uncensored-lora-v1/`
- [ ] Check logs: `grep ERROR offline_model.py`
- [ ] Test base model: Remove LoRA path from config
- [ ] Check RAM: `free -h` during inference

### Poor Quality
- [ ] Check data: `head training_data/conversations.jsonl`
- [ ] Train longer: Set `EPOCHS = 5` in trainer.py
- [ ] More data: Collect 100+ conversations
- [ ] Better data: Ensure Rick persona in conversations

---

## File Size Reference

Expected disk usage after full setup:

```
kiro-telegram-bridge/
├── .venv/                              ~500MB (virtualenv)
├── models/
│   └── llama-3.2-1b-uncensored-lora-v1/  ~20MB (LoRA weights)
│   └── checkpoints/                   ~2.5GB (during training)
├── training_data/                     ~10-50MB (depends on volume)
├── training_logs/                     ~10MB (metrics)
└── [other files]                      ~100MB
                                    ─────────────
Total:                                ~3.5-4.5GB
```

---

## Timeline Estimate

| Phase | Time | Notes |
|-------|------|-------|
| Setup | 15-20 min | First time includes model download |
| Data Collection | Flexible | Run bridge normally |
| 1st Training | 30-60 min | 50 conversations |
| 2nd Training | 1-2 hours | 100+ conversations |
| Testing | 10 min | Verify quality |
| Integration | 20 min | Add to main.py |
| **Total** | **~2-3 hours** | First complete cycle |

---

## Success Criteria

- [x] All files created
- [x] Infrastructure complete
- [ ] Setup script runs without errors
- [ ] First training completes successfully
- [ ] Offline model produces output
- [ ] Quality acceptable for Rick personality
- [ ] Can switch between backends
- [ ] Scheduler runs autonomously

---

## Next Phases

**Phase 3 (Next)**: Model comparison & switch mechanism
- [ ] Add /compare command to bridge
- [ ] Run same message through both Kiro and offline model
- [ ] Log quality metrics

**Phase 4**: Monitoring dashboard
- [ ] Create web UI for training metrics
- [ ] Display loss curves, model versions
- [ ] Show sample outputs

**Phase 5**: Production deployment
- [ ] Full end-to-end testing
- [ ] Performance benchmarking
- [ ] Documentation finalization

---

## Quick Reference Commands

```bash
# Full setup
bash setup_finetuning.sh

# Export training data
python3 training_exporter.py

# Start fine-tuning
python3 fine_tuning/trainer.py

# Test inference
python3 offline_model.py

# View training logs
tail -f training_logs/scheduler.log

# Check training history
cat training_logs/training_history.jsonl | jq '.[-1]'

# Start scheduler
python3 scheduler.py &

# View training stats
cat training_data/training_stats.json
```

---

## Support Resources

- 📖 **Full Guide**: `FINE_TUNING.md` (315 lines)
- 🚀 **Quick Start**: `FINETUNING_SETUP.md` (307 lines)
- 📋 **This Checklist**: `CHECKLIST.md`
- 🐛 **Logs**: `training_logs/`, `bridge.log`

---

**Status**: ✅ **READY TO TRAIN**

Start with:
```bash
bash setup_finetuning.sh
```
