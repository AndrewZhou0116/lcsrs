from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class PlanItem:
    lc_num: int
    title: str
    phase: str | None
    plan_order: int

def _split_line(line: str) -> list[str]:
    # support: "69 Sqrt(x)", "69|Sqrt(x)|phase", "69, Sqrt(x), phase"
    if "|" in line:
        parts = [p.strip() for p in line.split("|")]
    elif "," in line:
        parts = [p.strip() for p in line.split(",")]
    else:
        parts = line.strip().split(None, 2)  # lc, title, phase?
        parts = [p.strip() for p in parts]
    return [p for p in parts if p != ""]

def parse_plan_text(text: str) -> list[PlanItem]:
    items: list[PlanItem] = []
    order = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = _split_line(line)
        if len(parts) < 2:
            continue
        try:
            lc = int(parts[0])
        except ValueError:
            continue
        title = parts[1]
        phase = parts[2] if len(parts) >= 3 else None
        items.append(PlanItem(lc_num=lc, title=title, phase=phase, plan_order=order))
        order += 1
    return items

def parse_plan_file(path: str | Path) -> list[PlanItem]:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    return parse_plan_text(text)
