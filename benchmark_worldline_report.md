# QuestLine World-Line Evaluation

> Observability benchmark only; recommendation scoring was not changed.

## Overall

- Answers evaluated: **5040**
- Average steps: **5.2966**
- Maximum steps: **7**
- Total guesses: **26695**
- Unique guesses: **5040**
- 68-heavy guesses: **3432 (12.86%)**

## Group frequency

| Group | Count |
|---|---:|
| 01 | 21057 |
| 23 | 17997 |
| 45 | 15917 |
| 67 | 13893 |
| 89 | 11204 |

## By round

| Round | Games | 45 rate | 67 rate | Human r3 pattern | Main-world aligned | 68-heavy |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 5040 | 0.0% | 0.0% | 0.0% | 92.9% | 0.0% |
| 2 | 5039 | 99.8% | 16.7% | 0.0% | 96.2% | 0.0% |
| 3 | 5035 | 69.9% | 95.1% | 80.3% | 100.0% | 36.8% |
| 4 | 4927 | 61.9% | 71.5% | 0.0% | 99.9% | 14.7% |
| 5 | 4381 | 64.6% | 74.3% | 0.0% | 100.0% | 12.8% |
| 6 | 2132 | 66.2% | 64.9% | 0.0% | 100.0% | 13.0% |
| 7 | 141 | 54.6% | 75.9% | 0.0% | 100.0% | 13.5% |

## Interpretation

- `45 rate` measures whether a guess uses at least one digit from group `45`.
- `67 rate` measures whether a guess uses at least one digit from group `67`.
- The human round-3 pattern requires group `67` plus coverage of at least two of `01`, `23`, and `45`.
- Main-world alignment means the guess uses at least one digit from a currently strongest fixed group; it is not a quality judgment.
- 68-heavy is a descriptive count, not evidence by itself that the strategy is wrong.
