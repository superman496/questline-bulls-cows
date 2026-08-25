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

## 1.4.0 — GameSession and Narrative Productization

The 1.4 development line starts from the completed 1.3 engine refactor.

### Primary objective

- Introduce a shared `GameSession` state layer for Assist / 协查,
  Simulation / 推演, and Adventure / 冒险.
- Make `StoryBook` a complete case narrative rather than only a sequence of
  transition logs.
- Keep CLI as a reference client and debugging surface, not as the product
  architecture.

### Completed in this iteration

- Added `GameSession` as the shared state layer for all three modes.
- Added stable session statuses: active, logically solved, solved, and
  inconsistent.
- Routed Simulation and Adventure through the same transition pipeline used by
  Assist.
- Added structured read APIs: `current_state()`, `timeline()`, `read_story()`,
  `save()`, `resume()`, and `to_dict()`.
- Kept the 1.3 engine decision logic unchanged; this release adds orchestration
  and product state rather than score tuning.

### 1.4.x additions

- Added session replay data separating accepted transitions from rejected
  attempts.
- Added Markdown case export through `GameSession.export_markdown()`.
- Added explicit rejection handling for contradictory feedback and Adventure
  mode cheating; rejected input never contaminates the StoryBook.
- Save/resume now preserves rejected-attempt audit records.
- Expanded `current_state()` into a WebUI read model containing digits, groups,
  group relations, world-line data, chapters, suspense, and the last event.
- Added CLI `save`, `replay`, and `export` commands for case inspection and
  handoff.

### Six-slot recommendation panel hardening

- Fixed the endgame efficiency guardrail (`efficiency_frontier`) silently
  excluding every real remaining candidate from the QuestLine slots whenever a
  pure information probe scored better than testing an actual candidate.
  `resolve_endgame`'s task ranking — prefer a real candidate — is now
  respected end to end instead of being overridden downstream.
- Gave the AVG and MM slots the same `action` / `is_candidate` /
  `group_information_gain` / `evidence_profile` schema as the QuestLine and
  Conspiracy slots, instead of a partial hand-built dict.
- Fixed the endgame shortcut branch reusing the AVG guess's own
  expected/max-bucket numbers for all three QuestLine route items; each route
  now reports its own real numbers.
- Added route continuity as the tie-break before lexicographic order across
  every non-endgame task, not only the endgame shortcut.
- Rewrote the CLI's `build_menu()` to present the engine's six recommendations
  directly instead of recomputing its own, older AVG/MM/Conspiracy logic and
  silently dropping a slot whenever it repeated an earlier guess.
- Removed the dead `diversify_recommendations()` method (no remaining call
  sites after the six-slot rework).

### StoryBook audit view fixes

- Wired `render_identity_arc()` and `render_character_stories()` into the
  audit book under `## 身份认知轨迹` / `## 数字角色档案`; both methods existed
  but were never called from `render()`.
- Fixed the digit/group index sections being gated so that `render_audit()`
  could never show them.
- Fixed the readable (non-audit) book always showing the long per-round
  deliberation text instead of the short narrative line whenever a
  deliberation existed — which was every round — so the narrative text was
  effectively dead code.
- Added a group-level "伪装破裂" narrative trigger (a group going from
  `both_supported` / `symmetric` to `both_excluded`), since the existing
  single-digit 75%-support trigger rarely fires in real play.

### Text and localization consistency

- Centralized task labels, recommendation reasons, and action-type labels
  into `_QuestLineReasoningLayer.PUBLIC_TASKS` / `PUBLIC_REASONS` /
  `PUBLIC_ACTION_LABELS` (each with an English counterpart) and the
  `public_task()` / `public_reason()` / `public_action_label()` classmethods.
  The CLI previously hand-copied these dictionaries in four to six places;
  one copy had already drifted to different Chinese wording than the others,
  and the English UI mode was leaking untranslated Chinese labels in several
  places (recommendation menu action labels, `--mode` help text) or showing
  raw internal task/reason strings instead of a human-readable label.
- Fixed a garbled duplicate fragment in the Chinese feedback-example string
  and removed five dead `TEXT` dict keys that were never read by `tr()`.

### Verification

- Full regression suite: 36/36 passing (started this pass at 28/36).

### Design boundary

- Do not make WebUI depend on CLI text output.
- Do not reintroduce large score-tuning parameter layers.
- CLI and future WebUI should be adapters over `QuestLine Core → GameSession →
  StoryBook`.
