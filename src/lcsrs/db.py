from __future__ import annotations
import os
import sqlite3
import pathlib
from datetime import date, datetime
from typing import Any

from . import APP_NAME

def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def today() -> date:
    return date.today()

def default_db_path() -> str:
    base = os.environ.get("XDG_DATA_HOME", os.path.join(os.path.expanduser("~"), ".local", "share"))
    p = pathlib.Path(base) / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return str(p / "lcsrs.db")

SCHEMA = r"""
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS meta(
  k TEXT PRIMARY KEY,
  v TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS problems(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lc_num INTEGER NOT NULL UNIQUE,
  title TEXT NOT NULL,
  phase TEXT,
  plan_order INTEGER
);

CREATE INDEX IF NOT EXISTS idx_prob_plan ON problems(plan_order);

CREATE TABLE IF NOT EXISTS srs(
  problem_id INTEGER PRIMARY KEY,
  reps INTEGER NOT NULL DEFAULT 0,
  lapses INTEGER NOT NULL DEFAULT 0,
  interval INTEGER NOT NULL DEFAULT 0,
  ease REAL NOT NULL DEFAULT 2.3,
  due TEXT NOT NULL,          -- YYYY-MM-DD
  updated_at TEXT NOT NULL,
  FOREIGN KEY(problem_id) REFERENCES problems(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reviews(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  problem_id INTEGER NOT NULL,
  ts TEXT NOT NULL,
  quality INTEGER NOT NULL,     -- 0..5
  note TEXT,
  FOREIGN KEY(problem_id) REFERENCES problems(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notes(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  problem_id INTEGER NOT NULL,
  ts TEXT NOT NULL,
  content TEXT NOT NULL,
  FOREIGN KEY(problem_id) REFERENCES problems(id) ON DELETE CASCADE
);
"""

def connect(db_path: str | None = None) -> sqlite3.Connection:
    db = db_path or default_db_path()
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    return con

def init(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)
    con.commit()

# meta
def meta_get(con: sqlite3.Connection, k: str, default: str | None = None) -> str | None:
    row = con.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return row["v"] if row else default

def meta_set(con: sqlite3.Connection, k: str, v: str) -> None:
    con.execute("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))
    con.commit()

# problems
def upsert_problem(con: sqlite3.Connection, lc_num: int, title: str, phase: str | None, plan_order: int) -> None:
    con.execute(
        """
        INSERT INTO problems(lc_num,title,phase,plan_order)
        VALUES(?,?,?,?)
        ON CONFLICT(lc_num) DO UPDATE SET
          title=excluded.title,
          phase=excluded.phase,
          plan_order=excluded.plan_order
        """,
        (lc_num, title, phase, plan_order),
    )
    con.commit()

def get_by_lc(con: sqlite3.Connection, lc_num: int):
    return con.execute("SELECT * FROM problems WHERE lc_num=?", (lc_num,)).fetchone()

def get_problem_id(con: sqlite3.Connection, lc_num: int) -> int:
    r = get_by_lc(con, lc_num)
    if not r:
        raise SystemExit(f"LC {lc_num} not found in DB (did you import plan.txt?)")
    return int(r["id"])

# srs
def ensure_srs(con: sqlite3.Connection, problem_id: int) -> None:
    row = con.execute("SELECT problem_id FROM srs WHERE problem_id=?", (problem_id,)).fetchone()
    if row:
        return
    con.execute(
        "INSERT INTO srs(problem_id,reps,lapses,interval,ease,due,updated_at) VALUES(?,?,?,?,?,?,?)",
        (problem_id, 0, 0, 0, 2.3, today().isoformat(), now_iso()),
    )
    con.commit()

def get_srs(con: sqlite3.Connection, problem_id: int):
    ensure_srs(con, problem_id)
    return con.execute(
        "SELECT reps,lapses,interval,ease,due,updated_at FROM srs WHERE problem_id=?",
        (problem_id,),
    ).fetchone()

def save_srs(con: sqlite3.Connection, problem_id: int, reps: int, lapses: int, interval: int, ease: float, due_iso: str) -> None:
    con.execute(
        """
        UPDATE srs
        SET reps=?, lapses=?, interval=?, ease=?, due=?, updated_at=?
        WHERE problem_id=?
        """,
        (reps, lapses, interval, ease, due_iso, now_iso(), problem_id),
    )
    con.commit()

def list_due_reviews(con: sqlite3.Connection, due_on_or_before: str, limit: int):
    return con.execute(
        """
        SELECT p.lc_num, p.title, p.phase, p.plan_order,
               s.reps, s.lapses, s.interval, s.ease, s.due
        FROM srs s
        JOIN problems p ON p.id=s.problem_id
        WHERE s.due <= ?
        ORDER BY s.due ASC, p.plan_order ASC
        LIMIT ?
        """,
        (due_on_or_before, limit),
    ).fetchall()

def pick_new_by_plan(con: sqlite3.Connection, cursor_plan_order: int, n: int):
    # choose next NEW by plan_order > cursor, and that has never been reviewed
    return con.execute(
        """
        SELECT p.lc_num, p.title, p.phase, p.plan_order
        FROM problems p
        LEFT JOIN reviews r ON r.problem_id=p.id
        WHERE p.plan_order > ?
        GROUP BY p.id
        HAVING COUNT(r.id)=0
        ORDER BY p.plan_order ASC
        LIMIT ?
        """,
        (cursor_plan_order, n),
    ).fetchall()

def set_cursor_plan_order(con: sqlite3.Connection, plan_order: int) -> None:
    meta_set(con, "cursor_plan_order", str(int(plan_order)))

def get_cursor_plan_order(con: sqlite3.Connection) -> int:
    v = meta_get(con, "cursor_plan_order", "0")
    try:
        return int(v or "0")
    except ValueError:
        return 0

# reviews
def add_review(con: sqlite3.Connection, lc_num: int, quality: int, note: str | None) -> None:
    pid = get_problem_id(con, lc_num)
    ensure_srs(con, pid)
    con.execute(
        "INSERT INTO reviews(problem_id,ts,quality,note) VALUES(?,?,?,?)",
        (pid, now_iso(), int(quality), note),
    )
    con.commit()

def list_reviews(con: sqlite3.Connection, lc_num: int, limit: int = 30):
    pid = get_problem_id(con, lc_num)
    return con.execute(
        """
        SELECT ts, quality, note
        FROM reviews
        WHERE problem_id=?
        ORDER BY id DESC
        LIMIT ?
        """,
        (pid, limit),
    ).fetchall()

# notes
def add_note(con: sqlite3.Connection, lc_num: int, content: str) -> None:
    pid = get_problem_id(con, lc_num)
    con.execute("INSERT INTO notes(problem_id,ts,content) VALUES(?,?,?)", (pid, now_iso(), content))
    con.commit()

def list_notes(con: sqlite3.Connection, lc_num: int, limit: int = 50):
    pid = get_problem_id(con, lc_num)
    return con.execute(
        """
        SELECT ts, content
        FROM notes
        WHERE problem_id=?
        ORDER BY id DESC
        LIMIT ?
        """,
        (pid, limit),
    ).fetchall()

def stats(con: sqlite3.Connection) -> dict[str, Any]:
    total = con.execute("SELECT COUNT(*) AS c FROM problems").fetchone()["c"]
    due = con.execute(
        """
        SELECT COUNT(*) AS c
        FROM srs
        WHERE due <= ?
        """,
        (today().isoformat(),),
    ).fetchone()["c"]
    new_left = con.execute(
        """
        SELECT COUNT(*) AS c
        FROM problems p
        LEFT JOIN reviews r ON r.problem_id=p.id
        GROUP BY p.id
        HAVING COUNT(r.id)=0
        """
    ).fetchall()
    new_left = len(new_left)
    return {"total": int(total), "due_reviews": int(due), "new_left": int(new_left)}
