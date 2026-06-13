"""Quality gates for the critic eval.

These are the pass/fail floors the eval enforces. Keep them here as explicit
constants so changing a gate is a reviewed diff, never a silent edit buried in
the runner. `run_evals.py` exits non-zero when any of these is breached, which
is what makes the harness usable as a CI check.

Positive class throughout = "the draft contains a banned pattern that SHOULD be
flagged". So recall = of the bad drafts, how many the critic caught.
"""

# ── Draft-level gates (the critic's pass/fail decision on a whole draft) ──────

# Catch rate (recall). The safety gate: a miss means a bad email ships to a
# prospect, so this is the number that matters most.
CATCH_RATE_FLOOR = 0.90

# False-positive rate: of the clean drafts, how many the critic wrongly flagged.
# Each false alarm forces a needless regeneration (wasted tokens, blander copy).
FPR_CEILING = 0.15

# Single balance number. Harmonic mean of precision and recall.
F1_FLOOR = 0.85

# ── Per-violation-type gate ──────────────────────────────────────────────────

# Each banned-pattern type is also gated on its own recall, so a strong global
# score can't hide one rule the critic enforces 0% of the time. Only enforced
# for types with enough labeled examples to be meaningful (small samples are
# too noisy to gate on) — grow the golden set to bring more types under the gate.
PER_TYPE_RECALL_FLOOR = 0.80
PER_TYPE_MIN_SUPPORT = 3
