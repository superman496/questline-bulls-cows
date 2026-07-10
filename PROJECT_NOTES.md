# QuestLine Project Notes

> Project handoff and development notes for QuestLine.
>
> Current stable milestone: **v1.2.0 – Stable CLI Interaction Layer**
>
> Next milestone: **v1.3.0 – World-line Analysis**

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
- In v1.3, which world-line is currently strongest?

---

## 2. Current Stable Version

Current stable tag:

```text
v1.2.0
```

Current stable CLI file:

```text
questline_cli_v1_2_standalone.py
```

The v1.2.0 tag marks the stable interaction layer before starting v1.3 world-line analysis.

Recommended run commands:

```bash
python questline_cli_v1_2_standalone.py --lang zh
python questline_cli_v1_2_standalone.py --lang en
```

---

## 3. Main Files

Core files:

```text
questline.py                      # Core solver engine
questline_cli_v1_2_standalone.py  # Stable v1.2 CLI interaction layer
benchmark_full.py                 # Full 5040-answer benchmark
README.md                         # Public project documentation
CONTRIBUTING.md                   # Contribution notes
.gitignore                        # Ignore cache, replay, benchmark output, pycache
```

Current local/generated files that should generally not be committed:

```text
.questline_cache/
questline_replay_*.json
benchmark_full_results.json
__pycache__/
```

These are ignored by `.gitignore`.

---

## 4. v1.2.0 Stable CLI Features

v1.2.0 focuses on stabilizing the interactive CLI.

Implemented features:

- Chinese / English UI
- Multi-game loop
- Solved games do not force program exit
- `undo`, `history`, `report`, `new`, `quit`, and `help` commands
- Recommendation menu
- Recommendation sources:
  - `QuestLine`
  - `AVG`
  - `MM`
  - `Conspiracy`
  - `Manual`
- Stable 2 / 3 / 6 digit input grammar
- Flexible non-digit separators
- Feedback legality checks
- Duplicate guess conflict checks
- Consistency check before accepting any input, including `4b0c`
- Jackpot messages for first-guess solves
- Logical-solved state when only one possible answer remains
- Post-logic probing / 头铁验证 mode
- Replay JSON with rich metadata

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

This is intentional for v1.2:

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

The current stable interaction layer was tagged:

```text
v1.2.0
```

Command used:

```bash
git tag -a v1.2.0 -m "QuestLine CLI v1.2 stable"
git push origin v1.2.0
```

This tag marks the stable CLI interaction layer before v1.3 world-line work.

No GitHub Release has been created yet. The tag is sufficient as the current stable version anchor.

---

## 9. Benchmark Status

Full exhaustive benchmark over all 5040 possible answers has been run before v1.2 stabilization.

Known benchmark summary:

```text
total_codes: 5040
total_steps: 26695
average_steps: 5.296626984126984
min_steps: 1
max_steps: 7
```

Distribution:

```text
1 step: 1
2 steps: 4
3 steps: 108
4 steps: 546
5 steps: 2249
6 steps: 1991
7 steps: 141
8+ steps: 0
```

Important result:

```text
All 5040 answers solve within 7 steps.
No 8+ step cases.
```

---

## 10. v1.3 Direction: World-Line Analysis

v1.3 is not primarily a post-game review menu. The main goal is **world-line analysis**.

The user wants QuestLine to explain the reasoning story, not only output guesses.

Planned v1.3 analysis modules:

- Main world / 主世界
- Group structure based on:
  - `01`
  - `23`
  - `45`
  - `67`
  - `89`
- Top 2-digit group support
- Top 3-digit group support
- Top 4-digit candidate / group support
- Current main-world support rate
- Main-world support changes over time
- Endgame candidate ordering by narrative support
- Lucky-hit / 暴击参考 candidates
- Recommendation explanation for:
  - QuestLine
  - AVG
  - MM
  - Conspiracy

The report should help answer:

```text
为什么这条世界线更可信？
哪些组合正在变强？
主世界支持度是否突然下降？
当前引擎推荐是否符合人类推理预期？
```

---

## 11. Strategy Expectations to Revisit in v1.3

The user has a specific human strategy expectation:

```text
First move: judge 01 / 23
Second move: introduce 45
Third move: cross-test two digits from the first three groups and introduce 67
```

The user noticed that the current engine sometimes proposes moves like `68`-heavy tests and wants v1.3 world-line data before deciding how to adjust the engine.

Important design principle:

```text
Do not immediately retune the engine before world-line visibility exists.
First expose world-line statistics, then use evidence to decide whether the engine should change.
```

---

## 12. Potential v1.3 Output Sections

A future `report` could include:

```text
Current State
- Round
- Remaining possible answers
- Direct hit chance
- Pace / opening read
- Strategy state

World-Line Analysis
- Main world
- Main world support
- Top 2-groups
- Top 3-groups
- Top 4-groups

Recommendation Panel
- QuestLine Top 3
- Conspiracy Pick
- AVG
- MM
- bucket summaries

Endgame / Lucky Hit
- candidate list when small enough
- candidates sorted by narrative support
- direct-hit references
```

---

## 13. Project Philosophy Notes

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

## 14. Recommended Next Steps

Before starting v1.3:

1. Keep `questline_cli_v1_2_standalone.py` as the stable CLI.
2. Add this file as `PROJECT_NOTES.md`.
3. Optionally rename the stable CLI later to:

```text
questline_cli.py
```

4. Start v1.3 by adding world-line analysis helpers, preferably without immediately changing the engine recommendation logic.
5. Use world-line visibility to evaluate whether the engine should be retuned.
