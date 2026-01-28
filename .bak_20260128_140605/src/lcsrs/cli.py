from __future__ import annotations
import argparse, os
from pathlib import Path
from .util import today, now_iso, GRADE, db_path
from . import db as DB
from .import_plan import parse
from .srs import SRS, sm2

VERSION="0.2.0"

def q_from(tok:str)->int:
    t=tok.strip().lower()
    if t.isdigit(): return max(0,min(5,int(t)))
    if t in GRADE: return GRADE[t].q
    raise SystemExit("quality must be 0..5 or easy/hard/again")

def fmt_row(r, tag:str):
    star=" [+]" if int(r["starred"]) else ""
    prem=" (P)" if int(r["premium"]) else ""
    phase=r["phase"] or "-"
    due=r["due"] or "NEW"
    return f"{tag} {int(r['lc_num']):>4} {r['title']}{star}{prem} | phase={phase} | due={due} | reps={r['reps']} int={r['interval']}"

def cmd_init(a):
    con=DB.connect(a.db); DB.init(con)
    print(f"✅ DB ready: {a.db or db_path()}")

def cmd_import(a):
    con=DB.connect(a.db); DB.init(con)
    items=parse(Path(a.file).read_text(encoding="utf-8"))
    for it in items:
        DB.upsert(con,it.lc,it.title,it.phase,it.premium,it.starred,it.plan_order,now_iso())
    print(f"✅ Imported: {len(items)}")

def _cursor_plan_order(con)->int:
    lc = int(os.environ.get("LCSRS_CURSOR_LC","0") or "0")
    if lc<=0:
        return 0
    po = DB.get_plan_order_by_lc(con, lc)
    if po is None:
        print(f"⚠️ cursor lc={lc} not found in plan; cursor_plan_order=0")
        return 0
    return int(po)

def cmd_today(a):
    con=DB.connect(a.db); DB.init(con)
    cur=_cursor_plan_order(con)
    reviews=DB.list_reviews_due(con, today().isoformat(), a.reviews)
    new=DB.list_new_after(con, cur, a.new)

    print(f"📅 today: reviews={len(reviews)}/{a.reviews}, new={len(new)}/{a.new}, cursor_plan_order={cur}")
    for r in reviews:
        print(fmt_row(r, "R"))
    for r in new:
        print(fmt_row(r, "N"))

def cmd_grade(a):
    con=DB.connect(a.db); DB.init(con)
    row=DB.by_lc_latest(con,a.lc)
    if not row: raise SystemExit("❌ not found. import plan first.")
    q=q_from(a.quality); t=today()
    s=SRS(reps=int(row["reps"]),lapses=int(row["lapses"]),interval=int(row["interval"]),ease=float(row["ease"]),due=t)
    ns=sm2(s,q,t)
    DB.add_review(con,int(row["id"]),now_iso(),q,a.note)
    DB.save_srs(con,int(row["id"]),ns.reps,ns.lapses,ns.interval,ns.ease,ns.due.isoformat(),now_iso())
    print(f"✅ {row['lc_num']} {row['title']} | q={q} -> due={ns.due} interval={ns.interval} reps={ns.reps} ease={ns.ease:.2f}")

def cmd_session(a):
    con=DB.connect(a.db); DB.init(con)
    # session 只做“复习题”，避免一天被 NEW 塞爆
    rows=DB.list_reviews_due(con, today().isoformat(), a.limit)
    if not rows:
        print("🎉 No due reviews."); return
    print("🧠 Session (reviews): input easy/hard/again or 0..5. Enter=skip, q=quit")
    for i,r in enumerate(rows,1):
        print(f"\n[{i}/{len(rows)}] {fmt_row(r,'R')}")
        while True:
            inp=input("grade> ").strip().lower()
            if inp in ("q","quit","exit"): print("🛑 quit"); return
            if inp=="" or inp in ("s","skip"): break
            try: q=q_from(inp)
            except SystemExit as e: print(str(e)); continue
            t=today()
            s=SRS(reps=int(r["reps"]),lapses=int(r["lapses"]),interval=int(r["interval"]),ease=float(r["ease"]),due=t)
            ns=sm2(s,q,t)
            DB.add_review(con,int(r["id"]),now_iso(),q,None)
            DB.save_srs(con,int(r["id"]),ns.reps,ns.lapses,ns.interval,ns.ease,ns.due.isoformat(),now_iso())
            print(f"-> due={ns.due} interval={ns.interval} reps={ns.reps} ease={ns.ease:.2f}")
            break
    print("✅ session done")

def cmd_stats(a):
    con=DB.connect(a.db); DB.init(con)
    s=DB.stats(con, today().isoformat())
    print(f"📊 total={s['total']} due_reviews={s['due_reviews']} new_left={s['new_left']} mastered={s['mastered']}")

def main()->None:
    p=argparse.ArgumentParser(prog="lcsrs", description="LeetCode SRS CLI (offline-capable)")
    p.add_argument("--db", default=None, help="DB path (default ~/.local/share/lcsrs/lcsrs.db)")
    p.add_argument("-v","--version", action="store_true")
    sub=p.add_subparsers(dest="cmd", required=False)

    sp=sub.add_parser("init"); sp.set_defaults(f=cmd_init)
    sp=sub.add_parser("import"); sp.add_argument("file"); sp.set_defaults(f=cmd_import)

    sp=sub.add_parser("today")
    sp.add_argument("--reviews", type=int, default=3, help="how many due reviews to show")
    sp.add_argument("--new", type=int, default=1, help="how many new problems to pick (plan order)")
    sp.set_defaults(f=cmd_today)

    sp=sub.add_parser("grade"); sp.add_argument("lc", type=int); sp.add_argument("quality"); sp.add_argument("--note", default=None); sp.set_defaults(f=cmd_grade)
    sp=sub.add_parser("session"); sp.add_argument("--limit", type=int, default=50); sp.set_defaults(f=cmd_session)
    sp=sub.add_parser("stats"); sp.set_defaults(f=cmd_stats)

    a=p.parse_args()
    if a.version: print(f"lcsrs {VERSION}"); return
    if not a.cmd: p.print_help(); return
    a.f(a)

if __name__=="__main__":
    main()
