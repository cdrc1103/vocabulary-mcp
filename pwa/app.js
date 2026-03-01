// ── API config ────────────────────────────────────────────────────────────────
const API_URL = "https://your-app.railway.app";
const API_KEY = "your-api-key-here";

async function apiFetch(path, options = {}) {
  return fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": API_KEY,
      ...(options.headers || {}),
    },
  });
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

async function loadStudy() {
  showView("study");
  document.getElementById("study-loading").classList.remove("hidden");
  document.getElementById("study-empty").classList.add("hidden");
  document.getElementById("study-done").classList.add("hidden");
  document.getElementById("flashcard-area").classList.add("hidden");
  document.getElementById("study-progress").textContent = "";

  try {
    const res = await apiFetch("/vocabulary/due");
    if (!res.ok) throw new Error("Failed to load due words");
    dueCards = await res.json();
  } catch {
    document.getElementById("study-loading").classList.add("hidden");
    const msg = document.createElement("p");
    msg.className = "error-msg";
    msg.textContent = navigator.onLine
      ? "Failed to load words. Please try again."
      : "You're offline. Please reconnect to study.";
    document.getElementById("study-main").appendChild(msg);
    return;
  }

  document.getElementById("study-loading").classList.add("hidden");

  if (dueCards.length === 0) {
    document.getElementById("study-empty").classList.remove("hidden");
    return;
  }

  currentCardIndex = 0;
  reviewedCount = 0;
  showCard();
}

function showCard() {
  const card = dueCards[currentCardIndex];
  document.getElementById("study-progress").textContent =
    `${currentCardIndex + 1} / ${dueCards.length}`;
  document.getElementById("card-lang").textContent = card.language || "";
  document.getElementById("card-word").textContent = card.word;
  document.getElementById("card-definition").textContent = card.definition;
  document.getElementById("card-example").textContent = card.example || "";

  const flashcard = document.getElementById("flashcard");
  flashcard.classList.remove("flipped");
  document.getElementById("rating-buttons").classList.add("hidden");
  document.getElementById("flashcard-area").classList.remove("hidden");
}

// Flip card on tap / keyboard
const flashcard = document.getElementById("flashcard");
flashcard.addEventListener("click", flipCard);
flashcard.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); flipCard(); }
});

function flipCard() {
  flashcard.classList.add("flipped");
  document.getElementById("rating-buttons").classList.remove("hidden");
}

// Rating buttons
document.getElementById("rating-buttons").addEventListener("click", async (e) => {
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
  document.getElementById("flashcard-area").classList.add("hidden");
  document.getElementById("study-done").classList.remove("hidden");
  document.getElementById("study-done-count").textContent =
    `You reviewed ${reviewedCount} word${reviewedCount !== 1 ? "s" : ""}.`;
  document.getElementById("study-progress").textContent = "";
}

// ── Browse view ───────────────────────────────────────────────────────────────
async function loadBrowse() {
  showView("browse");
  const list = document.getElementById("browse-list");
  list.innerHTML = "";
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
    const msg = document.createElement("p");
    msg.className = "error-msg";
    msg.textContent = navigator.onLine ? "Failed to load words." : "You're offline.";
    list.appendChild(msg);
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

  for (const [lang, langWords] of Object.entries(groups).sort()) {
    const group = document.createElement("div");
    group.className = "lang-group";
    const heading = document.createElement("div");
    heading.className = "lang-heading";
    heading.textContent = lang;
    group.appendChild(heading);
    for (const word of langWords) group.appendChild(buildWordItem(word));
    list.appendChild(group);
  }
}

function buildWordItem(word) {
  const item = document.createElement("div");
  item.className = "word-item";
  item.dataset.id = word.id;

  const summary = document.createElement("div");
  summary.className = "word-summary";
  summary.innerHTML = `
    <div class="word-text">
      <div class="word-title">${escHtml(word.word)}</div>
      <div class="word-def">${escHtml(word.definition)}</div>
    </div>
    <span class="word-due">${word.next_review}</span>
    <span class="word-expand-icon">▾</span>
  `;
  summary.addEventListener("click", () => item.classList.toggle("expanded"));

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
  delBtn.addEventListener("click", async (e) => {
    e.stopPropagation();
    if (!confirm(`Delete "${word.word}"?`)) return;
    try {
      const res = await apiFetch(`/vocabulary/${word.id}`, { method: "DELETE" });
      if (res.ok) {
        item.remove();
      } else {
        alert("Failed to delete word.");
      }
    } catch {
      alert("Failed to delete word.");
    }
  });
  detail.appendChild(delBtn);

  item.appendChild(summary);
  item.appendChild(detail);
  return item;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Init ──────────────────────────────────────────────────────────────────────
loadHome();
