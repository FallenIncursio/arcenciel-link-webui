import re
from pathlib import Path

import launch  # type: ignore

REQ_FILE = Path(__file__).with_name("requirements.txt")

if not REQ_FILE.exists():
    print(f"[arcenciel-link] requirements.txt not found at {REQ_FILE}")
    raise SystemExit(0)

with REQ_FILE.open() as f:
    packages = [line.strip() for line in f if line.strip() and not line.startswith("#")]

for p in packages:
    distribution = re.split(r"[<>=!~;\[]", p, maxsplit=1)[0].strip()
    if distribution and not launch.is_installed(distribution):
        launch.run_pip(f"install {p}", f"arcenciel-link requirement: {p}")
