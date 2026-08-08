const $ = (s) => document.querySelector(s);
const list = $("#list");

let tasks = [];
let filter = "all";
let query = "";
let tag = "";
let selId = null;

// en-CA formats as YYYY-MM-DD in *local* time — toISOString would use UTC and
// mark things overdue on the wrong side of midnight.
const today = () => new Date().toLocaleDateString("en-CA");

// --- api -----------------------------------------------------------------
async function api(method, path = "", body = null) {
  const res = await fetch("/api/tasks" + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

let toastTimer;
function toast(msg, action) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.toggle("act", !!action);
  if (action) {
    const b = document.createElement("button");
    b.textContent = action.label;
    b.onclick = () => {
      el.classList.remove("show");
      action.run();
    };
    el.append(b);
  }
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), action ? 7000 : 3000);
}

// Actions apply the server's own response locally instead of re-fetching, so
// each one is a single round trip. Anything that fails re-syncs from scratch,
// so the UI still can't drift from the truth.
async function run(fn) {
  try {
    await fn();
  } catch (e) {
    toast(e.message);
    await load();
  }
}

// keeps local order identical to the server's ORDER BY done, position, id
function resort() {
  tasks.sort((a, b) => a.done - b.done || a.position - b.position || a.id - b.id);
}

let loaded = false;
async function load() {
  let fresh;
  try {
    fresh = await api("GET");
  } catch (e) {
    toast(e.message);
    return;
  }
  // the 60s poll usually finds nothing new — skip the DOM rebuild when so,
  // otherwise it interrupts scrolling and wipes a half-finished rename
  const changed = !loaded || JSON.stringify(fresh) !== JSON.stringify(tasks);
  tasks = fresh;
  loaded = true;
  if (changed) render();
  checkDue();
}

// --- tags: derived from the title, no extra table ------------------------
const TAG = /#([\p{L}\d_-]+)/gu;
const tagsOf = (t) => [...t.title.matchAll(TAG)].map((m) => m[1].toLowerCase());

// Dragging only makes sense when you can see every task in its real order.
const canDrag = () => filter === "all" && !query && !tag;

function visible() {
  // server already returns them ordered (done last, then manual position)
  return tasks
    .filter((t) => filter === "all" || (filter === "done") === !!t.done)
    .filter((t) => t.title.toLowerCase().includes(query))
    .filter((t) => !tag || tagsOf(t).includes(tag));
}

// --- render --------------------------------------------------------------
function row(t, now) {
  const li = document.createElement("li");
  li.className = `task p-${t.priority}` + (t.done ? " done" : "");
  li.dataset.id = t.id;
  li.draggable = canDrag();
  li.innerHTML = `
    <button class="check" aria-label="Toggle done">
      <svg viewBox="0 0 24 24"><path d="M4 12.5l5 5L20 6.5"/></svg>
    </button>
    <span class="title" contenteditable="plaintext-only" spellcheck="false"></span>
    <span class="chips"></span>
    <button class="del" aria-label="Delete">&times;</button>`;
  li.querySelector(".title").textContent = t.title;

  const chips = li.querySelector(".chips");
  const chip = (text, cls) => {
    const c = document.createElement("span");
    c.className = "chip " + cls;
    c.textContent = text;
    chips.append(c);
  };
  if (t.repeat !== "none") chip("↻ " + t.repeat, "rep");
  if (t.due) chip(t.due, !t.done && t.due < now ? "late" : "");
  return li;
}

function renderTags() {
  // localeCompare, not the default sort: tags allow any Unicode letter, and
  // the default orders by UTF-16 code unit rather than by alphabet
  const all = [...new Set(tasks.flatMap(tagsOf))].sort((a, b) => a.localeCompare(b));
  const bar = $("#tags");
  bar.replaceChildren(
    ...all.map((name) => {
      const b = document.createElement("button");
      b.textContent = "#" + name;
      b.dataset.tag = name;
      b.className = name === tag ? "on" : "";
      return b;
    })
  );
  bar.hidden = all.length === 0;
}

function paintSel() {
  for (const li of list.children) li.classList.toggle("sel", +li.dataset.id === selId);
  list.querySelector(".sel")?.scrollIntoView({ block: "nearest" });
}

function render() {
  const now = today();
  const rows = visible();
  list.replaceChildren(...rows.map((t) => row(t, now))); // ponytail: full re-render, fine under a few thousand tasks
  $("#empty").hidden = rows.length > 0;
  renderTags();
  paintSel();

  const left = tasks.filter((t) => !t.done).length;
  const late = tasks.filter((t) => !t.done && t.due && t.due < now).length;
  $("#summary").textContent =
    `${left} open · ${tasks.length - left} done` + (late ? ` · ${late} overdue` : "");
}

// --- add -----------------------------------------------------------------
$("#new").addEventListener("submit", async (e) => {
  e.preventDefault();
  const title = $("#title").value.trim();
  if (!title) return;
  const repeat = $("#repeat").value;
  const body = {
    title,
    priority: $("#priority").value,
    // a repeating task needs an anchor date; today is the sane default
    due: $("#due").value || (repeat !== "none" ? today() : null),
    repeat,
  };
  // clear straight away so typing the next one feels instant
  $("#title").value = "";
  $("#due").value = "";
  $("#repeat").value = "none";
  try {
    tasks.unshift(await api("POST", "", body));
    resort();
    render();
  } catch (err) {
    toast(err.message);
    $("#title").value = title; // hand the text back rather than losing it
  }
});

// --- filters -------------------------------------------------------------
$("#search").addEventListener("input", (e) => {
  query = e.target.value.trim().toLowerCase();
  render();
});

$("#filters").addEventListener("click", (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  filter = btn.dataset.filter;
  $("#filters .on")?.classList.remove("on");
  btn.classList.add("on");
  render();
});

$("#tags").addEventListener("click", (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  tag = tag === btn.dataset.tag ? "" : btn.dataset.tag; // click again to clear
  render();
});

$("#clear").addEventListener("click", () => {
  if (!tasks.some((t) => t.done)) return;
  run(async () => {
    await api("DELETE", "/done");
    tasks = tasks.filter((t) => !t.done);
    render();
  });
});

// --- row actions ---------------------------------------------------------
function restore(task) {
  // POST whitelists the fields it knows, so handing back the whole task restores it
  return run(async () => {
    tasks.unshift(await api("POST", "", task));
    resort();
    render();
  });
}

function toggle(id) {
  const t = tasks.find((x) => x.id === id);
  if (!t) return;
  const spawnsNext = t.repeat !== "none" && !t.done;
  run(async () => {
    const updated = await api("PATCH", `/${id}`, { done: !t.done });
    // finishing a repeating task creates one we don't know about yet
    if (spawnsNext) return load();
    Object.assign(t, updated);
    resort();
    render();
  });
}

function remove(id) {
  const gone = tasks.find((x) => x.id === id);
  if (!gone) return;
  run(async () => {
    await api("DELETE", `/${id}`);
    tasks = tasks.filter((x) => x.id !== id);
    render();
    toast("Task deleted", { label: "Undo", run: () => restore(gone) });
  });
}

list.addEventListener("click", (e) => {
  const li = e.target.closest(".task");
  if (!li) return;
  const id = +li.dataset.id;
  selId = id;
  if (e.target.closest(".check")) toggle(id);
  else if (e.target.closest(".del")) remove(id);
});

// inline rename: Enter commits, Esc reverts, blur commits
list.addEventListener("keydown", (e) => {
  if (!e.target.classList.contains("title")) return;
  if (e.key === "Enter") {
    e.preventDefault();
    e.target.blur();
  }
  if (e.key === "Escape") {
    e.target.dataset.cancel = "1";
    e.target.blur();
  }
});

list.addEventListener("focusout", (e) => {
  const el = e.target;
  if (!el.classList.contains("title")) return;
  const id = +el.closest(".task").dataset.id;
  const title = el.textContent.trim();
  const cancelled = el.dataset.cancel;
  delete el.dataset.cancel;
  const task = tasks.find((t) => t.id === id);
  if (cancelled || !title || !task || title === task.title) return render();
  run(async () => {
    Object.assign(task, await api("PATCH", `/${id}`, { title }));
    render();
  });
});

// --- drag to reorder (native HTML5, no library) --------------------------
let dragging = null;

list.addEventListener("dragstart", (e) => {
  dragging = e.target.closest(".task");
  if (!dragging) return;
  dragging.classList.add("drag");
  e.dataTransfer.effectAllowed = "move";
  e.dataTransfer.setData("text/plain", dragging.dataset.id); // Firefox needs this
});

list.addEventListener("dragover", (e) => {
  if (!dragging) return;
  e.preventDefault();
  const below = [...list.querySelectorAll(".task:not(.drag)")].find((li) => {
    const box = li.getBoundingClientRect();
    return e.clientY < box.top + box.height / 2;
  });
  list.insertBefore(dragging, below || null);
});

list.addEventListener("dragend", () => {
  if (!dragging) return;
  dragging.classList.remove("drag");
  dragging = null;
  const ids = [...list.children].map((li) => +li.dataset.id);
  run(async () => {
    await api("PATCH", "/order", { ids });
    // the rows are already where the user dropped them — just record it
    ids.forEach((id, i) => {
      const t = tasks.find((x) => x.id === id);
      if (t) t.position = i;
    });
    resort();
  });
});

// --- keyboard ------------------------------------------------------------
document.addEventListener("keydown", (e) => {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (/^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName) || e.target.isContentEditable) {
    if (e.key === "Escape") e.target.blur();
    return;
  }
  const rows = [...list.children];
  if (!rows.length && !"n/".includes(e.key)) return;
  const at = rows.findIndex((li) => +li.dataset.id === selId);

  const move = (step) => {
    const next = rows[at < 0 ? 0 : Math.max(0, Math.min(rows.length - 1, at + step))];
    if (next) {
      selId = +next.dataset.id;
      paintSel();
    }
  };

  switch (e.key) {
    case "n": e.preventDefault(); $("#title").focus(); break;
    case "/": e.preventDefault(); $("#search").focus(); break;
    case "j": e.preventDefault(); move(1); break;
    case "k": e.preventDefault(); move(-1); break;
    case "x": if (selId) { e.preventDefault(); toggle(selId); } break;
    case "e": if (selId) { e.preventDefault(); rows[at]?.querySelector(".title").focus(); } break;
    case "Delete":
    case "Backspace": if (selId) { e.preventDefault(); remove(selId); } break;
  }
});

// --- reminders -----------------------------------------------------------
// Native Notification API. Fires while the tab is open (background counts).
// The mailer in Backend/mailer.py covers the app-is-closed case.
const bell = $("#bell");
const notified = JSON.parse(localStorage.notified || "{}");

const remindersOn = () =>
  localStorage.reminders === "on" && window.Notification?.permission === "granted";

function paintBell() {
  bell.classList.toggle("on", remindersOn());
  bell.title = remindersOn() ? "Reminders on" : "Reminders off";
}

bell.addEventListener("click", async () => {
  if (remindersOn()) {
    localStorage.reminders = "off";
    return paintBell();
  }
  if (!("Notification" in window)) return toast("This browser can't do notifications");
  if ((await Notification.requestPermission()) !== "granted")
    return toast("Notifications are blocked in your browser settings");
  localStorage.reminders = "on";
  paintBell();
  checkDue();
});

function checkDue() {
  paintBell();
  if (!remindersOn()) return;
  const now = today();
  for (const t of tasks) {
    if (t.done || !t.due || t.due > now) continue;
    if (notified[t.id] === now) continue; // one nudge per task per day
    notified[t.id] = now;
    new Notification(t.due < now ? "⏰ Overdue" : "📌 Due today", {
      body: t.title,
      tag: `task-${t.id}`, // replaces its own older notification instead of stacking
    });
  }
  // forget finished/deleted tasks so they nudge again if reopened
  for (const id of Object.keys(notified))
    if (!tasks.some((t) => t.id === +id && !t.done)) delete notified[id];
  localStorage.notified = JSON.stringify(notified);
}

setInterval(load, 60_000); // re-sync + re-check, so a tab left open still nudges

await load();
