from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, date
import os, pathlib

APP_NAME="lcsrs"

def today()->date:
    return datetime.now().date()

def now_iso()->str:
    return datetime.now().isoformat(timespec="seconds")

def db_path()->str:
    base=os.environ.get("XDG_DATA_HOME", os.path.join(os.path.expanduser("~"), ".local", "share"))
    p=pathlib.Path(base)/APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return str(p/"lcsrs.db")

@dataclass(frozen=True)
class Grade:
    q:int
    label:str

GRADE={
    "easy":Grade(5,"一遍过/很熟练"),
    "hard":Grade(3,"过了但不熟练"),
    "again":Grade(1,"忘记/没做出来"),
}
