// Multiple-choice quiz. The question kinds follow the Normal / Reverse study
// toggle, so every answer updates the SM-2 schedule of the direction it tests:
//   Normal : hanzi → meaning, hanzi → pinyin
//   Reverse: meaning → hanzi, pinyin → hanzi, sound → hanzi
import { shortMeaning, splitPinyin, toneSpans } from "./pinyin.js";
import { canSpeak, getSettings, speak, speakCard, stopSpeaking } from "./speech.js";

// Multiple choice is weaker evidence than a self-rated recall, so a correct
// answer never counts as "Easy" (5), and a miss is a clear failure.
export const QUALITY = { right: 4, wrong: 1 };

const OPTION_COUNT = 4;
const SIMILAR_POOL = 8; // distractors are drawn from the N most similar cards

// ── Tiny DOM helper (textContent only, never innerHTML) ──────────────────────
function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v);
  }
  el.append(...children.filter((c) => c != null));
  return el;
}

// A word as hanzi spans coloured by tone; plain text when the tones can't be
// matched to the characters.
export function toneWord(word, pinyin, className = "") {
  const el = h("span", { class: className, lang: "zh-Hans" });
  const spans = toneSpans(word, pinyin);
  if (!spans) {
    el.textContent = word;
    return el;
  }
  for (const { ch, tone } of spans) {
    el.append(tone ? h("span", { class: `tone-${tone}`, text: ch }) : ch);
  }
  return el;
}

// The example sentence as up to three lines: hanzi, pinyin, English. Cards saved
// before the parts were split out keep whatever text they had in `example`
// (line breaks preserved). Returns null when the card has no example.
export function exampleBlock(card) {
  if (!card.example) return null;
  return h(
    "div",
    { class: "ex-block" },
    h("p", { class: "ex-zh", lang: "zh-Hans", text: card.example }),
    card.example_pinyin ? h("p", { class: "ex-py", text: card.example_pinyin }) : null,
    card.example_translation ? h("p", { class: "ex-en", text: card.example_translation }) : null
  );
}

function shuffle(arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

// ── Question kinds ────────────────────────────────────────────────────────────
const meaningOf = (c) => c.heisig?.keyword || shortMeaning(splitPinyin(c).english);
const pinyinOf = (c) => splitPinyin(c).pinyin;

// label(card) is what an option shows, and what must differ between options.
const KINDS = {
  hz2en: { label: meaningOf, hanziOptions: false, autoPrompt: true },
  hz2py: { label: pinyinOf, hanziOptions: false, autoPrompt: false },
  en2hz: { label: (c) => c.word, hanziOptions: true, autoPrompt: false },
  py2hz: { label: (c) => c.word, hanziOptions: true, autoPrompt: false },
  snd2hz: { label: (c) => c.word, hanziOptions: true, autoPrompt: "always" },
};

function kindsFor(card, reverse) {
  const hasPinyin = !!pinyinOf(card);
  const hasMeaning = !!meaningOf(card);
  const kinds = [];
  if (reverse) {
    if (hasMeaning) kinds.push("en2hz");
    if (hasPinyin) kinds.push("py2hz");
    if (canSpeak()) kinds.push("snd2hz");
  } else {
    if (hasMeaning) kinds.push("hz2en");
    if (hasPinyin) kinds.push("hz2py");
  }
  return kinds;
}

// Pick distractors that differ in label from the answer and from each other,
// preferring cards that look alike (same character count, same kind of card).
function distractors(card, kind, pool) {
  const { label } = KINDS[kind];
  const answer = label(card);
  const len = [...card.word].length;
  const similarity = (c) =>
    ([...c.word].length === len ? 2 : 0) + (!!c.heisig === !!card.heisig ? 1 : 0);
  const seen = new Set([answer]);
  const candidates = shuffle(pool)
    .filter((c) => c.id !== card.id)
    .sort((a, b) => similarity(b) - similarity(a))
    .filter((c) => {
      const text = label(c);
      if (!text || seen.has(text)) return false;
      seen.add(text);
      return true;
    });
  return shuffle(candidates.slice(0, SIMILAR_POOL)).slice(0, OPTION_COUNT - 1);
}

function buildQuestion(card, reverse, pool) {
  for (const kind of shuffle(kindsFor(card, reverse))) {
    const others = distractors(card, kind, pool);
    if (others.length === OPTION_COUNT - 1) {
      return { card, kind, options: shuffle([card, ...others]) };
    }
  }
  return null;
}

// ── Quiz controller ───────────────────────────────────────────────────────────
// root:   element the quiz renders into
// hooks:  { submitReview(id, quality), onProgress(text), onFinish(count) }
export function createQuiz(root, hooks) {
  let queue = [];
  let index = 0;
  let reviewed = 0;
  let reverse = false;
  let pool = [];
  let current = null; // { question, answered, picked }
  let active = false;

  function stop() {
    active = false;
    document.removeEventListener("keydown", onKey);
    stopSpeaking();
    root.replaceChildren();
  }

  function start(cards, fullDeck, isReverse) {
    stop();
    active = true;
    reverse = isReverse;
    pool = fullDeck;
    queue = cards.map((card) => ({ card, retry: false }));
    index = 0;
    reviewed = 0;
    document.addEventListener("keydown", onKey);
    next();
  }

  function next() {
    // Skip cards that can't make a question (e.g. no other card has a different answer).
    while (index < queue.length) {
      const item = queue[index];
      const question = buildQuestion(item.card, reverse, pool);
      if (question) {
        current = { item, question, answered: false, picked: null };
        hooks.onProgress(`${index + 1} / ${queue.length}`);
        renderQuestion();
        return;
      }
      index++;
    }
    stop();
    hooks.onFinish(reviewed);
  }

  function renderQuestion() {
    const { question } = current;
    const { card, kind } = question;
    const { pinyin } = splitPinyin(card);
    const speakOnPrompt = KINDS[kind].autoPrompt;

    const prompt = h("div", { class: "quiz-prompt" });
    if (kind === "hz2en" || kind === "hz2py") {
      prompt.append(
        h("p", {
          class: "quiz-label",
          text: kind === "hz2en" ? "What does it mean?" : "Which pinyin is it?",
        }),
        // Tone colours on the hanzi would give away the answer to the pinyin question.
        kind === "hz2py"
          ? h("span", { class: "quiz-hanzi", lang: "zh-Hans", text: card.word })
          : toneWord(card.word, pinyin, "quiz-hanzi")
      );
    } else if (kind === "snd2hz") {
      prompt.append(
        h("p", { class: "quiz-label", text: "Listen, then choose the word" }),
        h("button", {
          class: "btn btn-secondary quiz-play",
          type: "button",
          text: "🔊 Play sound",
          onclick: () => speak(card.word),
        })
      );
    } else {
      prompt.append(
        h("p", { class: "quiz-label", text: "Which word is this?" }),
        kind === "en2hz"
          ? h("p", { class: "quiz-meaning", text: meaningOf(card) })
          : h("p", { class: "quiz-pinyin", text: pinyin })
      );
    }

    const opts = h("div", { class: "quiz-options", role: "group", "aria-label": "Answers" });
    question.options.forEach((option, i) => {
      const btn = h("button", {
        class: `quiz-option${KINDS[kind].hanziOptions ? " quiz-option-hanzi" : ""}`,
        type: "button",
        "data-id": String(option.id),
        onclick: () => answer(option.id),
      });
      btn.append(
        h("span", { class: "quiz-key", "aria-hidden": "true", text: String(i + 1) }),
        // Plain text: tone colours on the options would leak the tone of the answer.
        h("span", {
          text: KINDS[kind].label(option),
          ...(KINDS[kind].hanziOptions ? { lang: "zh-Hans" } : {}),
        })
      );
      opts.append(btn);
    });

    root.replaceChildren(prompt, opts, h("div", { class: "quiz-result", "aria-live": "polite" }));

    // Called synchronously from the tap that got us here, which keeps iOS happy.
    if (speakOnPrompt === "always" || (speakOnPrompt && getSettings().autoplay)) {
      speak(card.word);
    }
  }

  function answer(pickedId) {
    if (!current || current.answered) return;
    current.answered = true;
    current.picked = pickedId;
    const { item, question } = current;
    const { card } = question;
    const correct = pickedId === card.id;

    // Only the first attempt counts for the schedule; a retry is just practice.
    if (!item.retry) {
      reviewed++;
      hooks.submitReview(card.id, correct ? QUALITY.right : QUALITY.wrong);
      if (!correct) queue.push({ card, retry: true });
    }

    for (const btn of root.querySelectorAll(".quiz-option")) {
      btn.disabled = true;
      const id = Number(btn.dataset.id);
      if (id === card.id) btn.classList.add("right");
      else if (id === pickedId) btn.classList.add("wrong");
    }

    const { pinyin, english } = splitPinyin(card);
    const result = root.querySelector(".quiz-result");
    const nextBtn = h("button", {
      class: "btn btn-primary quiz-next",
      type: "button",
      text: "Next →",
      onclick: () => {
        index++;
        next();
      },
    });
    result.replaceChildren(
      h("p", {
        class: `quiz-verdict ${correct ? "ok" : "no"}`,
        text: correct ? "✓ Correct" : "✗ Not quite",
      }),
      toneWord(card.word, pinyin, "quiz-hanzi quiz-hanzi-sm"),
      pinyin ? h("p", { class: "quiz-pinyin", text: pinyin }) : null,
      h("p", { class: "quiz-english", text: english }),
      exampleBlock(card),
      h(
        "div",
        { class: "quiz-actions" },
        h("button", {
          class: "btn btn-secondary",
          type: "button",
          text: "🔊 Hear it",
          onclick: () => speakCard(card),
        }),
        nextBtn
      )
    );
    nextBtn.focus({ preventScroll: true });
    if (getSettings().autoplay) speakCard(card);
  }

  function onKey(e) {
    if (!active || !current || e.metaKey || e.ctrlKey || e.altKey) return;
    if (/^(INPUT|TEXTAREA)$/.test(document.activeElement?.tagName)) return;
    const n = Number(e.key);
    if (!current.answered && n >= 1 && n <= OPTION_COUNT) {
      const option = current.question.options[n - 1];
      if (option) answer(option.id);
    } else if (current.answered && e.key === "Enter") {
      e.preventDefault();
      root.querySelector(".quiz-next")?.click();
    }
  }

  return { start, stop };
}
