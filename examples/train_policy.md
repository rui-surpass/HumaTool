# Train VLA Policy

This repository does not include raw demonstrations or model weights. After preparing an approved local dataset, convert it to the expected JSONL sample format:

```bash
python src/data_processing/convert_demo_format.py \
  --input-dir data/raw \
  --output data/processed/train_samples.jsonl \
  --window-size 16 \
  --stride 4
```

Then run the public-safe fine-tuning scaffold:

```bash
python src/vla_finetuning/finetune_lora.py --config configs/train_lora.yaml
```

Replace the scaffold with the actual GR00T / VLA training commands in your authorized environment.
