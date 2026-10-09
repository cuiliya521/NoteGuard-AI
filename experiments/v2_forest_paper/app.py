"""Private acceptance launcher; executes the original complete application."""
import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
previous = os.environ.get("NOTEGUARD_FOREST_PAPER")
os.environ["NOTEGUARD_FOREST_PAPER"] = "1"
try:
    runpy.run_path(str(ROOT / "app.py"), run_name="__main__")
finally:
    if previous is None:
        os.environ.pop("NOTEGUARD_FOREST_PAPER", None)
    else:
        os.environ["NOTEGUARD_FOREST_PAPER"] = previous
