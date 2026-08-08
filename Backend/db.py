"""SQLite storage + validation. No ORM, no dependencies."""
import calendar
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

DB = Path(os.environ.get("TODO_DB") or Path(__file__).with_name("todo.db"))

PRIORITIES = ("low", "medium", "high")
REPEATS = ("none", "daily", "weekly", "monthly")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  title    TEXT    NOT NULL,
  priority TEXT    NOT NULL DEFAULT 'medium',
  due      TEXT,
  done     INTEGER NOT NULL DEFAULT 0,
  position INTEGER NOT NULL DEFAULT 0,
  repeat   TEXT    NOT NULL DEFAULT 'none',
  created  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


@contextmanager
def conn():
    # ponytail: one connection per request. Swap for a pool only if this
    # ever serves more than one person on a laptop.
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    try:
        with c:  # commits on success, rolls back on exception
            yield c
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript(SCHEMA)
        # bring databases made by an older version up to date
        have = {r["name"] for r in c.execute("PRAGMA table_info(tasks)")}
        for col, decl in (("position", "INTEGER NOT NULL DEFAULT 0"),
                          ("repeat", "TEXT NOT NULL DEFAULT 'none'")):
            if col not in have:
                c.execute(f"ALTER TABLE tasks ADD COLUMN {col} {decl}")


def _clean(data, partial=False):
    """Whitelist + validate incoming fields. Raises ValueError on bad input."""
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    out = {}
    if "title" in data or not partial:
        title = str(data.get("title", "")).strip()
        if not 1 <= len(title) <= 200:
            raise ValueError("title must be 1-200 characters")
        out["title"] = title
    if "priority" in data:
        if data["priority"] not in PRIORITIES:
            raise ValueError("priority must be low, medium or high")
        out["priority"] = data["priority"]
    if "repeat" in data:
        if data["repeat"] not in REPEATS:
            raise ValueError("repeat must be none, daily, weekly or monthly")
        out["repeat"] = data["repeat"]
    if "due" in data:
        due = data["due"] or None
        if due is not None and not DATE.match(str(due)):
            raise ValueError("due must look like YYYY-MM-DD")
        out["due"] = due
    if "done" in data:
        out["done"] = int(bool(data["done"]))
    if "position" in data:
        try:
            out["position"] = int(data["position"])
        except (TypeError, ValueError):
            raise ValueError("position must be a whole number")
    return out


def _one(c, tid):
    row = c.execute("SELECT * FROM tasks WHERE id = ?", (tid,)).fetchone()
    if row is None:
        raise KeyError(tid)
    return dict(row)


def _next_due(due, repeat):
    d = date.fromisoformat(due)
    if repeat == "daily":
        return (d + timedelta(days=1)).isoformat()
    if repeat == "weekly":
        return (d + timedelta(days=7)).isoformat()
    # monthly: same day next month, clamped so 31 Jan -> 28/29 Feb
    year, month = d.year + d.month // 12, d.month % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1])).isoformat()


# --- tasks ---------------------------------------------------------------
def all_tasks():
    with conn() as c:
        rows = c.execute("SELECT * FROM tasks ORDER BY done, position, id").fetchall()
        return [dict(r) for r in rows]


def add(data):
    f = _clean(data)
    if f.get("repeat", "none") != "none" and not f.get("due"):
        raise ValueError("a repeating task needs a due date")
    with conn() as c:
        pos = f.get("position")
        if pos is None:  # new tasks land on top
            pos = c.execute("SELECT COALESCE(MIN(position), 0) - 1 FROM tasks").fetchone()[0]
        cur = c.execute(
            "INSERT INTO tasks (title, priority, due, done, position, repeat)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (f["title"], f.get("priority", "medium"), f.get("due"),
             f.get("done", 0), pos, f.get("repeat", "none")),
        )
        return _one(c, cur.lastrowid)


def update(tid, data):
    f = _clean(data, partial=True)
    if not f:
        raise ValueError("nothing to update")
    # keys come from _clean's whitelist, so this interpolation is safe
    sets = ", ".join(f"{k} = ?" for k in f)
    with conn() as c:
        before = _one(c, tid)  # 404 before we touch anything
        c.execute(f"UPDATE tasks SET {sets} WHERE id = ?", (*f.values(), tid))
        after = _one(c, tid)
        if after["repeat"] != "none" and not after["due"]:
            raise ValueError("a repeating task needs a due date")  # rolls back

        # ticking off a repeating task spawns the next occurrence
        if not before["done"] and after["done"] and after["repeat"] != "none":
            c.execute(
                "INSERT INTO tasks (title, priority, due, position, repeat)"
                " VALUES (?, ?, ?, ?, ?)",
                (after["title"], after["priority"], _next_due(after["due"], after["repeat"]),
                 after["position"], after["repeat"]),
            )
            # the recurrence moved to the new task; this one is now a plain record
            c.execute("UPDATE tasks SET repeat = 'none' WHERE id = ?", (tid,))
            after = _one(c, tid)
        return after


def delete(tid):
    with conn() as c:
        cur = c.execute("DELETE FROM tasks WHERE id = ?", (tid,))
        if cur.rowcount == 0:
            raise KeyError(tid)
        return {"deleted": tid}


def clear_done():
    with conn() as c:
        cur = c.execute("DELETE FROM tasks WHERE done = 1")
        return {"deleted": cur.rowcount}


def reorder(data):
    ids = data.get("ids") if isinstance(data, dict) else None
    if not isinstance(ids, list) or any(not isinstance(i, int) or isinstance(i, bool) for i in ids):
        raise ValueError("expected {ids: [taskId, ...]}")
    with conn() as c:
        c.executemany("UPDATE tasks SET position = ? WHERE id = ?", list(enumerate(ids)))
        return {"reordered": len(ids)}


def overdue():
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM tasks WHERE done = 0 AND due IS NOT NULL"
            " AND due < date('now', 'localtime') ORDER BY due"
        ).fetchall()
        return [dict(r) for r in rows]


# --- meta (used by the mailer to remember what it already sent) ----------
def meta_get(key):
    with conn() as c:
        row = c.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def meta_set(key, value):
    with conn() as c:
        c.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
