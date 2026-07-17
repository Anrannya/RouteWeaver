"""Canonical single-branch entry point for P3.

The implementation remains in Puzzle_dotrun_step2_with_tool.py so the
historical experiment logic has one source of truth. This public entry point
only standardizes the working directory and command-line interface.
"""

import os
import runpy
from pathlib import Path


if __name__ == "__main__":
    base = Path(__file__).resolve().parent
    os.chdir(base)
    runpy.run_path(str(base / "Puzzle_dotrun_step2_with_tool.py"), run_name="__main__")
