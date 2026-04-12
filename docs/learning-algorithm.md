# Learning Algorithm — SM-2 Spaced Repetition

## What is SM-2?

SM-2 (SuperMemo 2, 1987) is a spaced repetition algorithm that schedules reviews at increasing intervals. Cards you know well reappear less often; cards you struggle with reappear sooner. The goal: maximise retention with minimum review time.

---

## State per word

Each vocabulary word carries three mutable fields updated after every review:

| Field | Default | Meaning |
|---|---|---|
| `interval` | 1 | Days until the next review |
| `ease_factor` | 2.5 | Difficulty multiplier (min 1.3) |
| `repetitions` | 0 | Consecutive successful reviews |
| `next_review` | today | Absolute date of next review |

---

## Quality scores

After flipping a card the user rates recall quality (0–5):

| Button | Score | Meaning |
|---|---|---|
| Again | 0 | Complete blackout |
| Hard | 2 | Wrong, but word felt familiar |
| Okay | 3 | Correct, with difficulty |
| Good | 4 | Correct after slight hesitation |
| Easy | 5 | Perfect, instant recall |

Scores 0–2 are **failures** (quality < 3). Score 3–5 are **passes**.

---

## Algorithm (`backend/database.py:54`)

```python
def apply_sm2(interval, ease, reps, quality):
    if quality < 3:                          # failure — reset streak
        return 1, ease, 0

    if reps == 0:
        new_interval = 1                     # first pass → review tomorrow
    elif reps == 1:
        new_interval = 6                     # second pass → review in 6 days
    else:
        new_interval = round(interval * ease)  # subsequent → grow by EF

    new_ease = ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ease = max(1.3, new_ease)

    return new_interval, new_ease, reps + 1
```

### Ease factor delta by quality

| Quality | EF change | Example (EF 2.5 → …) |
|---|---|---|
| 5 (Easy) | +0.10 | 2.60 |
| 4 (Good) | +0.00 | 2.50 |
| 3 (Okay) | −0.14 | 2.36 |
| < 3 (fail) | unchanged | 2.50 (streak resets) |

Minimum EF is clamped to **1.3**, preventing intervals from collapsing on very difficult words.

---

## Review cycle example

Starting state: `interval=1, ease=2.5, reps=0`

| Session | Quality | New interval | New EF | New reps | Next review |
|---|---|---|---|---|---|
| 1 | 4 (Good) | 1 day | 2.50 | 1 | +1 d |
| 2 | 4 (Good) | 6 days | 2.50 | 2 | +6 d |
| 3 | 4 (Good) | 15 days | 2.50 | 3 | +15 d |
| 4 | 5 (Easy) | 38 days | 2.60 | 4 | +38 d |
| 5 | 2 (Hard) | **1 day** | 2.60 | **0** | +1 d |

A single failure resets the streak and interval to 1, but **ease factor is preserved** across failures — accumulated difficulty history is not lost.

---

## Scheduling

After `apply_sm2` returns, `review_word` in `database.py:215` computes the next review date:

```python
next_review = (date.today() + timedelta(days=new_interval)).isoformat()
```

`GET /vocabulary/due` returns all words where `next_review <= today`, which populates the study session.

---

## Study modes

The PWA supports two orientations of the same card:

- **Normal mode** — front: word, back: definition + example
- **Reverse mode** — front: definition, back: word + example

Both modes submit identical quality scores to the same SM-2 endpoint; the algorithm is unaffected by which side is shown.
