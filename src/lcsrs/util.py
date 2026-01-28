from __future__ import annotations
import os
import sys
import webbrowser

def open_url(url: str) -> None:
    # prefer browser open; fallback print
    try:
        webbrowser.open(url, new=2)
    except Exception:
        print(url)

def which_python() -> str:
    return sys.executable

def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)
