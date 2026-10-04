// ── API config ────────────────────────────────────────────────────────────────
const API_URL = "/api";

const TOKEN_KEY = "vocab_token";

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function apiFetch(path, options = {}) {
  const token = getToken();
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });
  if (res.status === 401) {
    clearToken();
    showLogin();
  }
  return res;
}

// ── Service worker registration ───────────────────────────────────────────────
if ("serviceWorker" in navigator) {
  // updateViaCache: "none" stops the browser HTTP-caching sw.js itself, so a
  // changed service worker is always detected instead of being stuck for up to 24h.
  navigator.serviceWorker.register("sw.js", { updateViaCache: "none" });

  // Reload once when a new service worker takes control, so a stale tab always
  // picks up the latest deploy without the user having to do it manually.
  let refreshing = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (refreshing) return;
    refreshing = true;
    window.location.reload();
  });
}

// ── Offline detection ─────────────────────────────────────────────────────────
const offlineBanner = document.getElementById("offline-banner");
function updateOnlineStatus() {
  offlineBanner.classList.toggle("hidden", navigator.onLine);
}
window.addEventListener("online", updateOnlineStatus);
window.addEventListener("offline", updateOnlineStatus);
updateOnlineStatus();

// ── Login ─────────────────────────────────────────────────────────────────────
const loginView = document.getElementById("view-login");
const loginForm = document.getElementById("login-form");
const loginError = document.getElementById("login-error");

function showLogin() {
  loginView.classList.remove("hidden");
  document.getElementById("login-password").value = "";
  loginError.classList.add("hidden");
}

function hideLogin() {
  loginView.classList.add("hidden");
}

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const password = document.getElementById("login-password").value;
  loginError.classList.add("hidden");

  const res = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });

  if (res.ok) {
    const { token } = await res.json();
    setToken(token);
    hideLogin();
    loadHome();
  } else {
    loginError.classList.remove("hidden");
    document.getElementById("login-password").select();
  }
});

// ── View switching ────────────────────────────────────────────────────────────
const views = {
  home: document.getElementById("view-home"),
  study: document.getElementById("view-study"),
  browse: document.getElementById("view-browse"),
};

function showView(name) {
  Object.values(views).forEach((v) => v.classList.add("hidden"));
  views[name].classList.remove("hidden");
}

// ── Shared helper ─────────────────────────────────────────────────────────────
function showErrorMsg(container, onlineMsg, offlineMsg) {
  const msg = document.createElement("p");
  msg.className = "error-msg";
  msg.textContent = navigator.onLine ? onlineMsg : offlineMsg;
  container.appendChild(msg);
}

// ── State ─────────────────────────────────────────────────────────────────────
let reverseMode = false;

// Each study direction has its own SM-2 schedule on the backend, so due lists
// and reviews are always scoped to the active mode.
const studyDirection = () => (reverseMode ? "reverse" : "forward");
let createdAfter = null; // ISO date string or null for "All time"
let currentSessionId = null; // number or null for "All sessions"

const HEISIG_KEY = "vocab_include_heisig";
let includeHeisig = true; // false hides Heisig hanzi cards from counts and study
try {
  includeHeisig = localStorage.getItem(HEISIG_KEY) !== "false";
} catch {
  // storage unavailable — keep default
}

function applyHeisigFilter(cards) {
  return includeHeisig ? cards : cards.filter((c) => !c.heisig);
}

// ── Home view ─────────────────────────────────────────────────────────────────
const homeEl = {
  heroCount: document.getElementById("hero-count"),
  heroSub: document.getElementById("hero-sub"),
  total: document.getElementById("total-words"),
  due: document.getElementById("due-words"),
  sectionCount: document.getElementById("section-count"),
  greeting: document.getElementById("greeting-title"),
  greetingSub: document.getElementById("greeting-sub"),
};

const PROVERBS = [
  ["好好学习，天天向上", "Good good study, day day up"],
  ["学无止境", "There is no end to learning"],
  ["活到老，学到老", "Live until old, learn until old"],
  ["千里之行，始于足下", "A journey of a thousand miles begins with a single step"],
  ["不积跬步，无以至千里", "Without small steps, you can't travel a thousand miles"],
  ["熟能生巧", "Practice makes perfect"],
  ["书山有路勤为径", "On the mountain of books, diligence is the path"],
  ["三人行，必有我师", "Among three people, one is sure to be my teacher"],
  ["学而时习之，不亦说乎", "To learn and practice what you learn — is that not a joy?"],
  ["只要功夫深，铁杵磨成针", "With enough effort, an iron rod grinds into a needle"],
];

function pickProverb() {
  const [zh, en] = PROVERBS[Math.floor(Math.random() * PROVERBS.length)];
  homeEl.greeting.textContent = zh;
  homeEl.greetingSub.textContent = en;
}

// null = unknown (loading or offline); otherwise the due-word count
function renderDue(count) {
  homeEl.due.textContent = count === null ? "—" : count;
  homeEl.heroCount.replaceChildren();
  if (count === null) {
    homeEl.heroCount.append("— ");
    const unit = document.createElement("span");
    unit.textContent = "words";
    homeEl.heroCount.append(unit);
    homeEl.heroSub.textContent = "ready for you";
  } else if (count === 0) {
    homeEl.heroCount.textContent = "All caught up";
    homeEl.heroSub.textContent = "No words due right now";
  } else {
    homeEl.heroCount.append(String(count), " ");
    const unit = document.createElement("span");
    unit.textContent = count === 1 ? "word" : "words";
    homeEl.heroCount.append(unit);
    homeEl.heroSub.textContent = "ready for you";
  }
}

async function refreshDueCount() {
  renderDue(null);
  try {
    const params = new URLSearchParams();
    if (createdAfter) params.set("created_after", createdAfter);
    if (currentSessionId !== null) params.set("session_id", String(currentSessionId));
    params.set("direction", studyDirection());
    const dueRes = await apiFetch(`/vocabulary/due?${params}`);
    if (dueRes.ok) {
      const due = await dueRes.json();
      renderDue(applyHeisigFilter(due).length);
    }
  } catch {
    // offline or server down — count stays at "—"
  }
}

async function loadHome() {
  showView("home");
  pickProverb();
  homeEl.total.textContent = "—";
  renderDue(null);
  document.getElementById("custom-date").max = new Date().toISOString().slice(0, 10);
  await Promise.all([
    loadSessions(),
    apiFetch("/vocabulary?limit=1")
      .then(async (res) => {
        if (res.ok) {
          const data = await res.json();
          homeEl.total.textContent = data.total;
        }
      })
      .catch(() => {}),
    refreshDueCount(),
  ]);
}

// ── Vocabulary sections ───────────────────────────────────────────────────────
// The backend calls these "sessions"; in the UI they are vocabulary sections.
// They are a flat list (id, name, date) with no hierarchy, so the picker shows
// one searchable list rather than inventing groups.
let sections = [];

async function loadSessions() {
  try {
    const res = await apiFetch("/sessions");
    if (!res.ok) return;
    sections = await res.json();
    // A previously selected section may have been deleted server-side.
    if (currentSessionId !== null && !sections.some((s) => s.id === currentSessionId)) {
      currentSessionId = null;
    }
    homeEl.sectionCount.textContent = sections.length;
    updateSectionTrigger();
  } catch {
    // offline — keep whatever sections we already have
  }
}

function currentSectionName() {
  const section = sections.find((s) => s.id === currentSessionId);
  return section ? section.name : "All sections";
}

function updateSectionTrigger() {
  const name = currentSectionName();
  const text = document.getElementById("section-trigger-text");
  text.textContent = name;
  document.getElementById("section-trigger").title = name;
}

// Menu in the header (settings/log out)
const menuBtn = document.getElementById("btn-menu");
const appMenu = document.getElementById("app-menu");

function setMenuOpen(open) {
  appMenu.classList.toggle("hidden", !open);
  menuBtn.setAttribute("aria-expanded", String(open));
  if (open) appMenu.querySelector("[role=menuitem]").focus();
}

menuBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  setMenuOpen(appMenu.classList.contains("hidden"));
});
document.addEventListener("click", (e) => {
  if (!appMenu.classList.contains("hidden") && !appMenu.contains(e.target)) setMenuOpen(false);
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !appMenu.classList.contains("hidden")) {
    setMenuOpen(false);
    menuBtn.focus();
  }
});

document.getElementById("btn-logout").addEventListener("click", () => {
  setMenuOpen(false);
  clearToken();
  showLogin();
  createdAfter = null;
  currentSessionId = null;
  sections = [];
  updateSectionTrigger();
  homeEl.sectionCount.textContent = "—";
  document.querySelectorAll(".time-btn").forEach((b) => {
    const isAll = b.dataset.days === "all";
    b.classList.toggle("active", isAll);
    b.setAttribute("aria-pressed", String(isAll));
  });
  document.getElementById("custom-date").classList.add("hidden");
  document.getElementById("custom-date").value = "";
});

// ── Study view ────────────────────────────────────────────────────────────────
document.getElementById("btn-study").addEventListener("click", () => loadStudy(reverseMode));
document.getElementById("btn-browse").addEventListener("click", loadBrowse);
document.getElementById("study-back").addEventListener("click", loadHome);
document.getElementById("browse-back").addEventListener("click", loadHome);
document.getElementById("study-done-btn").addEventListener("click", loadHome);
document.getElementById("study-home-btn").addEventListener("click", loadHome);
document.getElementById("study-again-btn").addEventListener("click", () => loadStudy(reverseMode));

let dueCards = [];
let currentCardIndex = 0;
let reviewedCount = 0;

// Fisher-Yates shuffle; used so cards from the same session (same next_review,
// added back-to-back) don't study in the order they were entered.
function shuffle(arr) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

// Cache all study-panel elements to avoid repeated getElementById calls
const studyEl = {
  loading: document.getElementById("study-loading"),
  empty: document.getElementById("study-empty"),
  done: document.getElementById("study-done"),
  area: document.getElementById("flashcard-area"),
  progress: document.getElementById("study-progress"),
  doneCount: document.getElementById("study-done-count"),
  main: document.getElementById("study-main"),
  lang: document.getElementById("card-lang"),
  word: document.getElementById("card-word"),
  definition: document.getElementById("card-definition"),
  example: document.getElementById("card-example"),
  heisig: document.getElementById("card-heisig"),
  pinyin: document.getElementById("card-pinyin"),
  translation: document.getElementById("card-translation"),
  ratings: document.getElementById("rating-buttons"),
  hint: document.querySelector(".card-hint"),
};

// reverse param allows callers to override the toggle state (e.g. study-again preserves mode)
async function loadStudy(reverse = false) {
  reverseMode = reverse;
  showView("study");
  // Clear any leftover error messages from a previous failed load
  studyEl.main.querySelectorAll(".error-msg").forEach((el) => el.remove());
  studyEl.loading.classList.remove("hidden");
  studyEl.empty.classList.add("hidden");
  studyEl.done.classList.add("hidden");
  studyEl.area.classList.add("hidden");
  studyEl.progress.textContent = "";

  try {
    const params = new URLSearchParams();
    if (createdAfter) params.set("created_after", createdAfter);
    if (currentSessionId !== null) params.set("session_id", String(currentSessionId));
    params.set("direction", studyDirection());
    const res = await apiFetch(`/vocabulary/due?${params}`);
    if (!res.ok) throw new Error("Failed to load due words");
    dueCards = shuffle(applyHeisigFilter(await res.json()));
  } catch {
    studyEl.loading.classList.add("hidden");
    showErrorMsg(
      studyEl.main,
      "Failed to load words. Please try again.",
      "You're offline. Please reconnect to study."
    );
    return;
  }

  studyEl.loading.classList.add("hidden");

  if (dueCards.length === 0) {
    studyEl.empty.classList.remove("hidden");
    return;
  }

  currentCardIndex = 0;
  reviewedCount = 0;
  showCard();
}

function showCard() {
  const card = dueCards[currentCardIndex];

  // Snap card to front instantly before updating content — prevents the back
  // face from briefly showing the new card's answer during the flip-back animation.
  const cardInner = flashcard.querySelector(".flashcard-card");
  cardInner.style.transition = "none";
  flashcard.classList.remove("flipped");
  void cardInner.offsetWidth; // force reflow so transition:none takes effect
  cardInner.style.transition = ""; // restore for user-initiated flips

  studyEl.progress.textContent = `${currentCardIndex + 1} / ${dueCards.length}`;
  studyEl.lang.textContent = card.language || "";

  renderCardFaces(card);

  flashcard.setAttribute(
    "aria-label",
    reverseMode ? "Tap to reveal word" : "Tap to reveal definition"
  );
  studyEl.hint.textContent = reverseMode ? "tap to reveal word" : "tap to reveal";

  studyEl.ratings.classList.add("hidden");
  studyEl.area.classList.remove("hidden");
}

// Fill both faces of the card for the current mode.
// Normal:  front word, back definition + example (+ Heisig pinyin block).
// Reverse: front pinyin only, back hanzi + English translation + example.
// Cards with no recoverable pinyin fall back to definition on the front and
// the word on the back.
// Split a card into its pinyin and English parts. New cards carry pinyin in a
// dedicated field (card.pinyin; Heisig cards also in heisig.pinyin). Legacy
// regular cards stored "pinyin | english" in the definition, so that is kept as
// a backup. Returns pinyin: "" when the card has no pinyin to show.
function splitPinyin(card) {
  const definition = card.definition || "";
  const stored = card.pinyin || (card.heisig && card.heisig.pinyin);
  if (stored) return { pinyin: stored, english: definition };
  const sep = definition.indexOf(" | ");
  if (sep === -1) return { pinyin: "", english: definition };
  return {
    pinyin: definition.slice(0, sep).trim(),
    english: definition.slice(sep + 3).trim(),
  };
}

function renderCardFaces(card) {
  const heisig = card.heisig;
  const toneClass = heisig ? `tone-${heisig.tone || 5}` : "";
  const { pinyin, english } = splitPinyin(card);
  const pinyinFront = reverseMode && !!pinyin;

  if (pinyinFront) {
    studyEl.word.textContent = pinyin;
    studyEl.word.className = `card-word ${toneClass}`.trim();
    studyEl.definition.textContent = card.word || "";
    studyEl.definition.className = `card-definition ${toneClass}`.trim();
    studyEl.translation.textContent = english;
  } else if (reverseMode) {
    studyEl.word.textContent = card.definition || "";
    studyEl.word.className = "card-word";
    studyEl.definition.textContent = card.word || "";
    studyEl.definition.className = `card-definition ${toneClass}`.trim();
    studyEl.translation.textContent = "";
  } else {
    studyEl.word.textContent = card.word || "";
    studyEl.word.className = `card-word ${toneClass}`.trim();
    studyEl.definition.textContent = card.definition || "";
    studyEl.definition.className = "card-definition";
    studyEl.translation.textContent = "";
  }
  studyEl.translation.classList.toggle("hidden", !pinyinFront);
  studyEl.example.textContent = card.example || "";

  // Pinyin is already on the front in reverse mode; don't repeat it on the back.
  renderHeisig(card, !pinyinFront);
}

// Populate or hide the Heisig block on the card back based on whether the
// card carries Heisig data. Additive: definition/example above it are untouched.
function renderHeisig(card, show = true) {
  const heisig = card.heisig;
  studyEl.heisig.classList.toggle("hidden", !heisig || !show);
  if (!heisig || !show) return;

  const tone = heisig.tone || 5;
  studyEl.pinyin.textContent = heisig.pinyin || "";
  studyEl.pinyin.className = `card-pinyin tone-${tone}`;
}

// Flip card on tap / keyboard
const flashcard = document.getElementById("flashcard");
flashcard.addEventListener("click", () => {
  if (window.getSelection().toString()) return;
  flipCard();
});
flashcard.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    flipCard();
  }
});
function isEditableElement(el) {
  if (!el) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || el.isContentEditable;
}

document.addEventListener("keydown", (e) => {
  if (
    e.key === " " &&
    document.activeElement !== flashcard &&
    !isEditableElement(document.activeElement) &&
    !views.study.classList.contains("hidden")
  ) {
    e.preventDefault();
    flipCard();
  }
});

function flipCard() {
  const isFlipped = flashcard.classList.toggle("flipped");
  studyEl.ratings.classList.toggle("hidden", !isFlipped);
}

// Rating buttons
studyEl.ratings.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-quality]");
  if (!btn) return;
  const quality = parseInt(btn.dataset.quality, 10);
  await submitReview(dueCards[currentCardIndex].id, quality);
  reviewedCount++;
  currentCardIndex++;
  if (currentCardIndex >= dueCards.length) {
    showStudyDone();
  } else {
    showCard();
  }
});

async function submitReview(id, quality) {
  try {
    await apiFetch(`/vocabulary/${id}/review?direction=${studyDirection()}`, {
      method: "PATCH",
      body: JSON.stringify({ quality }),
    });
  } catch {
    // best-effort; don't block UX on network failure
  }
}

function showStudyDone() {
  studyEl.area.classList.add("hidden");
  studyEl.done.classList.remove("hidden");
  studyEl.doneCount.textContent = `You reviewed ${reviewedCount} word${reviewedCount !== 1 ? "s" : ""}.`;
  studyEl.progress.textContent = "";
}

// ── Browse view ───────────────────────────────────────────────────────────────
const browseList = document.getElementById("browse-list");

// Event delegation: one listener handles all expand-toggle and delete interactions
browseList.addEventListener("click", async (e) => {
  const item = e.target.closest(".word-item");
  if (!item) return;

  if (e.target.closest(".btn-delete")) {
    const wordName = item.querySelector(".word-title").textContent;
    if (!confirm(`Delete "${wordName}"?`)) return;
    try {
      const res = await apiFetch(`/vocabulary/${item.dataset.id}`, { method: "DELETE" });
      if (res.ok) item.remove();
      else alert("Failed to delete word.");
    } catch {
      alert("Failed to delete word.");
    }
    return;
  }

  if (e.target.closest(".word-summary")) {
    item.classList.toggle("expanded");
  }
});

async function loadBrowse() {
  showView("browse");
  browseList.innerHTML = "";
  document.getElementById("browse-loading").classList.remove("hidden");
  document.getElementById("browse-empty").classList.add("hidden");

  let words, sessions;
  try {
    const [wordsRes, sessionsRes] = await Promise.all([
      apiFetch("/vocabulary"),
      apiFetch("/sessions"),
    ]);
    if (!wordsRes.ok) throw new Error();
    const data = await wordsRes.json();
    words = data.words;
    sessions = sessionsRes.ok ? await sessionsRes.json() : [];
  } catch {
    document.getElementById("browse-loading").classList.add("hidden");
    showErrorMsg(browseList, "Failed to load words.", "You're offline.");
    return;
  }

  document.getElementById("browse-loading").classList.add("hidden");

  if (!words || words.length === 0) {
    document.getElementById("browse-empty").classList.remove("hidden");
    return;
  }

  // Build session date lookup for headings
  const sessionDates = Object.fromEntries(sessions.map((s) => [s.name, s.date]));

  // Group by session_name
  const groups = {};
  for (const w of words) {
    const key = w.session_name || "misc";
    if (!groups[key]) groups[key] = [];
    groups[key].push(w);
  }

  // Sort: most recent session first (by date), misc always last
  const sortedEntries = Object.entries(groups).sort(([a], [b]) => {
    if (a === "misc") return 1;
    if (b === "misc") return -1;
    const dateA = sessionDates[a] || "0";
    const dateB = sessionDates[b] || "0";
    return dateB.localeCompare(dateA);
  });

  // Build into a DocumentFragment to batch all DOM writes into one reflow
  const frag = document.createDocumentFragment();
  for (const [sessionName, sessionWords] of sortedEntries) {
    const group = document.createElement("div");
    group.className = "lang-group";
    const heading = document.createElement("div");
    heading.className = "lang-heading";
    const sessionDate = sessionDates[sessionName];
    heading.textContent = sessionDate ? `${sessionName} — ${sessionDate}` : sessionName;
    group.appendChild(heading);
    for (const word of sessionWords) group.appendChild(buildWordItem(word));
    frag.appendChild(group);
  }
  browseList.appendChild(frag);
}

function buildWordItem(word) {
  const item = document.createElement("div");
  item.className = "word-item";
  item.dataset.id = word.id;

  // Use textContent throughout — no escaping needed, no XSS possible
  const wordTitle = document.createElement("div");
  wordTitle.className = "word-title";
  wordTitle.textContent = word.word;
  const wordDef = document.createElement("div");
  wordDef.className = "word-def";
  wordDef.textContent = word.definition;
  const wordText = document.createElement("div");
  wordText.className = "word-text";
  wordText.append(wordTitle, wordDef);

  const wordDue = document.createElement("span");
  wordDue.className = "word-due";
  wordDue.textContent = word.next_review;
  const expandIcon = document.createElement("span");
  expandIcon.className = "word-expand-icon";
  expandIcon.textContent = "▾";

  const summary = document.createElement("div");
  summary.className = "word-summary";
  summary.append(wordText, wordDue, expandIcon);

  const detail = document.createElement("div");
  detail.className = "word-detail";
  if (word.example) {
    const ex = document.createElement("div");
    ex.className = "word-example";
    ex.textContent = `"${word.example}"`;
    detail.appendChild(ex);
  }
  const delBtn = document.createElement("button");
  delBtn.className = "btn-delete";
  delBtn.textContent = "Delete";
  detail.appendChild(delBtn);

  item.append(summary, detail);
  return item;
}

// ── Mode toggle ───────────────────────────────────────────────────────────────
document.getElementById("mode-toggle").addEventListener("click", (e) => {
  const btn = e.target.closest(".seg-btn");
  if (!btn) return;
  reverseMode = btn.dataset.mode === "true";
  document.querySelectorAll("#mode-toggle .seg-btn").forEach((b) => {
    b.classList.toggle("active", b === btn);
    b.setAttribute("aria-pressed", String(b === btn));
  });
  refreshDueCount(); // due list differs per direction
});

// ── Time filter ───────────────────────────────────────────────────────────────
document.getElementById("time-filter").addEventListener("click", (e) => {
  const btn = e.target.closest(".time-btn");
  if (!btn) return;

  document.querySelectorAll(".time-btn").forEach((b) => {
    b.classList.toggle("active", b === btn);
    b.setAttribute("aria-pressed", String(b === btn));
  });

  const days = btn.dataset.days;
  const customInput = document.getElementById("custom-date");

  if (days === "custom") {
    customInput.classList.remove("hidden");
    return; // createdAfter unchanged until user picks a date
  }

  customInput.classList.add("hidden");
  customInput.value = "";

  if (days === "all") {
    createdAfter = null;
  } else {
    const d = new Date();
    d.setDate(d.getDate() - parseInt(days, 10));
    createdAfter = d.toISOString().slice(0, 10);
  }

  refreshDueCount();
});

document.getElementById("custom-date").addEventListener("change", (e) => {
  createdAfter = e.target.value || null;
  refreshDueCount();
});

// ── Section picker (bottom sheet on mobile, modal on desktop) ────────────────
const pickerEl = {
  backdrop: document.getElementById("section-picker-backdrop"),
  dialog: document.getElementById("section-picker"),
  search: document.getElementById("section-search"),
  list: document.getElementById("section-list"),
  empty: document.getElementById("section-empty"),
  trigger: document.getElementById("section-trigger"),
};
let pickerOptions = []; // [{ id: number | null, name, date? }] currently shown
let pickerActive = 0; // keyboard-highlighted index into pickerOptions

function renderSectionList() {
  const query = pickerEl.search.value.trim().toLowerCase();
  const all = { id: null, name: "All sections" };
  const matches = sections.filter((s) => s.name.toLowerCase().includes(query));
  pickerOptions = !query || all.name.toLowerCase().includes(query) ? [all, ...matches] : matches;

  const frag = document.createDocumentFragment();
  pickerOptions.forEach((opt, i) => {
    const li = document.createElement("li");
    li.id = `section-opt-${i}`;
    li.className = "picker-option";
    li.setAttribute("role", "option");
    li.dataset.index = String(i);
    const selected = opt.id === currentSessionId;
    li.setAttribute("aria-selected", String(selected));

    const check = document.createElement("span");
    check.className = "picker-check";
    check.setAttribute("aria-hidden", "true");
    check.textContent = selected ? "✓" : "";
    const name = document.createElement("span");
    name.className = "picker-name";
    name.textContent = opt.name;
    name.title = opt.name; // full name on hover when truncated
    li.append(check, name);
    if (opt.date) {
      const date = document.createElement("span");
      date.className = "picker-date";
      date.textContent = opt.date;
      li.append(date);
    }
    frag.appendChild(li);
  });
  pickerEl.list.replaceChildren(frag);
  pickerEl.empty.classList.toggle("hidden", pickerOptions.length > 0);
  setPickerActive(
    Math.max(
      0,
      pickerOptions.findIndex((o) => o.id === currentSessionId)
    ),
    false
  );
}

function setPickerActive(index, scroll = true) {
  const items = pickerEl.list.children;
  if (items.length === 0) {
    pickerEl.search.removeAttribute("aria-activedescendant");
    return;
  }
  pickerActive = Math.min(Math.max(index, 0), items.length - 1);
  for (const el of items) el.classList.remove("kbd-active");
  const el = items[pickerActive];
  el.classList.add("kbd-active");
  pickerEl.search.setAttribute("aria-activedescendant", el.id);
  if (scroll) el.scrollIntoView({ block: "nearest" });
}

function openSectionPicker() {
  pickerEl.search.value = "";
  renderSectionList();
  pickerEl.backdrop.setAttribute("aria-hidden", "false");
  pickerEl.backdrop.classList.add("open");
  const selected = pickerEl.list.children[pickerActive];
  if (selected) selected.scrollIntoView({ block: "center" });
  // Only auto-focus the search box where there is a hardware keyboard; on touch
  // devices it would pop the on-screen keyboard over the list.
  if (window.matchMedia("(hover: hover) and (pointer: fine)").matches) pickerEl.search.focus();
  else pickerEl.dialog.focus();
}

function closeSectionPicker() {
  pickerEl.backdrop.classList.remove("open");
  pickerEl.backdrop.setAttribute("aria-hidden", "true");
  pickerEl.trigger.focus();
}

function selectSection(index) {
  const opt = pickerOptions[index];
  if (!opt) return;
  const changed = opt.id !== currentSessionId;
  currentSessionId = opt.id;
  updateSectionTrigger();
  closeSectionPicker();
  if (changed) refreshDueCount();
}

pickerEl.trigger.addEventListener("click", openSectionPicker);
document.getElementById("section-picker-close").addEventListener("click", closeSectionPicker);
pickerEl.backdrop.addEventListener("click", (e) => {
  if (e.target === pickerEl.backdrop) closeSectionPicker();
});
pickerEl.search.addEventListener("input", renderSectionList);
pickerEl.list.addEventListener("click", (e) => {
  const li = e.target.closest(".picker-option");
  if (li) selectSection(Number(li.dataset.index));
});
pickerEl.dialog.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    e.preventDefault();
    closeSectionPicker();
  } else if (e.key === "ArrowDown") {
    e.preventDefault();
    setPickerActive(pickerActive + 1);
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    setPickerActive(pickerActive - 1);
  } else if (e.key === "Enter" && e.target === pickerEl.search) {
    e.preventDefault();
    selectSection(pickerActive);
  } else if (e.key === "Tab") {
    // Keep focus inside the modal dialog
    const focusable = [document.getElementById("section-picker-close"), pickerEl.search];
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (
      e.shiftKey &&
      (document.activeElement === first || document.activeElement === pickerEl.dialog)
    ) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }
});

// ── Heisig setting ────────────────────────────────────────────────────────────
const heisigSwitch = document.getElementById("heisig-toggle");

function syncHeisigToggle() {
  heisigSwitch.setAttribute("aria-checked", String(includeHeisig));
}

heisigSwitch.addEventListener("click", () => {
  includeHeisig = !includeHeisig;
  try {
    localStorage.setItem(HEISIG_KEY, String(includeHeisig));
  } catch {
    // storage unavailable — preference lasts for this page load only
  }
  syncHeisigToggle();
  refreshDueCount();
});
syncHeisigToggle();

// ── Init ──────────────────────────────────────────────────────────────────────
if (getToken()) {
  hideLogin();
  loadHome();
} else {
  showLogin();
}

// ── Edit card sheet ───────────────────────────────────────────────────────────
const editBackdrop = document.getElementById("edit-sheet-backdrop");
const editWordInput = document.getElementById("edit-word");
const editDefInput = document.getElementById("edit-definition");
const editExInput = document.getElementById("edit-example");
const editError = document.getElementById("edit-error");
const editSaveBtn = document.getElementById("edit-save");
const editDeleteBtn = document.getElementById("edit-delete");

function onViewportResize() {
  const vv = window.visualViewport;
  editBackdrop.style.height = `${vv.height}px`;
  editBackdrop.style.top = `${vv.offsetTop}px`;
}

function openEditSheet() {
  const card = dueCards[currentCardIndex];
  editWordInput.value = card.word || "";
  editDefInput.value = card.definition || "";
  editExInput.value = card.example || "";
  editError.classList.add("hidden");
  editBackdrop.setAttribute("aria-hidden", "false");
  editBackdrop.classList.add("open");
  window.visualViewport?.addEventListener("resize", onViewportResize);
  editWordInput.focus();
}

function closeEditSheet() {
  window.visualViewport?.removeEventListener("resize", onViewportResize);
  editBackdrop.style.height = "";
  editBackdrop.style.top = "";
  editBackdrop.classList.remove("open");
  editBackdrop.setAttribute("aria-hidden", "true");
  document.getElementById("btn-edit-card").focus();
}

async function saveEdit() {
  const card = dueCards[currentCardIndex];
  const word = editWordInput.value.trim();
  const definition = editDefInput.value.trim();
  const example = editExInput.value.trim() || null;

  if (!word || !definition) {
    editError.textContent = "Word and definition are required.";
    editError.classList.remove("hidden");
    return;
  }

  editSaveBtn.disabled = true;
  editSaveBtn.textContent = "Saving…";
  editError.classList.add("hidden");

  try {
    const res = await apiFetch(`/vocabulary/${card.id}`, {
      method: "PATCH",
      body: JSON.stringify({ word, definition, example }),
    });

    if (res.ok) {
      const updated = await res.json();
      Object.assign(dueCards[currentCardIndex], updated);
      // Refresh displayed text in-place — card stays on back face, ratings stay visible
      renderCardFaces(dueCards[currentCardIndex]);
      closeEditSheet();
    } else if (res.status === 409) {
      editError.textContent = "A word with this name already exists.";
      editError.classList.remove("hidden");
    } else {
      editError.textContent = "Failed to save. Try again.";
      editError.classList.remove("hidden");
    }
  } catch {
    editError.textContent = "Failed to save. Try again.";
    editError.classList.remove("hidden");
  } finally {
    editSaveBtn.disabled = false;
    editSaveBtn.textContent = "Save";
  }
}

async function deleteEditCard() {
  const card = dueCards[currentCardIndex];
  if (!confirm(`Delete "${card.word}"?`)) return;

  editDeleteBtn.disabled = true;
  editDeleteBtn.textContent = "Deleting…";

  try {
    const res = await apiFetch(`/vocabulary/${card.id}`, { method: "DELETE" });
    if (res.ok) {
      dueCards.splice(currentCardIndex, 1);
      closeEditSheet();
      if (currentCardIndex >= dueCards.length) {
        showStudyDone();
      } else {
        showCard();
      }
    } else {
      editError.textContent = "Failed to delete card.";
      editError.classList.remove("hidden");
    }
  } catch {
    editError.textContent = "Failed to delete card.";
    editError.classList.remove("hidden");
  } finally {
    editDeleteBtn.disabled = false;
    editDeleteBtn.textContent = "Delete card";
  }
}

document.getElementById("btn-edit-card").addEventListener("click", openEditSheet);
document.getElementById("edit-cancel").addEventListener("click", closeEditSheet);
editSaveBtn.addEventListener("click", saveEdit);
editDeleteBtn.addEventListener("click", deleteEditCard);
editBackdrop.addEventListener("click", (e) => {
  if (e.target === editBackdrop) closeEditSheet();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && editBackdrop.classList.contains("open")) closeEditSheet();
});
