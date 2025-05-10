import os, launch # type: ignore
from pathlib import Path

REQ_FILE = Path(__file__).with_name("requirements.txt")

if not REQ_FILE.exists():
    print(f"[arcenciel-link] requirements.txt not found at {REQ_FILE}")
    raise SystemExit(0)

with REQ_FILE.open() as f:
    packages = [
        l.strip() for l in f
        if l.strip() and not l.startswith("#")
    ]

for p in packages:
    if not launch.is_installed(p):
        launch.run_pip(f"install {p}", f"arcenciel-link requirement: {p}")