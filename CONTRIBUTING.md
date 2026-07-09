# Contributing

Thanks for your interest in QuestLine.

This is a small experimental solver project. Contributions are welcome, especially:

- benchmark improvements;
- clearer strategy explanations;
- tests for known branches;
- performance optimizations;
- documentation improvements.

## Development setup

```bash
git clone https://github.com/superman496/questline-bulls-cows.git
cd questline-bulls-cows
python -m pip install pytest
pytest
```

## Style

- Keep the solver deterministic.
- Preserve the `1b2c` feedback format.
- Avoid changing opening tie-breaks unless the benchmark proves it is worth it.
- Prefer readable strategy comments over clever but opaque code.

## Strategy philosophy

QuestLine is not intended to be a pure AVG or minimax clone.
Its goal is to combine strong performance with explainable, narrative-driven reasoning.
