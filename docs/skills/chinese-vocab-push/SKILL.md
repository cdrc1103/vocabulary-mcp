---
name: chinese-vocab-push
description: >
  Push Chinese vocabulary words to the Vocabulary App MCP at the end of a Chinese tutoring session.
  Use this skill whenever the user says "wrap up", "end session", "save vocab", "push vocab", "add words to app",
  or any similar phrase indicating the session is ending and vocabulary should be saved.
  Always ask the student whether they want regular word cards (bulk_add_vocabulary) or single-character
  Heisig-style cards (add_hanzi) — never omit Pinyin, never skip the example sentence.
  Example sentences must show the context and grammar situation a word is used in.
  This skill MUST be used at end-of-session; do not add vocab word by word during the session.
---

# Chinese Vocabulary Push Skill

## Purpose

Save all new Chinese vocabulary introduced during a tutoring session to the Vocabulary App MCP, using a consistent flashcard format optimised for spaced-repetition review. The example sentence is the most important part of the card after the word itself: it is how the student learns **when** and **how** to use the word.

---

## Card Format (strictly enforced)

| Field | Content |
|---|---|
| `word` | Hanzi only — e.g. `请假` |
| `pinyin` | Pinyin with tone marks, in its own field — e.g. `qǐngjià`. Never tone numbers, never inside `definition`. |
| `definition` | English meaning only, no pinyin — e.g. `to ask for leave; to take days off` |
| `example` | One example sentence in **hanzi only**, with Chinese punctuation — e.g. `我向经理请了一天假。` |
| `example_pinyin` | Pinyin of the example sentence with tone marks, word-spaced, capitalised first letter, with punctuation — e.g. `Wǒ xiàng jīnglǐ qǐng le yì tiān jià.` |
| `example_translation` | Natural English translation of the example — e.g. `I asked the manager for one day off.` |
| `language` | Always `"zh"` |
| `session_name` | All lowercase, no hyphens, no difficulty level, 1–3 words — e.g. `"daily routines"` or `"feelings"` |

The three example fields are separate. **Never** put the pinyin or the English into `example` — the app speaks the `example` field aloud and would read them out.

### Example card (fully filled out)

```json
{
  "word": "请假",
  "pinyin": "qǐngjià",
  "definition": "to ask for leave; to take days off",
  "example": "我向经理请了一天假。",
  "example_pinyin": "Wǒ xiàng jīnglǐ qǐng le yì tiān jià.",
  "example_translation": "I asked the manager for one day off.",
  "language": "zh",
  "session_name": "work life"
}
```

---

## Writing the example sentence

The student wants to understand **in which context** and **in which grammar situation** a word is used. A sentence that merely contains the word is not enough. Write each example so that it teaches the use of the word:

1. **Show the typical context.** Put the word in a realistic situation the student could actually be in (at work, shopping, with friends, at a restaurant…), with the who / when / where visible in the sentence. Avoid abstract or textbook-flat sentences such as "这是请假。".

2. **Make the grammar situation visible.** Choose the sentence that demonstrates the pattern the word is really used in, and keep the surrounding words that always go with it:
   - the preposition or particle it needs (`向 + person + verb`, `对 … 感兴趣`),
   - the measure word with its number (`三瓶水`, `一个超市`),
   - the verb pattern: verb–object verbs that split (`请了一天假`, `帮帮忙`), resultative or directional complements, `了` / `过` / `着`, `把` / `被` structures, `想` / `要` / `应该` + verb,
   - the word class it behaves as (a word that is both noun and measure word, or verb and preposition, should be shown in its main use as given in the definition).

3. **If the word has a pitfall, show it in the sentence.** For example: a verb–object word taking `了` and a duration in the middle, a measure word that cannot stand alone, a word that goes before the verb rather than after, a word that is normally followed by a specific particle. The sentence should model the correct way so the student sees it, not just hears about it.

4. **Reuse the session.** If the tutoring session already used the word in a sentence that fits the rules above (especially one from the student's own life or their textbook), reuse it — corrected if needed — rather than inventing a new one.

5. **Keep it learnable.** One clause where possible, about 6–14 characters, HSK 2–3 vocabulary plus words already seen in the session, so the only new thing in the sentence is the target word and its pattern.

6. **Translate for structure.** `example_translation` should be natural English that still lets the student trace the Chinese structure (the preposition, the measure word, the particle). Not word-for-word, but not so free that the pattern disappears.

7. **Check it.** The sentence must be grammatically correct, natural Mandarin. Double-check measure words, particle placement, aspect markers and word order before saving. Check that `example_pinyin` matches the hanzi exactly and uses the right tone marks for the word as used in the sentence.

Each card carries one example. If a word has a second important use, mention it to the student in the chat summary instead of overloading the card.

---

## Heisig Card Format (used only if the student picks "Heisig cards")

Heisig cards save one card per **individual hanzi** (not per word), each with a single English keyword, pinyin and tone.

### Steps

1. **Explode the word list into unique characters.** Take every new word/phrase from the session, split it into individual hanzi, and dedupe (e.g. `预约` + `座位` → `预`, `约`, `座`, `位`). Characters that already exist as cards are simply enriched in place by `add_hanzi`, which is fine.

2. **For each character, build a card with:**
   - `hanzi` — the single character.
   - `keyword` — one English word capturing its core meaning (not a phrase).
   - `pinyin` — with tone mark, never tone numbers.
   - `tone` — 1–5 (5 = neutral).
   - `definition` — meaning/usage only, no pinyin.
   - `example`, `example_pinyin`, `example_translation` — a sentence or short word that uses the character in its common role, written under the same rules as above (hanzi only / pinyin / English). Prefer a common word or phrase from the session that shows the character in context. These are only used when a card is *created*; they are ignored when the call enriches an existing card.

3. **Push via `add_hanzi`** with all cards in a single call and `session_name` set to the session's name (new cards join this session; existing cards keep their session).

### Example card

```json
{
  "hanzi": "位",
  "keyword": "position",
  "pinyin": "wèi",
  "tone": 4,
  "definition": "position; measure word for people (polite)",
  "example": "请问几位？",
  "example_pinyin": "Qǐngwèn jǐ wèi?",
  "example_translation": "Excuse me, how many people (in your party)?"
}
```

### Heisig-specific quality rules

- One card per **character**, never per multi-character word.
- Re-running `add_hanzi` on an existing character enriches it in place (keeps its review schedule) rather than duplicating — this is expected, not an error.

---

## Workflow

1. **Collect** — scan the conversation for every new Chinese word or phrase introduced during the session (including words drilled, explained, or used in example sentences that were new to the student).

2. **Deduplicate** — skip words already present in the student's known vocabulary (if inferable from context). When in doubt, include it.

3. **Ask the format question** — before building any cards, ask the student whether they want:
   - **Regular cards** — one card per word/phrase, or
   - **Heisig cards** — the words broken down into individual hanzi.

   Use a single-question, single-select prompt (e.g. via `ask_user_input_v0` if available) with options like "Regular cards" / "Heisig cards". If the student has already stated a standing preference earlier in the conversation or in a prior session, skip the question and use that preference.

4a. **If Regular cards** — build each card exactly as in the Card Format section, writing the example according to "Writing the example sentence". Then go to step 5.

4b. **If Heisig cards** — follow the Heisig Card Format section, then go to step 5.

5. **Choose a session name** — derive a concise, descriptive `session_name` from the main topic(s) of the session. Rules: all lowercase, no hyphens, no difficulty level, 1–3 words max.

6. **Push via MCP** — for regular cards call `Vocabulary App:bulk_add_vocabulary` with all words in a single call; for Heisig cards call `Vocabulary App:add_hanzi` with all cards in a single call. Set the top-level `session_name` parameter to the chosen name.

7. **Confirm** — after the MCP call succeeds, display a short summary table in chat, including the example so the student can check it.

   For regular cards:

   | # | Hanzi | Pinyin | English | Example |
   |---|-------|--------|---------|---------|
   | 1 | 请假 | qǐngjià | to ask for leave | 我向经理请了一天假。 |

   For Heisig cards:

   | Hanzi | Keyword | Pinyin | Tone |
   |---|---|---|---|
   | 位 | position | wèi | 4 |

   Then tell the student: "✅ X words added to your Vocabulary App under **[session_name]**. 加油！" (for Heisig cards, note how many were new vs. enriched). If a word has a second important use that did not fit on the card, mention it here in one line.

---

## Error handling

- If the MCP call fails, retry once. If it fails again, present the full word/card list as a formatted table in chat so the student doesn't lose the vocabulary, and explain that the app couldn't be reached.
- If a word has no obvious example sentence from the session, write one following "Writing the example sentence".

---

## Quality rules

- **Always** include Pinyin with tone marks (ā á ǎ à), never tone numbers.
- **Never** leave `definition`, `example`, `example_pinyin` or `example_translation` blank.
- **Never** put pinyin in `definition`, or pinyin/English in `example`.
- Every example must show the word in a realistic context and in its typical grammar pattern.
- Example sentences must be grammatically correct Mandarin — double-check measure words and particle usage before saving.
- Do **not** add grammar explanations or long notes to `definition` — put them in the lesson; the example sentence carries the usage.
