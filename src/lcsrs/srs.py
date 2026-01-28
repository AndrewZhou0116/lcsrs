from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta

@dataclass(frozen=True)
class SRSState:
    reps: int
    lapses: int
    interval: int      # days
    ease: float        # SM-2 EF
    due: date

def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x

def sm2(state: SRSState, quality: int, today: date) -> SRSState:
    """
    SM-2-ish:
      quality: 0..5
      - if quality < 3 -> lapse, interval resets
      - else -> interval grows, EF updates
    """
    q = int(quality)
    if q < 0 or q > 5:
        raise ValueError("quality must be 0..5")

    reps = state.reps
    lapses = state.lapses
    interval = state.interval
    ease = state.ease

    if q < 3:
        # lapse
        lapses += 1
        reps = 0
        interval = 1
        ease = clamp(ease - 0.2, 1.3, 2.8)
        due = today + timedelta(days=interval)
        return SRSState(reps=reps, lapses=lapses, interval=interval, ease=ease, due=due)

    # success
    reps += 1
    # EF update
    ef = ease + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    ease = clamp(ef, 1.3, 2.8)

    if reps == 1:
        interval = 1
    elif reps == 2:
        interval = 6
    else:
        interval = max(1, int(round(interval * ease)))

    due = today + timedelta(days=interval)
    return SRSState(reps=reps, lapses=lapses, interval=interval, ease=ease, due=due)
