"""Output parsing and metrics for the critic eval.

Two jobs:
  1. parse_codes: turn the critic's free-form output (["CODE: quote", ...]) into
     a set of violation codes we can compare against the gold labels.
  2. confusion: a binary confusion matrix plus derived rates (precision, recall,
     F1, false-positive rate), used both draft-level and per violation type.
"""

from __future__ import annotations

import re

# Codes are UPPERCASE_WITH_UNDERSCORES at the start of each violation string
# (the critic role instructs "Use the violation codes in UPPERCASE").
_CODE_RE = re.compile(r"^[\s\-*]*([A-Z][A-Z0-9_]{2,})")


def parse_codes(raw_violations: list[str]) -> set[str]:
    codes: set[str] = set()
    for v in raw_violations:
        if not isinstance(v, str):
            continue
        m = _CODE_RE.match(v.strip())
        if m:
            codes.add(m.group(1))
    return codes


def _safe_div(n: float, d: float) -> float | None:
    return n / d if d else None


def confusion(preds: list[bool], golds: list[bool]) -> dict:
    """Binary confusion matrix + derived rates. Rates are None when undefined
    (e.g. recall is None when there are no positive gold cases to recall)."""
    tp = sum(p and g for p, g in zip(preds, golds))
    fp = sum(p and not g for p, g in zip(preds, golds))
    fn = sum((not p) and g for p, g in zip(preds, golds))
    tn = sum((not p) and (not g) for p, g in zip(preds, golds))

    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    fpr = _safe_div(fp, fp + tn)
    if precision is None or recall is None:
        f1 = None
    elif precision == 0 and recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)

    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision, "recall": recall, "f1": f1, "fpr": fpr,
    }
