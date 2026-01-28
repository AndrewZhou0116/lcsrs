from __future__ import annotations
import re
from dataclasses import dataclass

PHASE=re.compile(r"^\s*Phase\s*\d+\s*[:：]\s*(.+?)\s*$", re.I)
PROB=re.compile(r"^\s*(?:【\+】\s*)?(\d+)\s+(.+?)\s*$")
PLUS=re.compile(r"^\s*【\+】\s*")

@dataclass
class Item:
    lc:int
    title:str
    phase:str|None
    premium:int
    starred:int
    plan_order:int

def parse(text:str)->list[Item]:
    phase=None
    out=[]
    order=0
    for raw in text.splitlines():
        line=raw.strip()
        if not line:
            continue
        m=PHASE.match(raw)
        if m:
            phase=m.group(1).strip()
            continue
        m2=PROB.match(raw)
        if not m2:
            continue
        lc=int(m2.group(1))
        title=m2.group(2).strip()
        title=re.sub(r"\s*\(.*?\)\s*$","",title).strip()
        premium=1 if "premium" in line.lower() else 0
        starred=1 if PLUS.match(raw) else 0
        order += 1
        out.append(Item(lc,title,phase,premium,starred,order))
    return out
