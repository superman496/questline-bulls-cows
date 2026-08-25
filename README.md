# QuestLine

**Version 1.4**

QuestLine is a fact-driven investigation engine for the classic 4-digit Bulls
& Cows game. The 1.3 line replaced the original round-oriented scorer with an
investigation-task pipeline: candidate facts, digit identity, group
relations, position evidence, and world-line changes now drive every guess,
not a tuned score. The 1.4 line adds a shared `GameSession` state layer, turns
`StoryBook` into a full case narrative, and hardens the six-slot
recommendation panel (QuestLine ×3, AVG, MM, Conspiracy) so every slot carries
the same evidence and the endgame never silently drops a real candidate in
favor of a purely "efficient" probe.

**A narrative-driven Bulls & Cows solver.**  
**Follow the strongest story. Distrust coincidence.**

QuestLine is a deterministic, explainable solver for the classic **4-digit Bulls & Cows** game with non-repeating digits.

Unlike a pure bucket-splitting solver, QuestLine follows strong world lines, tracks digit groups, rotates cow information into bull pressure, and falls back to safer cuts when the signal gets weak.

> Build the story. Test the pressure. Distrust the lucky coincidence.

---

## Game rules

QuestLine assumes the common 4-digit Bulls & Cows variant:

- The secret code has **4 distinct digits**.
- Digits are selected from `0-9`.
- Leading zero is allowed.
- Feedback format is `xb yc`, written as `1b2c`, `0b1c`, `4b0c`, etc.
  - `bull`: correct digit in the correct position.
  - `cow`: correct digit in the wrong position.

Example:

```text
Secret: 1846
Guess : 1648
Result: 2b2c
```

---

## Strategy personality

QuestLine plays like a social deduction solver:

- **Build stable world lines** from the opening.
- **Trust strong, low-coincidence explanations**.
- **Convert cow information into bull pressure**.
- **Push when the story is strong**.
- **Slow down in complicated middle games**.
- **Fall back when signals stay weak**.
- **Use exact mechanical splitting when the endgame is solved**.

In short:

```text
Opening: fixed and stable.
Middle game: narrative-driven.
Advantage: push.
Disadvantage: stabilize.
Endgame: compress exactly.
```

---

## Features

- Single-file Python solver (`questline.py`), no third-party runtime dependencies.
- Deterministic lexicographic tie-breaks.
- Fast feedback matrix for interactive use, cached on disk between runs.
- Six-slot recommendation panel — QuestLine ×3, AVG, MM, Conspiracy — where
  every slot shares the same action/candidate schema, and the endgame task
  ranking (prefer a real candidate) is never overridden by the efficiency
  guardrail.
- Human-readable reports.
- World-line analysis in reports: main fixed-digit groups, support rates, and support changes over time.
- StoryBook chapters that connect state, action, feedback, facts, and world-line changes, plus an audit view with a digit identity-arc and per-digit case dossiers.
- Three narrative CLI modes: Assist, Simulation, and Adventure.
- `GameSession` shared state for all three modes.
- Structured session snapshots and transition timelines for future WebUI clients.
- Centralized, bilingual (zh/en) task, reason, and action labels
  (`QuestLineSolver.public_task` / `public_reason` / `public_action_label`),
  so the CLI cannot drift into inconsistent wording across screens.
- Compatible helper functions:
  - `choose_human_like_guess(history, top_k=15)`
  - `print_report(history)`
  - `interactive()`
- Built-in class API:
  - `QuestLineSolver.next_guess(history)`
  - `QuestLineSolver.play_answer(answer)`
  - `GameSession.current_state()`
  - `GameSession.timeline()`
  - `GameSession.save()` / `GameSession.resume()`
- `GameSession.replay()` / `GameSession.export_markdown()`

CLI case commands:

```text
save    save the current case JSON
replay  print structured accepted-transition JSON
export  write the current case book as Markdown
```

---

## Quick start

Clone the repository:

```bash
git clone https://github.com/superman496/questline-bulls-cows.git
cd questline-bulls-cows
```

Run the built-in demo:

```bash
python questline.py
```

Or use QuestLine from Python:

```python
from questline import QuestLineSolver

solver = QuestLineSolver()

history = [
    ("0123", "0b1c"),
    ("1045", "0b1c"),
]

print(solver.next_guess(history))
```

Print a detailed report:

```python
from questline import print_report

history = [
    ("0123", "0b1c"),
    ("1045", "0b1c"),
]

print_report(history)
```

Reports also expose the current world-line picture: the strongest fixed-digit
groups (`01`, `23`, `45`, `67`, `89`), their candidate support, the leading
margin over the next world, and the most supported 2-, 3-, and 4-digit
patterns. This is observability only; it does not retune recommendation
scoring.

See [`CHANGELOG.md`](CHANGELOG.md) for the complete version history.
See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the engine design, the
investigation decision chain, and the six-slot recommendation contract.

Interactive mode:

```python
from questline import interactive

interactive()
```

### CLI modes

The CLI uses one narrative vocabulary for all three ways to play:

1. **Assist mode / 协查模式** — the user plays an external game and enters
   feedback; QuestLine interprets the evidence and recommends the next action.
2. **Simulation mode / 推演模式** — the user supplies the answer; QuestLine
   acts step by step and exposes how it discovers the answer.
3. **Adventure mode / 冒险模式** — QuestLine creates a hidden answer; the user
   guesses while the system returns feedback and develops the story.

```bash
python questline_cli.py --mode assist
python questline_cli.py --mode simulation --answer 0456
python questline_cli.py --mode adventure
```

During Simulation and Adventure, enter `story` or `book` to read the current
case book. The previous parameter names `solver`, `explore`, and `story` remain
accepted as compatibility aliases.

---

## Example

```python
from questline import QuestLineSolver, fb_to_str

solver = QuestLineSolver()
answer = "0456"

for guess, feedback, remaining in solver.play_answer(answer):
    print(f"{guess} -> {fb_to_str(feedback)}  remaining={remaining}")
```

Possible output:

```text
0123 -> 1b0c  remaining=480
0456 -> 4b0c  remaining=1
```

---

## Benchmark

Rules:

- 4 digits
- no repeated digits
- leading zero allowed
- total answer space: `10P4 = 5040`

The exhaustive 5040-answer run is expensive to repeat on every change (each
answer plays through several full-space scoring rounds), so day-to-day
verification uses a random sample, the same way the 1.3 release did. A fresh
300-answer sample after the 1.4 recommendation-panel fixes:

| Metric | Value |
|---|---:|
| Answers sampled | 300 |
| Total steps | 1380 |
| Average steps | 4.60 |
| Min steps | 1 |
| Max steps | 7 |
| ≤4 steps | 136 (45.3%) |
| ≤5 steps | 255 (85.0%) |
| ≤6 steps | 295 (98.3%) |
| 7+ steps | 5 (1.7%) |
| 8+ steps | 0 |

Run it yourself:

```bash
python benchmark_full.py --limit 300
```

Or the full exhaustive benchmark (`python benchmark_full.py`, no `--limit`) —
see `PROJECT_NOTES.md` for the last known full-space numbers and when they
were last refreshed.

---

## Repository layout

```text
questline-bulls-cows/
├── questline.py               # Core solver engine: facts, tasks, six-slot recommendations, GameSession, StoryBook
├── questline_cli.py           # Interactive CLI: Assist / Simulation / Adventure, Chinese / English UI
├── benchmark_full.py          # Exhaustive 5040-answer benchmark
├── benchmark_worldline.py     # World-line observability benchmark
├── README.md                  # This file
├── ARCHITECTURE.md            # Engine design and decision chain
├── CHANGELOG.md               # Version history
├── PROJECT_NOTES.md           # Development handoff notes
├── CONTRIBUTING.md
├── LICENSE
├── .gitignore
├── examples/
│   └── interactive_demo.py
└── tests/
    └── test_solver.py
```

---

## Development

QuestLine has no third-party runtime dependencies.

For tests, install `pytest` if needed:

```bash
python -m pip install pytest
pytest
```

---

## License

This project is released under the MIT License.
