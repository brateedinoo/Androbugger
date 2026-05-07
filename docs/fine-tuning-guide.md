# Fine-Tuning Guide — Androbugger LLM

This guide covers exporting training data from Androbugger and fine-tuning a local LLM using Unsloth + LoRA, then deploying it via Ollama.

## 1. Export Training Data

From the Admin panel → Fine-Tuning tab, click **Export Training Data**, or use the CLI:

```bash
uv run androbugger export-training-data --output /tmp/androbugger-training.jsonl
```

Then validate the export:

```bash
uv run androbugger validate-training-data /tmp/androbugger-training.jsonl
```

### Data Format

Each line is a JSON object:

```json
{
  "messages": [
    {"role": "user", "content": "<deterministic_summary>"},
    {"role": "assistant", "content": "<llm_report>\n\nRoot cause: ...\n\nApplied fix: ..."}
  ]
}
```

## 2. Fine-Tune with Unsloth + LoRA

### Install Unsloth

```bash
pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
pip install --no-deps trl peft accelerate bitsandbytes
```

### Training Script

```python
from unsloth import FastLanguageModel
from trl import SFTTrainer
from transformers import TrainingArguments
from datasets import load_dataset

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="Qwen/Qwen3-14B",
    max_seq_length=4096,
    dtype=None,
    load_in_4bit=True,
)

model = FastLanguageModel.get_peft_model(
    model,
    r=16,
    target_modules=["q_proj", "v_proj", "k_proj", "o_proj",
                    "gate_proj", "up_proj", "down_proj"],
    lora_alpha=16,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
)

dataset = load_dataset("json", data_files="/tmp/androbugger-training.jsonl", split="train")

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="messages",
    max_seq_length=4096,
    args=TrainingArguments(
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        warmup_steps=10,
        max_steps=200,
        learning_rate=2e-4,
        fp16=True,
        logging_steps=10,
        output_dir="androbugger-lora",
        optim="adamw_8bit",
    ),
)
trainer.train()
```

## 3. Convert to GGUF

```bash
# Save merged model
model.save_pretrained_merged("androbugger-merged", tokenizer, save_method="merged_16bit")

# Convert with llama.cpp
python convert_hf_to_gguf.py androbugger-merged --outtype q4_k_m --outfile androbugger-q4.gguf
```

## 4. Create Ollama Modelfile

```
FROM androbugger-q4.gguf

SYSTEM """You are an expert Android IFP diagnostic assistant. You analyse bugreport data and identify root causes of crashes, ANRs, OOM kills, and thermal throttling. Be precise, structured, and actionable."""

PARAMETER num_ctx 4096
PARAMETER temperature 0.1
PARAMETER top_p 0.9
```

```bash
ollama create androbugger-v1 -f Modelfile
```

## 5. Update Androbugger to Use the New Model

In `.env`:

```
ANDROBUGGER_DEFAULT_LLM_MODEL=ollama/androbugger-v1
```

## 6. Evaluate

```bash
uv run androbugger eval-model \
  --model ollama/androbugger-v1 \
  --eval-set /tmp/eval-set.jsonl
```

ROUGE-L F-score ≥ 0.35 on the held-out eval set indicates meaningful diagnostic quality improvement over the base model.
