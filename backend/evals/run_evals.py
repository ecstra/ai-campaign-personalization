#!/usr/bin/env python
"""Eval harness for the Outreach email critic.

Treats `CriticUtility.critique_email` as a CLASSIFIER and scores it against a
hand-labeled golden set, across one or more models:

  - catch rate (recall): of drafts that truly contain a banned pattern, how many
    the critic flagged. A miss means a bad email ships, so this is the safety
    metric.
  - false-positive rate: of clean drafts, how many the critic wrongly flagged.
    Each false alarm forces a needless regeneration.
  - per-violation-type recall/precision, so one weak rule can't hide behind a
    strong global score.

The critic pins no temperature, so its output wobbles run to run. Use --trials
to run each case several times: every (case, trial) is pooled into the metrics,
so a flaky check shows up as honestly-lower recall rather than a single noisy
number, and per-case hit rate (e.g. "caught 2/3") flags exactly which drafts
are unstable.

Usage (from backend/)
---------------------
  python evals/run_evals.py                                   # env LLM_MODEL, 1 trial
  python evals/run_evals.py --model deepseek-v4-flash,deepseek-v4-pro --trials 3
  python evals/run_evals.py --subset 8 --concurrency 8
  python evals/run_evals.py --no-gate                         # report only, exit 0

Needs backend/.env with LLM_SOURCE / LLM_API_KEY / LLM_MODEL (the same vars the
app uses). --model overrides which model id(s) to evaluate. Exit code is
non-zero when any gate in thresholds.py is breached for any model, so this drops
straight into CI as a required check.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import graders
import thresholds

EVALS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = EVALS_DIR.parent
GOLDEN_PATH = EVALS_DIR / "golden" / "critic.jsonl"
RESULTS_DIR = EVALS_DIR / "results"


# ── Loading ──────────────────────────────────────────────────────────────────

def load_cases(path: Path, subset: int | None) -> list[dict]:
    cases: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases[:subset] if subset else cases


# ── Running the critic ───────────────────────────────────────────────────────

def setup_critic():
    """Load env BEFORE importing the critic (provider.py reads LLM_* at import
    time), then return the critic module so its LLM_MODEL global can be swapped
    per model without touching the production code."""
    from dotenv import load_dotenv
    load_dotenv(BACKEND_DIR / ".env")
    sys.path.insert(0, str(BACKEND_DIR))
    import core.mail.agent.critic as critic_mod
    return critic_mod


async def predict_trials(critic_mod, model: str, cases: list[dict],
                         concurrency: int, trials: int) -> list[list[list[str]]]:
    critic_mod.LLM_MODEL = model  # override the module global for this model
    sem = asyncio.Semaphore(concurrency)

    async def one(case: dict) -> list[str]:
        async with sem:
            result = await critic_mod.CriticUtility.critique_email(
                subject=case["subject"],
                body=case["body"],
                recipient_context=case.get("recipient_context", ""),
            )
            return list(result.violations)

    trials_raw: list[list[list[str]]] = []
    for _ in range(trials):
        trials_raw.append(await asyncio.gather(*(one(c) for c in cases)))
    return trials_raw


# ── Scoring ──────────────────────────────────────────────────────────────────

def score(cases: list[dict], trials_raw: list[list[list[str]]]) -> dict:
    n_trials = len(trials_raw)
    parsed = [[graders.parse_codes(trials_raw[t][ci]) for ci in range(len(cases))]
              for t in range(n_trials)]

    code_universe: set[str] = set()
    for c in cases:
        code_universe |= set(c["gold_violations"])
    for t in range(n_trials):
        for ci in range(len(cases)):
            code_universe |= parsed[t][ci]
    code_universe.discard("CRITIC_ERROR")

    draft_preds, draft_golds = [], []
    n_errors = 0
    per_case = {c["id"]: {"gold": sorted(set(c["gold_violations"])), "correct": 0, "trials": []}
                for c in cases}

    for t in range(n_trials):
        for ci, c in enumerate(cases):
            pred = parsed[t][ci]
            if "CRITIC_ERROR" in pred:
                n_errors += 1
            pred_pos = bool(pred - {"CRITIC_ERROR"})
            gold_pos = bool(set(c["gold_violations"]))
            draft_preds.append(pred_pos)
            draft_golds.append(gold_pos)
            pc = per_case[c["id"]]
            pc["trials"].append(sorted(pred - {"CRITIC_ERROR"}))
            if pred_pos == gold_pos:
                pc["correct"] += 1

    draft = graders.confusion(draft_preds, draft_golds)

    per_type: dict[str, dict] = {}
    for code in sorted(code_universe):
        preds, golds = [], []
        for t in range(n_trials):
            for ci, c in enumerate(cases):
                preds.append(code in parsed[t][ci])
                golds.append(code in set(c["gold_violations"]))
        m = graders.confusion(preds, golds)
        m["support"] = sum(golds)
        per_type[code] = m

    for pc in per_case.values():
        pc["hit_rate"] = pc["correct"] / n_trials

    return {"draft": draft, "per_type": per_type, "per_case": per_case,
            "n_trials": n_trials, "n_cases": len(cases), "n_errors": n_errors}


# ── Gating ───────────────────────────────────────────────────────────────────

def gate(res: dict) -> list[str]:
    failures: list[str] = []
    draft, per_type = res["draft"], res["per_type"]

    if res["n_errors"]:
        failures.append(f"CRITIC_ERROR on {res['n_errors']} call(s)")
    if draft["recall"] is not None and draft["recall"] < thresholds.CATCH_RATE_FLOOR:
        failures.append(f"catch_rate {draft['recall']:.2f} < {thresholds.CATCH_RATE_FLOOR}")
    if draft["f1"] is not None and draft["f1"] < thresholds.F1_FLOOR:
        failures.append(f"f1 {draft['f1']:.2f} < {thresholds.F1_FLOOR}")
    if draft["fpr"] is not None and draft["fpr"] > thresholds.FPR_CEILING:
        failures.append(f"fpr {draft['fpr']:.2f} > {thresholds.FPR_CEILING}")
    for code, m in per_type.items():
        if (m["support"] >= thresholds.PER_TYPE_MIN_SUPPORT
                and m["recall"] is not None
                and m["recall"] < thresholds.PER_TYPE_RECALL_FLOOR):
            failures.append(
                f"{code} recall {m['recall']:.2f} < {thresholds.PER_TYPE_RECALL_FLOOR}")
    return failures


# ── Reporting ────────────────────────────────────────────────────────────────

def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def print_model_report(model: str, res: dict) -> None:
    draft = res["draft"]
    print()
    print("=" * 64)
    print(f" {model}   ({res['n_cases']} cases x {res['n_trials']} trial(s))")
    print("=" * 64)
    print(" Draft-level (correct pass/fail decision on the whole draft)")
    print(f"   catch rate (recall) : {_pct(draft['recall']):>7}   (tp={draft['tp']}, fn={draft['fn']})")
    print(f"   precision           : {_pct(draft['precision']):>7}")
    print(f"   false-positive rate : {_pct(draft['fpr']):>7}   (fp={draft['fp']}, tn={draft['tn']})")
    print(f"   f1                  : {_pct(draft['f1']):>7}")

    print("\n Per violation type")
    print(f"   {'CODE':<26}{'recall':>8}{'prec':>8}{'support':>9}")
    for code, m in res["per_type"].items():
        print(f"   {code:<26}{_pct(m['recall']):>8}{_pct(m['precision']):>8}{m['support']:>9}")

    flaky = {cid: pc for cid, pc in res["per_case"].items()
             if 0 < pc["hit_rate"] < 1}
    wrong = {cid: pc for cid, pc in res["per_case"].items()
             if pc["hit_rate"] == 0}
    if wrong:
        print(f"\n Always wrong ({len(wrong)}): " + ", ".join(wrong))
    if flaky:
        print(f" Flaky across trials ({len(flaky)}): "
              + ", ".join(f"{cid} {pc['correct']}/{res['n_trials']}" for cid, pc in flaky.items()))


def comparison_markdown(all_res: dict[str, dict]) -> str:
    models = list(all_res)
    lines = ["## Headline (draft-level)", "",
             "| Model | Catch rate | Precision | FPR | F1 |",
             "|---|---|---|---|---|"]
    for m in models:
        d = all_res[m]["draft"]
        lines.append(f"| `{m}` | {_pct(d['recall'])} | {_pct(d['precision'])} | "
                     f"{_pct(d['fpr'])} | {_pct(d['f1'])} |")

    codes = sorted({c for r in all_res.values() for c in r["per_type"]})
    lines += ["", "## Per-violation-type recall", "",
              "| Violation type | " + " | ".join(f"`{m}`" for m in models) + " |",
              "|---" * (len(models) + 1) + "|"]
    for code in codes:
        cells = [_pct(all_res[m]["per_type"].get(code, {}).get("recall")) for m in models]
        lines.append(f"| {code} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def write_results(all_res: dict[str, dict]) -> tuple[Path, Path]:
    RESULTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {"timestamp": ts, "models": all_res}
    out = RESULTS_DIR / f"{ts}.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (RESULTS_DIR / "latest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md = f"# Critic eval — {ts}\n\n" + comparison_markdown(all_res)
    md_path = RESULTS_DIR / "summary.md"
    md_path.write_text(md, encoding="utf-8")
    return out, md_path


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=None,
                    help="comma-separated model id(s) to evaluate (default: env LLM_MODEL)")
    ap.add_argument("--trials", type=int, default=1, help="runs per case (pooled into metrics)")
    ap.add_argument("--subset", type=int, default=None, help="run only the first N cases")
    ap.add_argument("--concurrency", type=int, default=6, help="parallel critic calls")
    ap.add_argument("--no-gate", action="store_true", help="report only, always exit 0")
    args = ap.parse_args()

    cases = load_cases(GOLDEN_PATH, args.subset)
    if not cases:
        print(f"No cases found in {GOLDEN_PATH}", file=sys.stderr)
        sys.exit(2)

    critic_mod = setup_critic()
    models = ([m.strip() for m in args.model.split(",") if m.strip()]
              if args.model else [os.getenv("LLM_MODEL", "unknown")])

    all_res: dict[str, dict] = {}
    for model in models:
        trials_raw = asyncio.run(predict_trials(critic_mod, model, cases, args.concurrency, args.trials))
        all_res[model] = score(cases, trials_raw)
        print_model_report(model, all_res[model])

    out, md_path = write_results(all_res)
    print(f"\nWrote {out.relative_to(BACKEND_DIR)} and {md_path.relative_to(BACKEND_DIR)}")

    any_fail = False
    print()
    for model in models:
        failures = gate(all_res[model])
        if failures:
            any_fail = True
            print(f"GATE {model}: FAIL")
            for f in failures:
                print(f"  - {f}")
        else:
            print(f"GATE {model}: PASS")

    if any_fail and not args.no_gate:
        sys.exit(1)


if __name__ == "__main__":
    main()
