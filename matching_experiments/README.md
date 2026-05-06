# Matching Experiments

Evaluates how well different LLMs match vulnerability findings to ground-truth entries, compared against human annotations.

## Overview

A fixed set of **50 findings** (25 human-confirmed True Positives + 25 human-confirmed False Positives) is matched against ground-truth vulnerabilities using various LLMs. The pipeline:

1. **Pairwise LLM comparison** — each finding is compared against every ground-truth entry (same target) using an LLM with structured output (YES/NO).
2. **Bipartite matching** — the Hungarian algorithm resolves many-to-many raw matches into optimal 1-to-1 assignments per target.
3. **TP/FP counting** — matched findings = True Positives; unmatched findings = False Positives.

Results are compared to the human annotation baseline (25 TP / 25 FP by construction).

## Usage

```bash
cd ethibench
source .venv/bin/activate

# Run with default 3 replicates
python matching_experiments/run_experiment.py --models haiku-4.5

# Run multiple models at once
python matching_experiments/run_experiment.py --models haiku-4.5 gpt-5.4-mini deepseek-3.1 qwen-3.6-plus

# Custom number of replicates
python matching_experiments/run_experiment.py --models haiku-4.5 --replicates 5

# Add more replicates later (accumulates with previous runs)
python matching_experiments/run_experiment.py --models haiku-4.5 --replicates 2
```

## Available Models

| Key | Model | Provider |
|-----|-------|----------|
| `haiku-4.5` | claude-haiku-4-5 | Anthropic |
| `gpt-5.4-mini` | gpt-5.4-mini | OpenAI |
| `deepseek-3.1` | accounts/fireworks/models/deepseek-v3p1 | Fireworks |
| `qwen-3.6-plus` | accounts/fireworks/models/qwen3p6-plus | Fireworks |

## Environment Variables

| Variable | Required for |
|----------|-------------|
| `ANTHROPIC_API_KEY` | haiku-4.5 |
| `OPENAI_API_KEY` | gpt-5.4-mini |
| `FIREWORKS_API_KEY` | deepseek-3.1, qwen-3.6-plus |
| `LANGCHAIN_API_KEY` | LangSmith tracing |

LangSmith tracing is enabled by default (project: `matching-experiments`). Set `LANGCHAIN_TRACING_V2=false` to disable.

## Output

- `results/<model-key>.json` — per-model results with all replicates and summary (mean/std)
- `results/comparison.png` — grouped bar chart comparing all models against the human baseline

## Replicates

Due to the probabilistic nature of LLMs, each model is run multiple times (default: 3). Results **accumulate** across runs — if you run 1 replicate today and 2 more tomorrow, the JSON and plots will reflect all 3 replicates combined.

The comparison plot shows mean ± std error bars for each model.

## Files

| File | Description |
|------|-------------|
| `run_experiment.py` | Main experiment script |
| `selected_findings.json` | Fixed set of 50 finding UUIDs (25 TP + 25 FP) |
| `annotations.json` | Human annotations (input, read-only) |
| `findings.jsonl` | All vulnerability findings with UUIDs (input, read-only) |
| `_generate_selection.py` | One-time script used to generate `selected_findings.json` |

## Finding Selection Criteria

The 50 findings in `selected_findings.json` were selected deterministically (seed=42):

- **25 TPs**: findings annotated with exactly 1 ground-truth match, not marked as false positive or duplicate, with no two TPs sharing the same ground-truth entry.
- **25 FPs**: findings annotated as false positive with no ground-truth matches, not marked as duplicate.
