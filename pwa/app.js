// ── API config ────────────────────────────────────────────────────────────────
const API_URL = "https://backend-production-c18e.up.railway.app";

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
  home:   document.getElementById("view-home"),
  study:  document.getElementById("view-study"),
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

// ── Home view ─────────────────────────────────────────────────────────────────
async function loadHome() {
  showView("home");
  document.getElementById("total-words").textContent = "—";
  document.getElementById("due-words").textContent = "—";
  try {
    const [allRes, dueRes] = await Promise.all([
      apiFetch("/vocabulary?limit=1"),
      apiFetch("/vocabulary/due"),
    ]);
    if (allRes.ok) {
      const data = await allRes.json();
      document.getElementById("total-words").textContent = data.total;
    }
    if (dueRes.ok) {
      const due = await dueRes.json();
      document.getElementById("due-words").textContent = due.length;
    }
  } catch {
    // offline or server down — stats stay at "—"
  }
}

document.getElementById("btn-logout").addEventListener("click", () => {
  clearToken();
  showLogin();
});
document.getElementById("btn-study").addEventListener("click", loadStudy);
document.getElementById("btn-browse").addEventListener("click", loadBrowse);
document.getElementById("study-back").addEventListener("click", loadHome);
document.getElementById("browse-back").addEventListener("click", loadHome);
document.getElementById("study-done-btn").addEventListener("click", loadHome);
document.getElementById("study-home-btn").addEventListener("click", loadHome);
document.getElementById("study-again-btn").addEventListener("click", loadStudy);

// ── Study view ────────────────────────────────────────────────────────────────
let dueCards = [];
let currentCardIndex = 0;
let reviewedCount = 0;

// Cache all study-panel elements to avoid repeated getElementById calls
const studyEl = {
  loading:    document.getElementById("study-loading"),
  empty:      document.getElementById("study-empty"),
  done:       document.getElementById("study-done"),
  area:       document.getElementById("flashcard-area"),
  progress:   document.getElementById("study-progress"),
  doneCount:  document.getElementById("study-done-count"),
  main:       document.getElementById("study-main"),
  lang:       document.getElementById("card-lang"),
  word:       document.getElementById("card-word"),
  definition: document.getElementById("card-definition"),
  example:    document.getElementById("card-example"),
  ratings:    document.getElementById("rating-buttons"),
};

async function loadStudy() {
  showView("study");
  // Clear any leftover error messages from a previous failed load
  studyEl.main.querySelectorAll(".error-msg").forEach((el) => el.remove());
  studyEl.loading.classList.remove("hidden");
  studyEl.empty.classList.add("hidden");
  studyEl.done.classList.add("hidden");
  studyEl.area.classList.add("hidden");
  studyEl.progress.textContent = "";

  try {
    const res = await apiFetch("/vocabulary/due");
    if (!res.ok) throw new Error("Failed to load due words");
    dueCards = await res.json();
  } catch {
    studyEl.loading.classList.add("hidden");
    showErrorMsg(
      studyEl.main,
      "Failed to load words. Please try again.",
      "You're offline. Please reconnect to study.",
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
  studyEl.progress.textContent = `${currentCardIndex + 1} / ${dueCards.length}`;
  studyEl.lang.textContent = card.language || "";
  studyEl.word.textContent = card.word;
  studyEl.definition.textContent = card.definition;
  studyEl.example.textContent = card.example || "";

  flashcard.classList.remove("flipped");
  studyEl.ratings.classList.add("hidden");
  studyEl.area.classList.remove("hidden");
}

// Flip card on tap / keyboard
const flashcard = document.getElementById("flashcard");
flashcard.addEventListener("click", flipCard);
flashcard.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); flipCard(); }
});

function flipCard() {
  flashcard.classList.add("flipped");
  studyEl.ratings.classList.remove("hidden");
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
  studyEl.doneCount.textContent =
    `You reviewed ${reviewedCount} word${reviewedCount !== 1 ? "s" : ""}.`;
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

  let words;
  try {
    const res = await apiFetch("/vocabulary");
    if (!res.ok) throw new Error();
    const data = await res.json();
    words = data.words;
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

  // Group by language
  const groups = {};
  for (const w of words) {
    const lang = w.language || "unknown";
    if (!groups[lang]) groups[lang] = [];
    groups[lang].push(w);
  }

  // Build into a DocumentFragment to batch all DOM writes into one reflow
  const frag = document.createDocumentFragment();
  for (const [lang, langWords] of Object.entries(groups).sort()) {
    const group = document.createElement("div");
    group.className = "lang-group";
    const heading = document.createElement("div");
    heading.className = "lang-heading";
    heading.textContent = lang;
    group.appendChild(heading);
    for (const word of langWords) group.appendChild(buildWordItem(word));
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

// ── Init ──────────────────────────────────────────────────────────────────────
if (getToken()) {
  hideLogin();
  loadHome();
} else {
  showLogin();
}
