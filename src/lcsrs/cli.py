from __future__ import annotations
import argparse
from datetime import date

from . import __version__
from . import db as DB
from .import_plan import parse_plan_file
from .srs import SRSState, sm2
from .util import open_url

# -------- quality mapping --------
def q_from(s: str) -> int:
    s = s.strip().lower()
    if s in ("easy", "e", "ok", "good"):
        return 5
    if s in ("fuzzy", "f", "meh", "hard"):
        return 3
    if s in ("forgot", "again", "a"):
        return 1
    # allow 0..5
    try:
        q = int(s)
        if 0 <= q <= 5:
            return q
    except ValueError:
        pass
    raise SystemExit("quality must be easy/fuzzy/forgot or 0..5")

def lc_problem_url(title: str) -> str:
    # LeetCode canonical: https://leetcode.com/problems/<slug>/description/
    # build slug similar to LC: lowercase, spaces->-, remove non-alnum/-.
    import re
    t = title.strip().lower()
    t = t.replace("(", " ").replace(")", " ")
    t = re.sub(r"[’']", "", t)
    t = re.sub(r"[^a-z0-9]+", "-", t)
    t = re.sub(r"-{2,}", "-", t).strip("-")
    return f"https://leetcode.com/problems/{t}/description/"

def cmd_init(a):
    con = DB.connect(a.db)
    DB.init(con)
    print(f"✅ DB ready: {DB.default_db_path() if a.db is None else a.db}")

def cmd_import(a):
    con = DB.connect(a.db)
    DB.init(con)
    items = parse_plan_file(a.file)
    for it in items:
        DB.upsert_problem(con, it.lc_num, it.title, it.phase, it.plan_order)
    print(f"✅ Imported {len(items)} from {a.file}")

def cmd_cursor(a):
    con = DB.connect(a.db); DB.init(con)
    # cursor means: last plan_order consumed
    if a.set is not None:
        # allow setting by LC number too
        r = DB.get_by_lc(con, a.set)
        if not r:
            raise SystemExit(f"LC {a.set} not found")
        DB.set_cursor_plan_order(con, int(r["plan_order"]))
        print(f"✅ cursor_plan_order set to {int(r['plan_order'])} (after LC {a.set})")
        return
    print(DB.get_cursor_plan_order(con))

def cmd_show(a):
    con = DB.connect(a.db); DB.init(con)
    cur = DB.get_cursor_plan_order(con)
    new_rows = DB.pick_new_by_plan(con, cur, a.new)
    due_rows = DB.list_due_reviews(con, date.today().isoformat(), a.reviews)

    print("NEW:")
    if not new_rows:
        print("  (none)")
    else:
        for r in new_rows:
            print(f"  {int(r['lc_num']):>4}  {r['title']}")

    print("\nREVIEW:")
    if not due_rows:
        print("  (none)")
    else:
        for r in due_rows:
            print(f"  {int(r['lc_num']):>4}  {r['title']}")

def cmd_open(a):
    con = DB.connect(a.db); DB.init(con)
    r = DB.get_by_lc(con, a.lc)
    if not r:
        raise SystemExit(f"LC {a.lc} not found in DB")
    url = lc_problem_url(r["title"])
    open_url(url)
    print(url)

def cmd_done(a):
    con = DB.connect(a.db); DB.init(con)
    lc = a.lc
    q = q_from(a.quality)
    note = a.note

    # record review
    DB.add_review(con, lc, q, note)

    # update srs
    pid = DB.get_problem_id(con, lc)
    s = DB.get_srs(con, pid)
    st = SRSState(
        reps=int(s["reps"]),
        lapses=int(s["lapses"]),
        interval=int(s["interval"]),
        ease=float(s["ease"]),
        due=date.fromisoformat(s["due"]),
    )
    ns = sm2(st, q, date.today())
    DB.save_srs(con, pid, ns.reps, ns.lapses, ns.interval, ns.ease, ns.due.isoformat())

    # advance cursor if this was NEW (no prior reviews before this one)
    # we decide NEW by: total reviews count == 1 after insert
    rcount = con.execute(
        "SELECT COUNT(*) AS c FROM reviews WHERE problem_id=?",
        (pid,),
    ).fetchone()["c"]
    if int(rcount) == 1:
        pr = DB.get_by_lc(con, lc)
        if pr and pr["plan_order"] is not None:
            DB.set_cursor_plan_order(con, int(pr["plan_order"]))
            print(f"✅ NEW consumed -> cursor_plan_order={int(pr['plan_order'])}")

    print(f"✅ saved: LC {lc} q={q} -> due={ns.due} interval={ns.interval} reps={ns.reps} ease={ns.ease:.2f}")

def cmd_log(a):
    con = DB.connect(a.db); DB.init(con)
    rows = DB.list_reviews(con, a.lc, limit=a.limit)
    if not rows:
        print("(no reviews)")
        return
    for r in rows:
        note = f" | {r['note']}" if r["note"] else ""
        print(f"{r['ts']}  q={int(r['quality'])}{note}")

def cmd_note(a):
    con = DB.connect(a.db); DB.init(con)
    DB.add_note(con, a.lc, a.content)
    print("✅ note added")

def cmd_notes(a):
    con = DB.connect(a.db); DB.init(con)
    rows = DB.list_notes(con, a.lc, limit=a.limit)
    if not rows:
        print("(no notes)")
        return
    for r in rows:
        print(f"{r['ts']}  {r['content']}")

def cmd_stats(a):
    con = DB.connect(a.db); DB.init(con)
    s = DB.stats(con)
    print(f"📊 total={s['total']} due_reviews={s['due_reviews']} new_left={s['new_left']}")

def main():
    p = argparse.ArgumentParser(prog="lc", description="LeetCode SRS CLI")
    p.add_argument("--db", default=None, help="DB path (default ~/.local/share/lcsrs/lcsrs.db)")
    p.add_argument("-v", "--version", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=False)

    sp = sub.add_parser("init"); sp.set_defaults(f=cmd_init)

    sp = sub.add_parser("import")
    sp.add_argument("file")
    sp.set_defaults(f=cmd_import)

    sp = sub.add_parser("cursor")
    sp.add_argument("--set", type=int, default=None, help="set cursor by LC number")
    sp.set_defaults(f=cmd_cursor)

    sp = sub.add_parser("show")
    sp.add_argument("--new", type=int, default=1)
    sp.add_argument("--reviews", type=int, default=3)
    sp.set_defaults(f=cmd_show)

    sp = sub.add_parser("open")
    sp.add_argument("lc", type=int)
    sp.set_defaults(f=cmd_open)

    sp = sub.add_parser("done")
    sp.add_argument("lc", type=int)
    sp.add_argument("quality", help="easy/fuzzy/forgot or 0..5")
    sp.add_argument("--note", default=None)
    sp.set_defaults(f=cmd_done)

    sp = sub.add_parser("log")
    sp.add_argument("lc", type=int)
    sp.add_argument("--limit", type=int, default=30)
    sp.set_defaults(f=cmd_log)

    sp = sub.add_parser("note")
    sp.add_argument("lc", type=int)
    sp.add_argument("content")
    sp.set_defaults(f=cmd_note)

    sp = sub.add_parser("notes")
    sp.add_argument("lc", type=int)
    sp.add_argument("--limit", type=int, default=50)
    sp.set_defaults(f=cmd_notes)

    sp = sub.add_parser("stats")
    sp.set_defaults(f=cmd_stats)

    a = p.parse_args()
    if a.version:
        print(__version__)
        return
    if not a.cmd:
        p.print_help()
        return
    a.f(a)

if __name__ == "__main__":
    main()
