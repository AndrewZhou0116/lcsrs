from __future__ import annotations

import time
from pathlib import Path
from typing import Optional, Tuple

from .db import connect, tx, get_meta, set_meta
from .srs import ReviewState, next_state

RETIRE_EASY_STREAK = 3

def _should_retire(conn, lc_num: int, streak: int = RETIRE_EASY_STREAK) -> bool:
    rows = conn.execute(
        """
        SELECT grade
        FROM review_logs
        WHERE lc_num = ?
          AND grade != 'seed'
        ORDER BY reviewed_at DESC, id DESC
        LIMIT ?;
        """,
        (lc_num, streak),
    ).fetchall()

    if len(rows) < streak:
        return False
    return all(r["grade"] == "easy" for r in rows)


def get_meta(conn, key: str, default: str) -> str:
    row = conn.execute("SELECT value FROM meta WHERE key=?;", (key,)).fetchone()
    return row["value"] if row else default

def set_meta(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value;",
        (key, value),
    )

def _load_prev_review(conn, lc_num: int) -> Optional[ReviewState]:
    row = conn.execute(
        """
        SELECT due_at, interval_days, ease, reps, lapses, easy_streak, last_grade, status
        FROM reviews WHERE lc_num=?;
        """,
        (lc_num,),
    ).fetchone()
    if not row:
        return None
    return ReviewState(
        due_at=int(row["due_at"]),
        interval_days=float(row["interval_days"]),
        ease=float(row["ease"]),
        reps=int(row["reps"]),
        lapses=int(row["lapses"]),
        easy_streak=int(row["easy_streak"]),
        last_grade=str(row["last_grade"]),
        status=str(row["status"]),
    )

def _advance_cursor_to_next_new(conn) -> None:
    cur = int(get_meta(conn, "cursor_plan_order", "1") or "1")
    row = conn.execute(
        """
        SELECT MIN(p.plan_order) AS next_po
        FROM problems p
        LEFT JOIN reviews r ON r.lc_num=p.lc_num
        WHERE r.lc_num IS NULL AND p.plan_order >= ?;
        """,
        (cur,),
    ).fetchone()
    next_po = row["next_po"]
    if next_po is None:
        # no NEW left: cursor becomes (max+1)
        mx = conn.execute("SELECT MAX(plan_order) AS m FROM problems;").fetchone()["m"] or 0
        set_meta(conn, "cursor_plan_order", str(int(mx) + 1))
    else:
        set_meta(conn, "cursor_plan_order", str(int(next_po)))

def apply_done(db_path: Path, lc_num: int, grade: str, note: Optional[str]) -> Tuple[int, int]:
    """
    Returns (prev_due_at, next_due_at) as unix seconds (prev_due_at may be 0 if new).
    """
    now = int(time.time())
    conn = connect(db_path)

    with tx(conn):
        # sanity: ensure problem exists
        p = conn.execute("SELECT lc_num FROM problems WHERE lc_num=?;", (lc_num,)).fetchone()
        if not p:
            raise ValueError(f"lc_num {lc_num} not found in problems (did you import plan.txt?)")

        prev = _load_prev_review(conn, lc_num)
        prev_due = prev.due_at if prev else 0
        prev_int = prev.interval_days if prev else None
        prev_ease = prev.ease if prev else None

        nxt = next_state(prev, grade, now)

        conn.execute(
            """
            INSERT INTO reviews(lc_num, due_at, interval_days, ease, reps, lapses, easy_streak, last_grade, status, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(lc_num) DO UPDATE SET
              due_at=excluded.due_at,
              interval_days=excluded.interval_days,
              ease=excluded.ease,
              reps=excluded.reps,
              lapses=excluded.lapses,
              easy_streak=excluded.easy_streak,
              last_grade=excluded.last_grade,
              status=excluded.status,
              updated_at=excluded.updated_at;
            """,
            (
                lc_num,
                nxt.due_at,
                nxt.interval_days,
                nxt.ease,
                nxt.reps,
                nxt.lapses,
                nxt.easy_streak,
                nxt.last_grade,
                nxt.status,
                now,
            ),
        )

        conn.execute(
            """
            INSERT INTO review_logs(
              lc_num, reviewed_at, grade,
              prev_due_at, next_due_at,
              prev_intvl, next_intvl,
              prev_ease, next_ease,
              note
            ) VALUES(?,?,?,?,?,?,?,?,?,?);
            """,
            (
                lc_num,
                now,
                grade,
                prev_due if prev_due != 0 else None,
                nxt.due_at,
                prev_int,
                nxt.interval_days,
                prev_ease,
                nxt.ease,
                note,
            ),
        )

        # retire rule: 3 consecutive easy -> retired


        if grade != "easy":
            conn.execute(
                "UPDATE reviews SET status='active', updated_at=? WHERE lc_num=?;",
                (now, lc_num),
    )


        if nxt.easy_streak >= RETIRE_EASY_STREAK:
            conn.execute(
                "UPDATE reviews SET status='retired', updated_at=? WHERE lc_num=?;",
                (now, lc_num),
    )



        _advance_cursor_to_next_new(conn)

    conn.close()
    return prev_due, nxt.due_at


