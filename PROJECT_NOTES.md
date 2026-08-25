# QuestLine Project Notes

> Project handoff and development notes for QuestLine.
>
> Current stable milestone: **v1.4.0 – GameSession, Narrative Productization, and Six-Slot Recommendation Hardening**
>
> Next milestone: **v1.5 – WebUI adapter**

## 0. Current Development Baseline

The repository now includes the completed 1.4 session layer on top of the 1.3
engine, plus a hardening pass on the recommendation panel and the StoryBook
audit view. See `CHANGELOG.md` for the itemized record of what shipped in
each version — this file only tracks where the project stands and what is
still open.

The conceptual explanation of the engine and story pipeline lives in
`ARCHITECTURE.md`. Read it before changing the investigation model, the
six-slot recommendation contract, or adding a new presentation adapter.

**Before trusting a "tests pass" claim, run them yourself.** Most tests in
`tests/test_solver.py` construct `QuestLineSolver(use_cache=False)`, which
rebuilds the full 5040×5040 feedback matrix from scratch — if `pytest` isn't
on hand, a plain script that imports `test_solver` and calls every `test_*`
function can take over a minute per test and looks like it hung. It hasn't;
monkey-patching `_build_feedback_matrix` to memoize once per process (not
touching the on-disk cache) brings a full 36-test run down to ~70s. This cost
a fair amount of time to discover this pass — don't rediscover it.

### v1.4 development order

1. Define the shared `GameSession` contract. ✅
2. Route Assist, Simulation, and Adventure through it. ✅
3. Upgrade `StoryBook` from event log to case narrative. ✅
4. Expose structured read APIs for future WebUI adapters. ✅
5. Add replay, save/resume, export, and fault scenarios. ✅
6. Keep CLI as the reference/debug client. ✅
7. Harden the six-slot recommendation panel and the StoryBook audit view. ✅

The intended architecture is:

```text
QuestLine Core Engine
        ↓
GameSession / StoryBook
        ↓
CLI Adapter       WebUI Adapter (future)
```

WebUI must consume structured session and story data directly; it must not
parse CLI text output.

---

## 1. Project Identity

**QuestLine** is a narrative-driven Bulls & Cows solver.

Core idea:

> Follow the strongest story. Distrust coincidence.
>
> 沿着最可信的世界线逼近真相，不轻信巧合。

QuestLine is not intended to be only a cold solver that prints the next guess. The goal is to make the reasoning process visible:

- What is the remaining possible answer count?
- Is the current line ahead, normal, slow, or difficult?
- Which strategy state is active?
- Which recommendation comes from QuestLine, AVG, MM, or Conspiracy?
- When does the game become logically solved?
- If the player keeps probing after logical solve, how is that recorded?
- Which world-line is currently strongest, and why?

---

## 2. Current Stable Version

Current stable milestone:

```text
v1.4.0
```

Current CLI file:

```text
questline_cli.py
```

The CLI file dropped its `_v1_3_standalone` suffix in 1.4: the version lived
in the filename for a while, which meant the name went stale every time the
engine moved on. The file is now named for what it is, not the release it was
written in; version history belongs in `CHANGELOG.md`.

Recommended run commands:

```bash
python questline_cli.py --lang zh
python questline_cli.py --lang en
```

No git tag has been cut for 1.4.0 yet — see [§8](#8-git--version-state).

---

## 3. Main Files

Core files:

```text
questline.py               # Core solver engine, GameSession, StoryBook
questline_cli.py           # Narrative CLI: Assist / Simulation / Adventure
benchmark_full.py          # Full 5040-answer benchmark
benchmark_worldline.py     # World-line observability benchmark
README.md                  # Public project documentation
ARCHITECTURE.md            # Engine design and decision chain
CHANGELOG.md               # Version history
CONTRIBUTING.md            # Contribution notes
.gitignore                 # Ignore cache, replay, benchmark output, __pycache__
```

Current local/generated files that should generally not be committed:

```text
.questline_cache/
questline_replay_*.json
benchmark_full_results.json
benchmark_worldline_results.json
benchmark_sample_*_results.json
__pycache__/
```

These are ignored by `.gitignore`.

---

## 4. Feature Summary

See `README.md` → "Features" for the current, user-facing feature list. This
file does not keep a second copy — two lists drift the same way two label
dictionaries used to (see `CHANGELOG.md`'s 1.4.x notes on that). Sections 5-7
below cover the implementation details README intentionally leaves out
(exact input grammar, replay JSON field semantics, logical-solve bookkeeping).

---

## 5. Input Grammar

Commands are recognized first:

```text
q / quit / exit
undo / back
history / h
report / r
new / restart
help / ?
```

For non-command input, **any non-digit character is treated as a separator**.

合法输入只有三类：

### 5.1 Two digits: feedback for default #1

Examples:

```text
40
4:0
4x0
4。0
(4,0)
```

Meaning:

```text
Use recommendation #1 and record 4b0c.
```

### 5.2 Three digits: menu index + feedback

Examples:

```text
411
4:11
4x1y1
```

Meaning:

```text
Use recommendation #4 and record 1b1c.
```

### 5.3 Six digits: manual guess + feedback

Examples:

```text
932840
9328 40
9328x4y0
9328:40
```

Meaning:

```text
Manually guess 9328 and record 4b0c.
```

### 5.4 Feedback validation

Feedback must satisfy:

```text
0 <= bull <= 4
0 <= cow <= 4
bull + cow <= 4
```

Invalid examples:

```text
05
23
44
50
```

### 5.5 Guess validation

Manual guesses must satisfy:

```text
4 digits
all digits distinct
leading zero allowed
```

Invalid examples:

```text
0000
2222
1123
```

### 5.6 Ambiguous grouped six-digit input

Allowed:

```text
932840
9328 40
9328 4 0
```

Rejected:

```text
123,40,1
12,34,01
1,234,01
```

Even if the total number of digits is six, ambiguous grouping should not be accepted.

---

## 6. Replay JSON Semantics

Replay JSON records the final effective route, not the full UI operation log.

### 6.1 Undo behavior

`undo` removes the last effective row from both in-memory history and replay rows.

Therefore, undone moves are **not saved** in replay JSON.

```text
Replay JSON = final effective reasoning route
not full operation event log
```

### 6.2 Correction behavior

If a feedback is corrected through recovery mode, the row remains in replay JSON and gets:

```json
"corrected": true
```

The row's `feedback`, `parsed_as`, and `remaining_after` are updated.

### 6.3 Replay top-level fields

Typical replay fields:

```json
{
  "project": "QuestLine",
  "saved_at": "...",
  "ui_language": "zh",
  "solved": true,
  "jackpot": false,
  "final_answer": "5019",
  "rounds": 8,
  "logical_answer": "5019",
  "logical_solved_at_round": 5,
  "verified_at_round": 8,
  "verification_delay_rounds": 3,
  "post_logic_probe_count": 2,
  "history": []
}
```

### 6.4 Replay row fields

Typical row fields:

```json
{
  "round": 3,
  "guess": "6251",
  "feedback": "0b2c",
  "source": "QuestLine",
  "input_mode": "default",
  "matched_menu_rank": 1,
  "parsed_as": "已解析：默认 #1 6251 -> 0b2c（QuestLine）",
  "corrected": false,
  "post_logic_probe": false,
  "remaining_after": 44
}
```

### 6.5 Source vs input_mode

`source` means where the guess belongs in the recommendation system.

`input_mode` means how the user entered it.

Example:

```text
User enters: 873440
Current menu #2 is 8734 [Conspiracy]
```

Replay should record:

```json
"source": "Conspiracy",
"input_mode": "manual",
"matched_menu_rank": 2
```

This means:

```text
The user manually typed the guess, but the guess matched a Conspiracy recommendation.
```

---

## 7. Logical Solved and Post-Logic Probing

QuestLine distinguishes two states:

```text
logical solved = remaining possible answer count is 1
verified solved = user enters 4b0c for the final answer
```

When only one answer remains, CLI displays:

```text
逻辑已破案：唯一可能答案是 XXXX。输入 40 可确认解决，也可以继续手动验证。
```

Post-logic probing is allowed if the additional feedback remains consistent with the unique answer.

Rows after logical solve and before final confirmation are marked:

```json
"post_logic_probe": true
```

Replay top-level fields:

```json
"logical_answer": "5019",
"logical_solved_at_round": 5,
"verified_at_round": 8,
"verification_delay_rounds": 3,
"post_logic_probe_count": 2
```

Definitions:

```text
verification_delay_rounds = verified_at_round - logical_solved_at_round
post_logic_probe_count = number of rows with post_logic_probe == true
```

---

## 8. Git / Version State

The last cut tag was the pre-1.3 stable interaction layer:

```text
v1.2.0
```

```bash
git tag -a v1.2.0 -m "QuestLine CLI v1.2 stable"
git push origin v1.2.0
```

1.3.0 and 1.4.0 are recorded in `CHANGELOG.md` but have not been tagged in
git yet. Cutting a `v1.4.0` tag (and a GitHub Release) once this repository is
under version control again is the natural next housekeeping step.

---

## 9. Benchmark Status

The full exhaustive 5040-answer run is slow enough (each answer plays several
full-space scoring rounds) that it is not re-run for every change. The last
numbers quoted in this project (pre-1.3 engine, full 5040 answers) were:

```text
average_steps: 5.2966
max_steps: 7
8+ steps: 0
```

1.3's own verification instead sampled 500 answers post-refactor and got
`average 4.7580, max 6` (see `CHANGELOG.md`). After the 1.4 recommendation-panel
fixes in this pass, a fresh 300-answer sample got:

```text
average_steps: 4.60
max_steps: 7
8+ steps: 0
```

(`python benchmark_full.py --limit 300`; the raw JSON output is gitignored
and was deleted after these numbers were recorded here — regenerate it with
the same command if you need the per-answer detail.) A full 5040-answer
re-run was attempted during this pass but did not finish; the full-space
numbers above are still the pre-1.3 ones. Re-run `benchmark_full.py` (no
`--limit`) for a definitive current number — expect it to take on the order
of 30+ minutes. See `benchmark_worldline_report.md` (generated by
`benchmark_worldline.py`) for the current world-line observability output;
its own raw JSON output is likewise gitignored and disposable.

---

## 10. Historical planning notes

Sections that used to live here — the pre-1.3 world-line analysis plan and
the "strategy expectations to revisit" notes — described work that has since
shipped. `CHANGELOG.md`'s 1.3.0 and 1.4.0 entries are the authoritative record
of what was actually built; this file no longer duplicates that plan.

---

## 11. Project Philosophy Notes

QuestLine should remain playable and explainable.

Important project personality:

```text
QuestLine does not force the player to follow the main story.
It allows alternate timelines.
It records whether the player followed QuestLine, AVG, MM, Conspiracy, or Manual input.
It can tell when the truth is already logically known, but still allows the player to keep probing.
```

Key phrases:

```text
Follow the strongest story.
Distrust coincidence.
Conspiracy Pick.
Alternate timeline.
平行世界线直接成为主世界。
逻辑已破案，但玩家还想继续盘问世界。
```

---

## 12. Recommended Next Steps

After 1.4:

1. Cut a `v1.4.0` git tag once the repository is back under version control.
2. Re-run `benchmark_full.py` and `benchmark_worldline.py` and refresh the
   numbers quoted in `README.md` / `PROJECT_NOTES.md` §9.
3. Start the WebUI adapter described in `ARCHITECTURE.md` §7, consuming
   `GameSession.current_state()` / `StoryBook` directly rather than parsing
   CLI text.
4. Decide whether `action_is_eligible`'s "one new group at a time" rule
   should extend to any other task, or stay specific to
   `cross_test_new_group` / `converge_outer_choice`.
