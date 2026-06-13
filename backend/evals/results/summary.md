# Critic eval — 20260613T070737Z

## Headline (draft-level)

| Model | Catch rate | Precision | FPR | F1 |
|---|---|---|---|---|
| `deepseek-v4-flash` | 98.0% | 100.0% | 0.0% | 99.0% |
| `deepseek-v4-pro` | 100.0% | 100.0% | 0.0% | 100.0% |

## Per-violation-type recall

| Violation type | `deepseek-v4-flash` | `deepseek-v4-pro` |
|---|---|---|
| BARE_FILLER_ADJECTIVE | 90.0% | 100.0% |
| CAPABILITY_MENU_DUMP | 100.0% | 100.0% |
| CORPORATE_FILLER | 100.0% | 100.0% |
| EM_DASH | 100.0% | 100.0% |
| FILLER_PHRASE_PATTERN | 100.0% | 100.0% |
| INFERENCE_FROM_FACT | 100.0% | 100.0% |
| NAME_FORMALITY_MISMATCH | 100.0% | 100.0% |
