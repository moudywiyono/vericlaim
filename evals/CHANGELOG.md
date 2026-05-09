# Eval Changelog

Record every change that affects metrics: what changed, when, what moved, and the decision.
Format: `## YYYY-MM-DD | <change> | <metric delta> | <decision>`

---

## 2026-05-09 | Initial eval harness scaffold | baseline | ship

Skeleton only — no metrics yet. Component suite runners, perturbation pipeline, and metric
stubs are in place. All metrics raise `NotImplementedError` pending specialist implementation.

Gold set gate active: `E2ESuite` requires `VERICLAIM_ALLOW_GOLD_EVAL=1` to run.
