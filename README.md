# QuestLine

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

- Single-file Python solver.
- No third-party runtime dependencies.
- Deterministic lexicographic tie-breaks.
- Fast feedback matrix for interactive use.
- Human-readable reports.
- Compatible helper functions:
  - `choose_human_like_guess(history, top_k=15)`
  - `print_report(history)`
  - `interactive()`
- Built-in class API:
  - `BullsCowsSolver.next_guess(history)`
  - `BullsCowsSolver.play_answer(answer)`

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
from questline import BullsCowsSolver

solver = BullsCowsSolver()

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

Interactive mode:

```python
from questline import interactive

interactive()
```

---

## Example

```python
from questline import BullsCowsSolver, fb_to_str

solver = BullsCowsSolver()
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

## Benchmark snapshot

On two fixed random samples totaling 400 answers:

| Strategy | Average | ≤4 steps | ≤5 steps | ≤6 steps | 7+ steps |
|---|---:|---:|---:|---:|---:|
| QuestLine | 5.2275 | 65 | 239 | 394 | 6 |
| AVG baseline | 5.2350 | 59 | 245 | 396 | 4 |
| MM baseline | 5.3650 | 52 | 212 | 390 | 10 |

Interpretation:

- QuestLine keeps AVG-level average performance.
- QuestLine has a higher burst rate than AVG.
- QuestLine has a shorter tail than MM.
- QuestLine is designed for explainability, not only raw bucket splitting.

---

## Repository layout

Suggested layout:

```text
questline-bulls-cows/
├── questline.py
├── README.md
├── LICENSE
├── .gitignore
├── examples/
│   └── interactive_demo.py
├── tests/
│   └── test_solver.py
└── benchmark.py
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
