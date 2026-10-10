// Text-to-speech through the browser's Web Speech API, using the device's own
// Mandarin voice (on iPhone these are the system voices from iOS).
import { speakableText } from "./pinyin.js";

const KEYS = {
  autoplay: "vocab_autoplay",
  rate: "vocab_speech_rate",
  audioFirst: "vocab_audio_first",
};

const synth = typeof window !== "undefined" && "speechSynthesis" in window ? speechSynthesis : null;

// ── Settings (persisted per device) ───────────────────────────────────────────
const settings = { autoplay: true, rate: 0.8, audioFirst: false };
try {
  settings.autoplay = localStorage.getItem(KEYS.autoplay) !== "false";
  settings.audioFirst = localStorage.getItem(KEYS.audioFirst) === "true";
  const rate = Number(localStorage.getItem(KEYS.rate));
  if (rate >= 0.4 && rate <= 1.2) settings.rate = rate;
} catch {
  // storage unavailable — defaults apply for this page load
}

export const getSettings = () => ({ ...settings });

export function setSetting(name, value) {
  settings[name] = value;
  try {
    localStorage.setItem(KEYS[name], String(value));
  } catch {
    // storage unavailable — setting lasts for this page load only
  }
}

// ── Voice selection ───────────────────────────────────────────────────────────
let voices = [];
let voice = null;
const listeners = new Set();

const langOf = (v) => v.lang.replace("_", "-").toLowerCase();
const isCantonese = (v) =>
  /^zh-hk$|^yue/.test(langOf(v)) || /cantonese|粤|廣東|sinji|sin-ji/i.test(v.name);

// Mandarin only: Cantonese voices (zh-HK / yue) would read pinyin-matched words
// with the wrong sounds, so they are never picked.
function score(v) {
  const lang = langOf(v);
  let s = 0;
  if (lang === "zh-cn") s += 20;
  else if (lang === "zh-tw") s += 10;
  if (/premium|enhanced|siri/i.test(v.name)) s += 5;
  return s;
}

function refreshVoices() {
  if (!synth) return;
  voices = synth.getVoices();
  const zh = voices.filter((v) => langOf(v).startsWith("zh") && !isCantonese(v));
  voice = zh.sort((a, b) => score(b) - score(a))[0] || null;
  for (const cb of listeners) cb();
}

if (synth) {
  refreshVoices();
  // Voices load asynchronously in Chrome / Android, so the list is often empty at first.
  synth.addEventListener?.("voiceschanged", refreshVoices);
}

// Calls cb whenever the voice list changes; returns an unsubscribe function.
export function onVoiceChange(cb) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

// Optimistic while the voice list is still empty (it may not have loaded yet);
// false only when the list is known and holds no Mandarin voice.
export const canSpeak = () => !!synth && (!!voice || voices.length === 0);

export function voiceStatus() {
  if (!synth) return { ok: false, text: "This browser has no speech support." };
  if (voice) return { ok: true, text: `Voice: ${voice.name} (${voice.lang})` };
  if (voices.length === 0) return { ok: true, text: "Looking for a Chinese voice…" };
  return {
    ok: false,
    text: "No Mandarin voice found. On iPhone: Settings › Accessibility › Spoken Content › Voices › Chinese.",
  };
}

// ── Speaking ──────────────────────────────────────────────────────────────────
// Browsers refuse to start speech until the page has seen a user gesture, and
// iOS Safari is strict about it. Speaking a silent utterance from the first tap
// unlocks later, programmatic speech (e.g. a question that auto-plays).
let unlocked = false;
export function unlockSpeech() {
  if (unlocked || !synth) return;
  unlocked = true;
  const u = new SpeechSynthesisUtterance(" ");
  u.volume = 0;
  synth.speak(u);
}
if (typeof document !== "undefined") {
  for (const type of ["touchend", "click", "keydown"]) {
    document.addEventListener(type, unlockSpeech, { once: true, capture: true });
  }
}

export function stopSpeaking() {
  if (synth) synth.cancel();
}

// Speak each text in order, replacing whatever is playing. Only the Chinese
// characters of each text are spoken; returns false when there was nothing to say.
export function speak(...texts) {
  const parts = texts.map(speakableText).filter(Boolean);
  if (!parts.length || !canSpeak()) return false;
  synth.cancel();
  for (const part of parts) {
    const u = new SpeechSynthesisUtterance(part);
    if (voice) u.voice = voice;
    u.lang = voice ? voice.lang : "zh-CN";
    u.rate = settings.rate;
    synth.speak(u);
  }
  return true;
}

// Speak a card's word, then its example sentence.
export const speakCard = (card) => speak(card.word, card.example);
