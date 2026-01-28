from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta

@dataclass
class SRS:
    reps:int=0
    lapses:int=0
    interval:int=0
    ease:float=2.3
    due:date|None=None

def _clamp(x,lo,hi):
    return max(lo,min(hi,x))

def sm2(s:SRS, q:int, today:date)->SRS:
    q=max(0,min(5,int(q)))
    ease=_clamp(s.ease + (0.1-(5-q)*(0.08+(5-q)*0.02)), 1.3, 2.7)

    reps, lapses, interval = s.reps, s.lapses, s.interval
    if q<3:
        lapses += 1
        reps = 0
        interval = 1
    else:
        reps += 1
        if reps==1: interval=1
        elif reps==2: interval=3
        else: interval=max(4, int(round(interval*ease)))

    due=today+timedelta(days=interval)
    return SRS(reps=reps,lapses=lapses,interval=interval,ease=ease,due=due)
