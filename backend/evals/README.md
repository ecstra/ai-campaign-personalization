# Critic evals

An eval harness for the email **critic** — the second LLM pass in
`core/mail/agent/critic.py` that scores every generated draft against a
banned-pattern checklist (em-dashes, filler, inference-from-fact, capability
menu dumps, ...) and triggers a regeneration when it finds a violation.

The critic is an **LLM-as-judge running in production**. This harness is the
thing that proves the judge is actually right: it runs the critic over a set of
hand-labeled drafts, across one or more models, and measures how often it
catches a real violation versus how often it false-alarms on a clean draft.

## Why the critic, and why these metrics

The critic is a classifier. Positive class = "this draft contains a banned
pattern that should be flagged." So you score it like a classifier:

| Metric | Question | Why it matters |
|---|---|---|
| **Catch rate (recall)** | of the bad drafts, how many did the critic flag? | A miss ships a bad email to a prospect. This is the safety metric. |
| **False-positive rate** | of the clean drafts, how many did it wrongly flag? | Each false alarm forces a needless regeneration: wasted tokens, blander copy. |
| **Precision** | of the drafts it flagged, how many were truly bad? | The inverse cost of over-flagging. |
| **Per-type recall** | for each banned pattern, how many instances were caught? | A strong global score can hide one rule the critic enforces poorly. |

A single blended number is deliberately avoided. The per-type table is what you
act on. Because the critic pins no temperature, each case is run several times
(`--trials`) and every `(case, trial)` is pooled into the metrics, so a flaky
check shows up as honestly-lower recall instead of a single noisy data point.

## Results — 29 cases × 5 trials

Both models pass the gate. These numbers are *after* the deterministic pre-pass
fix described below.

### Headline (draft-level)

| Model | Catch rate | Precision | FPR | F1 |
|---|---|---|---|---|
| `deepseek-v4-pro` | **100%** | 100% | 0% | **100%** |
| `deepseek-v4-flash` | 98.0% | 100% | 0% | 99.0% |

### Per-violation-type recall

| Violation type | `deepseek-v4-pro` | `deepseek-v4-flash` |
|---|---|---|
| BARE_FILLER_ADJECTIVE | 100% | 90% |
| CAPABILITY_MENU_DUMP | 100% | 100% |
| CORPORATE_FILLER | 100% | 100% |
| EM_DASH | 100% | 100% |
| FILLER_PHRASE_PATTERN | 100% | 100% |
| INFERENCE_FROM_FACT | 100% | 100% |
| NAME_FORMALITY_MISMATCH | 100% | 100% |

`deepseek-v4-pro` catches every planted violation with no false positives.
`deepseek-v4-flash` now matches it on every check except a small wobble on
`BARE_FILLER_ADJECTIVE` (90% recall — one borderline "custom/unique" draft it
flags on 3 of 5 runs), still above the 0.80 gate floor. Both models occasionally
over-apply `CORPORATE_FILLER`/`INFERENCE_FROM_FACT` as an extra tag on a draft
that already fails for another reason (precision ~93–95%), which costs nothing
because that draft was being regenerated anyway.

### The fix: a deterministic regex pre-pass

The first run exposed that `deepseek-v4-flash` was unreliable on the two most
trivially detectable checks, while `pro` was already perfect:

| Check | flash, before | flash, after |
|---|---|---|
| EM_DASH | 73.3% | **100%** |
| NAME_FORMALITY_MISMATCH | 65.0% | **100%** |

`EM_DASH` and `NAME_FORMALITY_MISMATCH` are rule-expressible, so they no longer
hinge on the model's judgment: `critic.py` now runs a regex pre-pass (`—`
membership and `\bDear\s+[A-Z]`) and merges those findings with the LLM's output,
which still owns the fuzzy checks. Both are caught 100% of the time on either
model now, and `flash` went from **failing** the gate to passing it. The eval is
what caught the blind spot and what verified the fix.

## Running it

From the `backend/` directory (needs `backend/.env` with `LLM_SOURCE`,
`LLM_API_KEY`, `LLM_MODEL` — the same vars the app uses):

```bash
python evals/run_evals.py                                          # env LLM_MODEL, 1 trial
python evals/run_evals.py --model deepseek-v4-flash,deepseek-v4-pro --trials 5
python evals/run_evals.py --subset 8 --concurrency 8               # cheaper smoke run
python evals/run_evals.py --no-gate                                # report only, exit 0
```

`--model` overrides which model id(s) to score (comma-separated runs a
comparison). `--trials N` runs each case N times and pools the results. The
script **exits non-zero** when any gate in `thresholds.py` is breached for any
model, so it drops straight into CI as a required check. Each run also writes a
machine-readable `results/<ts>.json` and a markdown `results/summary.md`.

## CI

`.github/workflows/critic-evals.yml` runs the harness on every PR that touches
`backend/core/mail/**` or `backend/evals/**`. Set the repo secret `LLM_API_KEY`
(Settings → Secrets → Actions) and it gates merges; the summary is uploaded as a
build artifact.

## How it works

```
load golden/critic.jsonl            # hand-labeled drafts + their true violations
  → for each model, for each trial: call CriticUtility.critique_email(...)
  → parse the critic's "CODE: quote" output into a set of violation codes
  → compare to the gold labels: confusion matrix, draft-level + per type
  → write results JSON + summary.md
  → gate: exit non-zero if any floor in thresholds.py is breached
```

The runner swaps the critic module's `LLM_MODEL` global per model, so it
evaluates the *real* production critic unchanged — no fork, no mock.

## Files

```
evals/
  golden/critic.jsonl   # the spec: {id, subject, body, recipient_context, gold_violations:[...]}
  graders.py            # parse critic output into codes; confusion matrix
  thresholds.py         # the pass/fail gates (edit in a reviewed diff)
  run_evals.py          # load → run critic (multi-model, multi-trial) → score → report → gate
  results/              # per-run JSON + latest.json + summary.md (gitignored)
  README.md
```

## Growing the golden set (this is the ongoing work)

The committed `critic.jsonl` is 29 realistic cases across five product/persona
scenarios, covering every violation type (each with ≥3 examples so it is gated),
plus hard negatives — a hyphen and en-dash that are *not* em-dashes, and an
"exact"/"precise" that *is* qualified by a real number. Every label was
independently audited against the checklist before committing.

To make it production-representative:

1. Export real drafts from the `emails` table (subject + body) with the lead's
   `recipient_context`.
2. Hand-label the true violations in each (read `critic_role.md` for the codes).
3. Append them as JSONL lines. Every production miss the critic lets through
   becomes a new line here — that is how the set stays honest over time.
