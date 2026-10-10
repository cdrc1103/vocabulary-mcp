// Pure pinyin / text helpers shared by the study views. No DOM access here, so
// everything in this file can be unit-tested with plain `node --test`.

const TONE_MARKS = {
  ā: ["a", 1],
  á: ["a", 2],
  ǎ: ["a", 3],
  à: ["a", 4],
  ē: ["e", 1],
  é: ["e", 2],
  ě: ["e", 3],
  è: ["e", 4],
  ī: ["i", 1],
  í: ["i", 2],
  ǐ: ["i", 3],
  ì: ["i", 4],
  ō: ["o", 1],
  ó: ["o", 2],
  ǒ: ["o", 3],
  ò: ["o", 4],
  ū: ["u", 1],
  ú: ["u", 2],
  ǔ: ["u", 3],
  ù: ["u", 4],
  ǖ: ["v", 1],
  ǘ: ["v", 2],
  ǚ: ["v", 3],
  ǜ: ["v", 4],
};

// Letters that may legally start / end a syllable. Deliberately a little
// over-permissive (e.g. it accepts "ju" for "jü"): the segmenter below only has
// to find *a* split with the right syllable count, not validate pinyin.
const SYLLABLE =
  /^(?:zh|ch|sh|[bpmfdtnlgkhjqxzcsrwy])?(?:iang|iong|uang|ueng|ang|eng|ing|ong|ian|iao|uai|uan|van|ai|ei|ao|ou|an|en|er|ia|ie|iu|in|ua|uo|ui|un|ue|ve|vn|a|o|e|i|u|v)$/;
const MAX_SYLLABLE_LEN = 6; // zhuang, chuang, shuang

// CJK ideographs, plus the full-width punctuation that appears in sentences.
const CJK = /[\u3400-\u9fff\uf900-\ufaff]/;
const SPEAKABLE = /[\u3400-\u9fff\uf900-\ufaff，。！？、；：]/g;

export const isHanzi = (ch) => CJK.test(ch);

// Keep only the Chinese part of a free-text field. The example field may mix
// the sentence with pinyin or an English gloss, and the speech engine should
// only be given the Chinese.
export function speakableText(text) {
  return ((text || "").match(SPEAKABLE) || []).join("");
}

// Short label for an answer option: the first sense of the definition, trimmed.
export function shortMeaning(definition, max = 48) {
  const first = (definition || "").split(/\s*[;；]\s*|\s+\/\s+/)[0].trim();
  if (first.length <= max) return first;
  const cut = first.slice(0, max);
  const lastSpace = cut.lastIndexOf(" ");
  return `${cut.slice(0, lastSpace > max / 2 ? lastSpace : max)}…`;
}

// Split a card into its pinyin and English parts. New cards carry pinyin in a
// dedicated field (card.pinyin; Heisig cards also in heisig.pinyin). Legacy
// regular cards stored "pinyin | english" in the definition, so that is kept as
// a backup. Returns pinyin: "" when the card has no pinyin to show.
export function splitPinyin(card) {
  const definition = card.definition || "";
  const stored = card.pinyin || card.heisig?.pinyin;
  if (stored) return { pinyin: stored, english: definition };
  const sep = definition.indexOf(" | ");
  if (sep === -1) return { pinyin: "", english: definition };
  return {
    pinyin: definition.slice(0, sep).trim(),
    english: definition.slice(sep + 3).trim(),
  };
}

// Break a pinyin string into per-letter data: base letters (ü → v), the
// original display character, the tone attached to each letter (0 = none), and
// the positions where whitespace / apostrophes / hyphens force a syllable break.
function scan(pinyin) {
  const base = [];
  const orig = [];
  const tone = [];
  const breaks = new Set();
  const text = pinyin.toLowerCase().normalize("NFC").replace(/u:/g, "ü");
  for (const ch of text) {
    if (TONE_MARKS[ch]) {
      base.push(TONE_MARKS[ch][0]);
      orig.push(ch);
      tone.push(TONE_MARKS[ch][1]);
    } else if (ch === "ü") {
      base.push("v");
      orig.push(ch);
      tone.push(0);
    } else if (/[a-z]/.test(ch)) {
      base.push(ch);
      orig.push(ch);
      tone.push(0);
    } else if (/[0-5]/.test(ch)) {
      // tone number typed after its syllable ("tui3"); 0 and 5 are neutral
      if (base.length) tone[tone.length - 1] = ch === "0" ? 5 : Number(ch);
    } else if (ch === "(" || ch === ")" || ch === "（" || ch === "）") {
      // optional-syllable markers: keep the letters, drop the brackets
    } else if (base.length) {
      breaks.add(base.length);
    }
  }
  return { base, orig, tone, breaks };
}

// Segment a pinyin string into exactly `count` syllables, or return null when
// no valid split exists (erhua "diǎnr", slash alternatives, typos, ...).
// Each syllable is { text, tone (1-5, 5 = neutral), gap }; `gap` is true when a
// space separated it from the previous syllable in the source.
export function pinyinSyllables(pinyin, count) {
  if (!pinyin || count < 1) return null;
  const { base, orig, tone, breaks } = scan(pinyin);
  const n = base.length;
  if (n === 0) return null;
  const dead = new Set();

  function toneOf(i, j) {
    let found = 0;
    for (let k = i; k < j; k++) {
      if (tone[k]) {
        if (found) return -1; // two tone marks inside one syllable
        found = tone[k];
      }
    }
    return found || 5;
  }

  function go(i, left) {
    if (i === n) return left === 0 ? [] : null;
    if (left === 0 || dead.has(i * 64 + left)) return null;
    for (let j = Math.min(n, i + MAX_SYLLABLE_LEN); j > i; j--) {
      let crosses = false;
      for (let b = i + 1; b < j; b++) if (breaks.has(b)) crosses = true;
      if (crosses || toneOf(i, j) === -1) continue;
      if (!SYLLABLE.test(base.slice(i, j).join(""))) continue;
      const rest = go(j, left - 1);
      if (rest) return [[i, j], ...rest];
    }
    dead.add(i * 64 + left);
    return null;
  }

  const spans = go(0, count);
  if (!spans) return null;
  return spans.map(([i, j]) => ({
    text: orig.slice(i, j).join(""),
    tone: toneOf(i, j),
    gap: i > 0 && breaks.has(i),
  }));
}

// Pair each character of `word` with its tone. Returns null when the pinyin
// can't be matched one-to-one to the hanzi, so callers can fall back to plain
// text. Non-hanzi characters (punctuation, latin letters) get tone null.
export function toneSpans(word, pinyin) {
  const chars = [...(word || "")];
  const hanzi = chars.filter(isHanzi).length;
  const syllables = hanzi ? pinyinSyllables(pinyin, hanzi) : null;
  if (!syllables) return null;
  let s = 0;
  return chars.map((ch) => ({ ch, tone: isHanzi(ch) ? syllables[s++].tone : null }));
}
