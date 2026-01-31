from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from .db import connect

@dataclass(frozen=True)
class ShowItem:
    lc_num: int
    title: str

def _get_meta(conn, key: str, default: str) -> str:
    row = conn.execute("SELECT value FROM meta WHERE key=?;", (key,)).fetchone()
    return row["value"] if row else default

def load_show(db_path: Path) -> Tuple[List[ShowItem], List[ShowItem]]:
    """
    Returns: (new_items, review_items)
    - NEW: from cursor_plan_order forward, problems that are NOT in reviews table
    - REVIEW: reviews due_at <= now, independent of cursor
    """
    now = int(time.time())
    conn = connect(db_path)

    cursor_plan_order = int(_get_meta(conn, "cursor_plan_order", "1"))
    new_quota = int(_get_meta(conn, "new_quota", "1"))
    review_per_new = int(_get_meta(conn, "review_per_new", "3"))
    review_quota = max(0, new_quota * review_per_new)

    new_rows = conn.execute(
        """
        SELECT p.lc_num, p.title
        FROM problems p
        LEFT JOIN reviews r ON r.lc_num = p.lc_num
        WHERE r.lc_num IS NULL
          AND p.plan_order >= ?
        ORDER BY p.plan_order
        LIMIT ?;
        """,
        (cursor_plan_order, new_quota),
    ).fetchall()

    review_rows = conn.execute(
        """
        SELECT p.lc_num, p.title
        FROM reviews r
        JOIN problems p ON p.lc_num = r.lc_num
        WHERE r.status='active'
          AND r.due_at <= ?
        ORDER BY r.due_at ASC
        LIMIT ?;
        """,
        (now, review_quota),
    ).fetchall()

    conn.close()

    new_items = [ShowItem(int(r["lc_num"]), r["title"]) for r in new_rows]
    review_items = [ShowItem(int(r["lc_num"]), r["title"]) for r in review_rows]
    return new_items, review_items

