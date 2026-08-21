# QuestLine Architecture

## 1. Purpose

QuestLine is not only a Bulls & Cows answer finder. It is an explainable
investigation engine.

The solver should preserve reasonable AVG/MM efficiency while making each
action understandable as an information-gathering decision. Its central output
is therefore not only a guess, but a transition in an evolving investigation:

```text
State 1
  → current investigation task
  → selected action and rationale
  → feedback
  → changed facts
  → changed world-line picture
  → State 2
```

The story is the sequence of these transitions.

## 2. Design principles

### Facts before scores

The engine first describes what the remaining candidate worlds say. It tracks:

- candidate count and candidate space;
- digit identity support: excluded, possible, likely, confirmed;
- digit-to-position support and position status;
- fixed group relations (`01`, `23`, `45`, `67`, `89`);
- group conflicts, symmetry, and support gaps;
- the current investigation task and task feasibility.

Numerical efficiency is used after the task has constrained the eligible action
space. A raw score must not silently replace the investigation objective.

### No round-based plot

Tasks change because the facts change, not because a fixed round number was
reached. Typical tasks include establishing the foundation, introducing `45`,
breaking an outer-group symmetry, applying position pressure, and resolving the
endgame.

### Main worlds are interpretations

`main_world` means the currently leading explanation of the evidence. It is not
declared to be the real answer until feedback confirms the answer. Story text
must distinguish “currently leading” from “proven”.

### Position is second-layer evidence

Digits are the primary characters. Positions are the evidence that explains how
those characters fit into the final arrangement. The engine keeps all four
position supports, but the story only highlights meaningful changes or
threshold crossings so that statistical noise does not become fake plot.

## 3. Engine layers

```text
candidate filtering
        ↓
investigation_state()
        ↓
classify_action() / action_is_eligible()
        ↓
task_policy() / task_sort_key()
        ↓
choose() / next_guess()
        ↓
explain_transition()
        ↓
StoryBook
```

`investigation_state()` is the factual state layer. Action classification and
task eligibility are structural safeguards. Efficiency ranking chooses among
actions that are compatible with the current task.

The former patch-oriented scoring concepts—phase weights, guards, trigger
bonuses, semi-brakes, and fallback scoring—are not the architecture of 1.3.
They should not be reintroduced merely to fix an isolated recommendation.

## 4. Transition explanation contract

`QuestLineSolver.explain_transition(history, guess, feedback)` compares the
state before and after one feedback and returns:

- `action`: guess, feedback, and action classification;
- `decision`: task and action rationale;
- `before` / `after`: candidate count, task, and leading world groups;
- `facts`: digit identity changes;
- `position_facts`: position support changes;
- `group_changes`: changed group relations;
- `worldline`: leading-world support and confidence changes;
- `narrative`: a readable one-turn explanation.

This event is the atomic story unit. Presentation layers should consume this
structured event rather than reconstruct meaning from CLI text.

## 5. StoryBook model

`StoryBook` turns transition events into a case narrative:

- chapters are opened by investigation-task changes;
- digit indexes form character timelines;
- group indexes form faction timelines;
- events preserve world-line and position evidence;
- rendering produces a readable case book;
- structured data remains available for future UI clients.

The narrative has four scales:

1. **Digit** — a character becomes supported, weakened, excluded, or confirmed.
2. **Group** — a pair is symmetric, divided, mutually supported, or rejected.
3. **World line** — a complete explanation gains or loses support.
4. **Chapter** — the investigation task changes its question.

## 6. Three product modes

All modes should eventually share `GameSession`; only the actor and feedback
source differ:

| Mode | Human role | QuestLine role |
|---|---|---|
| Assist / 协查 | Acts in an external game and enters feedback | Interprets evidence and recommends action |
| Simulation / 推演 | Supplies the hidden answer | Acts step by step and exposes its reasoning |
| Adventure / 冒险 | Guesses | Supplies feedback and develops the case |

The CLI is a reference adapter and debugging surface. Future WebUI must consume
`GameSession` and `StoryBook` data directly, not parse CLI output.

## 7. 1.4 direction

The next product layer is:

```text
QuestLine Core Engine
        ↓
GameSession / StoryBook
        ↓
CLI Adapter       WebUI Adapter
```

`GameSession` should own mode, answer visibility, history, current state,
story, status, and turn transitions. `StoryBook` should grow from an event
sequence into a complete case narrative with chapters, turning points,
rejected hypotheses, current suspense, and closure.
