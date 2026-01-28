from __future__ import annotations
import sqlite3
from typing import Optional
from .util import db_path

SCHEMA="""
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS problems(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 lc_num INTEGER NOT NULL,
 title TEXT NOT NULL,
 phase TEXT,
 premium INTEGER DEFAULT 0,
 starred INTEGER DEFAULT 0,
 plan_order INTEGER,
 created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_prob ON problems(lc_num,title);
CREATE INDEX IF NOT EXISTS idx_plan_order ON problems(plan_order);

CREATE TABLE IF NOT EXISTS srs(
 problem_id INTEGER PRIMARY KEY,
 reps INTEGER NOT NULL DEFAULT 0,
 lapses INTEGER NOT NULL DEFAULT 0,
 interval INTEGER NOT NULL DEFAULT 0,
 ease REAL NOT NULL DEFAULT 2.3,
 due TEXT,
 last_reviewed TEXT,
 FOREIGN KEY(problem_id) REFERENCES problems(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reviews(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 problem_id INTEGER NOT NULL,
 reviewed_at TEXT NOT NULL,
 quality INTEGER NOT NULL,
 note TEXT,
 FOREIGN KEY(problem_id) REFERENCES problems(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_due ON srs(due);
"""

def connect(path:Optional[str]=None)->sqlite3.Connection:
    con=sqlite3.connect(path or db_path())
    con.row_factory=sqlite3.Row
    return con

def init(con:sqlite3.Connection)->None:
    con.executescript(SCHEMA)
    con.commit()

def upsert(con, lc:int, title:str, phase:str|None, premium:int, starred:int, plan_order:int|None, created_at:str)->int:
    con.execute(
        "INSERT OR IGNORE INTO problems(lc_num,title,phase,premium,starred,plan_order,created_at) VALUES(?,?,?,?,?,?,?)",
        (lc,title,phase,premium,starred,plan_order,created_at),
    )
    # 如果已存在但 plan_order 为空/没写过，补上
    con.execute(
        "UPDATE problems SET plan_order=COALESCE(plan_order, ?) WHERE lc_num=? AND title=?",
        (plan_order, lc, title),
    )
    row=con.execute("SELECT id FROM problems WHERE lc_num=? AND title=?",(lc,title)).fetchone()
    pid=int(row["id"])
    con.execute("INSERT OR IGNORE INTO srs(problem_id) VALUES(?)",(pid,))
    con.commit()
    return pid

def get_plan_order_by_lc(con, lc:int)->int|None:
    row=con.execute(
        "SELECT plan_order FROM problems WHERE lc_num=? AND plan_order IS NOT NULL ORDER BY plan_order DESC LIMIT 1",
        (lc,),
    ).fetchone()
    return int(row["plan_order"]) if row else None

def list_reviews_due(con, today_iso:str, limit:int):
    # 只取“已进入复习队列”的题：interval>0 且 due<=today
    return con.execute("""
      SELECT p.id,p.lc_num,p.title,p.phase,p.premium,p.starred,p.plan_order,
             s.reps,s.lapses,s.interval,s.ease,s.due
      FROM problems p JOIN srs s ON s.problem_id=p.id
      WHERE s.interval>0 AND s.due IS NOT NULL AND s.due <= ?
      ORDER BY s.due ASC, p.plan_order ASC
      LIMIT ?""",(today_iso,limit)).fetchall()

def list_new_after(con, cursor_plan_order:int, limit:int):
    # NEW：interval=0 且 reps=0（未开始），严格按 plan_order 往后取
    return con.execute("""
      SELECT p.id,p.lc_num,p.title,p.phase,p.premium,p.starred,p.plan_order,
             s.reps,s.lapses,s.interval,s.ease,s.due
      FROM problems p JOIN srs s ON s.problem_id=p.id
      WHERE p.plan_order IS NOT NULL
        AND p.plan_order > ?
        AND s.interval=0 AND s.reps=0
      ORDER BY p.plan_order ASC
      LIMIT ?""",(cursor_plan_order,limit)).fetchall()

def by_lc_latest(con, lc:int):
    return con.execute("""
      SELECT p.id,p.lc_num,p.title,p.phase,p.premium,p.starred,p.plan_order,
             s.reps,s.lapses,s.interval,s.ease,s.due
      FROM problems p JOIN srs s ON s.problem_id=p.id
      WHERE p.lc_num=?
      ORDER BY p.plan_order DESC, p.id DESC
      LIMIT 1""",(lc,)).fetchone()

def save_srs(con, pid:int, reps:int,lapses:int,interval:int,ease:float,due_iso:str,last_iso:str):
    con.execute("UPDATE srs SET reps=?,lapses=?,interval=?,ease=?,due=?,last_reviewed=? WHERE problem_id=?",
                (reps,lapses,interval,ease,due_iso,last_iso,pid))
    con.commit()

def add_review(con, pid:int, at_iso:str, q:int, note:str|None):
    con.execute("INSERT INTO reviews(problem_id,reviewed_at,quality,note) VALUES(?,?,?,?)",
                (pid,at_iso,int(q),note))
    con.commit()

def stats(con, today_iso:str)->dict:
    total=con.execute("SELECT COUNT(*) c FROM problems").fetchone()["c"]
    due_reviews=con.execute("SELECT COUNT(*) c FROM srs WHERE interval>0 AND due IS NOT NULL AND due<=?",(today_iso,)).fetchone()["c"]
    new_left=con.execute("SELECT COUNT(*) c FROM srs WHERE interval=0 AND reps=0").fetchone()["c"]
    mastered=con.execute("SELECT COUNT(*) c FROM srs WHERE reps>=5 AND interval>=21").fetchone()["c"]
    return {"total":total,"due_reviews":due_reviews,"new_left":new_left,"mastered":mastered}
