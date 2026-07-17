"""Canonical single-branch entry point for CSQA.

``--tool`` selects the paper's sequential-GRPO evidence policy, while
``--no-tool`` selects the no-injection DoT branch. Both delegate to the same
implementation used by the paired comparison runner.
"""

import argparse
import os
import runpy
import sys
from pathlib import Path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run one CSQA VG-DoT branch.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--tool", dest="use_tool", action="store_true",
                      help="enable validated evidence with sequential GRPO (default)")
    mode.add_argument("--no-tool", dest="use_tool", action="store_false",
                      help="disable evidence injection and execute DoT")
    parser.add_argument("--n", type=int, default=200,
                        help="number of questions to evaluate (default: 200)")
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--online-budget", type=float, default=0.44,
                        help="injection budget passed to the GRPO runner")
    parser.set_defaults(use_tool=True)
    args = parser.parse_args()
    if args.n < 1:
        parser.error("--n must be positive")

    base = Path(__file__).resolve().parent
    os.chdir(base)
    selected_mode = "seqmdp_grpo" if args.use_tool else "no_inject"
    target = base / "CSQA_dotrun_step2_grpo_compare.py"
    sys.argv = [
        str(target),
        "--rounds", "1",
        "--n", str(args.n),
        "--temperature", str(args.temperature),
        "--online_budget", str(args.online_budget),
        "--modes", selected_mode,
    ]
    runpy.run_path(str(target), run_name="__main__")
