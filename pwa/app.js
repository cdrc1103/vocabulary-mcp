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
  navigator.serviceWorker.register("sw.js");
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
let createdAfter = null; // ISO date string or null for "All time"
let currentSessionId = null; // number or null for "All sessions"

// ── Home view ─────────────────────────────────────────────────────────────────
async function refreshDueCount() {
  document.getElementById("due-words").textContent = "—";
  try {
    const params = new URLSearchParams();
    if (createdAfter) params.set("created_after", createdAfter);
    if (currentSessionId !== null) params.set("session_id", String(currentSessionId));
    const path = params.size ? `/vocabulary/due?${params}` : "/vocabulary/due";
    const dueRes = await apiFetch(path);
    if (dueRes.ok) {
      const due = await dueRes.json();
      document.getElementById("due-words").textContent = due.length;
    }
  } catch {
    // offline or server down — count stays at "—"
  }
}

async function loadHome() {
  showView("home");
  document.getElementById("total-words").textContent = "—";
  document.getElementById("due-words").textContent = "—";
  document.getElementById("custom-date").max = new Date().toISOString().slice(0, 10);
  await Promise.all([
    loadSessions(),
    apiFetch("/vocabulary?limit=1")
      .then(async (res) => {
        if (res.ok) {
          const data = await res.json();
          document.getElementById("total-words").textContent = data.total;
        }
      })
      .catch(() => {}),
    refreshDueCount(),
  ]);
}

async function loadSessions() {
  const container = document.getElementById("session-filter");
  container.innerHTML = "";
  try {
    const res = await apiFetch("/sessions");
    if (!res.ok) return;
    const sessions = await res.json();

    const allBtn = document.createElement("button");
    allBtn.className = "session-btn" + (currentSessionId === null ? " active" : "");
    allBtn.dataset.sessionId = "all";
    allBtn.textContent = "All";
    allBtn.setAttribute("aria-pressed", String(currentSessionId === null));
    container.appendChild(allBtn);

    for (const s of sessions) {
      const btn = document.createElement("button");
      const isActive = currentSessionId === s.id;
      btn.className = "session-btn" + (isActive ? " active" : "");
      btn.dataset.sessionId = String(s.id);
      btn.textContent = s.name;
      btn.setAttribute("aria-pressed", String(isActive));
      container.appendChild(btn);
    }
  } catch {
    // offline — session filter stays empty
  }
}

document.getElementById("btn-logout").addEventListener("click", () => {
  clearToken();
  showLogin();
  createdAfter = null;
  currentSessionId = null;
  document.querySelectorAll(".time-btn").forEach((b) => {
    const isAll = b.dataset.days === "all";
    b.classList.toggle("active", isAll);
    b.setAttribute("aria-pressed", String(isAll));
  });
  document.getElementById("custom-date").classList.add("hidden");
  document.getElementById("custom-date").value = "";
  document.getElementById("session-filter").innerHTML = "";
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
  story: document.getElementById("card-story"),
  primitives: document.getElementById("card-primitives"),
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
    const duePath = params.size ? `/vocabulary/due?${params}` : "/vocabulary/due";
    const res = await apiFetch(duePath);
    if (!res.ok) throw new Error("Failed to load due words");
    dueCards = await res.json();
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

  if (reverseMode) {
    // Front: definition. Back: word + example.
    studyEl.word.textContent = card.definition || "";
    studyEl.definition.textContent = card.word || "";
  } else {
    // Front: word. Back: definition + example.
    studyEl.word.textContent = card.word || "";
    studyEl.definition.textContent = card.definition || "";
  }
  studyEl.example.textContent = card.example || "";

  flashcard.setAttribute(
    "aria-label",
    reverseMode ? "Tap to reveal word" : "Tap to reveal definition"
  );
  studyEl.hint.textContent = reverseMode ? "tap to reveal word" : "tap to reveal";

  renderHeisig(card);
  studyEl.ratings.classList.add("hidden");
  studyEl.area.classList.remove("hidden");
}

// Populate or hide the Heisig block on the card back based on whether the
// card carries Heisig data. Additive: definition/example above it are untouched.
function renderHeisig(card) {
  const heisig = card.heisig;
  studyEl.heisig.classList.toggle("hidden", !heisig);
  if (!heisig) return;

  const tone = heisig.tone || 5;
  studyEl.pinyin.textContent = heisig.pinyin || "";
  studyEl.pinyin.className = `card-pinyin tone-${tone}`;

  studyEl.story.textContent = heisig.story || "";

  const prims = heisig.primitives || [];
  studyEl.primitives.textContent = prims.map((p) => `${p.component} = ${p.keyword}`).join(" · ");
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
    await apiFetch(`/vocabulary/${id}/review`, {
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
  const btn = e.target.closest(".mode-btn");
  if (!btn) return;
  reverseMode = btn.dataset.mode === "true";
  document.querySelectorAll(".mode-btn").forEach((b) => {
    b.classList.toggle("active", b === btn);
    b.setAttribute("aria-pressed", String(b === btn));
  });
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

document.getElementById("session-filter").addEventListener("click", (e) => {
  const btn = e.target.closest(".session-btn");
  if (!btn) return;

  document.querySelectorAll(".session-btn").forEach((b) => {
    b.classList.toggle("active", b === btn);
    b.setAttribute("aria-pressed", String(b === btn));
  });

  const sid = btn.dataset.sessionId;
  currentSessionId = sid === "all" ? null : parseInt(sid, 10);
  refreshDueCount();
});

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
      if (reverseMode) {
        studyEl.word.textContent = updated.definition || "";
        studyEl.definition.textContent = updated.word || "";
      } else {
        studyEl.word.textContent = updated.word || "";
        studyEl.definition.textContent = updated.definition || "";
      }
      studyEl.example.textContent = updated.example || "";
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

document.getElementById("btn-edit-card").addEventListener("click", openEditSheet);
document.getElementById("edit-cancel").addEventListener("click", closeEditSheet);
editSaveBtn.addEventListener("click", saveEdit);
editBackdrop.addEventListener("click", (e) => {
  if (e.target === editBackdrop) closeEditSheet();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && editBackdrop.classList.contains("open")) closeEditSheet();
});
