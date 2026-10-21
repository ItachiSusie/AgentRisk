# Data

Official data: <https://huggingface.co/datasets/AgentRisk/agentrisk-data-2027>

| File | Rows | Use |
| --- | --- | --- |
| `raw/train.jsonl` | 568 | few-shot examples only |
| `raw/dev.jsonl` | 143 | full evaluation |

`raw/` is not committed. Download it with `python src/download_data.py`, which
also writes `MANIFEST.json` (HF commit SHA, download time, file SHA-256, row
counts, example IDs). Everyone should work from the revision in `MANIFEST.json`.

## Fields

- Model input: `formatted_interaction`, `proposed_action`. `example_id` is kept by the program to match results.
- Gold, offline evaluation only, never put in a prompt: `risk_severity`, `risk_domains`, `risk_drivers`.

Task 3 (policy-guided intervention) has no public policy or gold labels yet.
