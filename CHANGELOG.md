# Changelog

## 1.3.0 — Narrative Engine Refactor

QuestLine 1.3 is an engine refactor, not a parameter-tuning release.

### Engine architecture

- Replaced round-driven phase heuristics with fact-driven investigation tasks.
- Added `investigation_state()` as the factual state layer for candidate space,
  digit identity, digit positions, group relations, conflicts, and task state.
- Added structural action classification and task eligibility before efficiency
  ranking, so the current investigation objective has priority over a raw score.
- Moved feasibility safeguards into `task_policy()` and explicit task states:
  `ready`, `task_relaxable`, `task_infeasible`, and `state_inconsistent`.
- Removed the legacy scoring patch layer: phase weights, guards, trigger
  bonuses, semi-brakes, fallback scoring, and legacy guess/play paths.
- Repeated guesses are structurally rejected; endgames prefer direct candidate
  verification instead of mechanical splitting.

### Explainability and story

- Added transition explanations with the contract:
  `state 1 → action → feedback → facts → world-line change → state 2`.
- Added position evidence alongside digit identity evidence.
- Added `StoryBook`, chapter transitions, digit indexes, group indexes, and
  readable case-book rendering.
- Added the narrative modes:
  - Assist / 协查：the user acts, QuestLine interprets.
  - Simulation / 推演：the user supplies the answer, QuestLine acts.
  - Adventure / 冒险：QuestLine supplies the answer, the user acts.

### CLI

- Added `assist`, `simulation`, and `adventure` mode entry points.
- Kept `solver`, `explore`, and `story` as compatibility aliases.
- Added `story` / `book` commands for reading the current case book.

### Verification

- 22 engine and StoryBook regression tests pass.
- 500-answer behavior benchmark: average `4.7580` steps, maximum `6`.
- The benchmark is observability-only and does not retune recommendation scores.
