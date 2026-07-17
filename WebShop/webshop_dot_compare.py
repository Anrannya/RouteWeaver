"""Sequential paired harness for WebShop DoT versus VG-DoT."""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def run_branch(base: Path, mode: str, n: int, no_hint: bool,
               summary_path: Path) -> dict:
    command = [
        sys.executable, "webshop_dot.py", f"--{mode}", "--n", str(n),
        "--summary-json", str(summary_path),
    ]
    if mode == "tool" and no_hint:
        command.append("--no-hint")
    started = time.time()
    completed = subprocess.run(command, cwd=base, check=False)
    result = {
        "mode": mode,
        "command": command,
        "returncode": completed.returncode,
        "elapsed_seconds": time.time() - started,
    }
    if completed.returncode == 0 and summary_path.exists():
        result["metrics"] = json.loads(summary_path.read_text(encoding="utf-8"))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run WebShop no-tool/tool branches sequentially."
    )
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument(
        "--order",
        choices=("auto", "no-tool-first", "tool-first"),
        default="auto",
        help="auto alternates branch order across rounds",
    )
    parser.add_argument(
        "--no-hint",
        action="store_true",
        help="compare no-tool against the tool-without-prebaked-hint ablation",
    )
    args = parser.parse_args()
    if args.rounds < 1 or args.n < 1:
        parser.error("--rounds and --n must be positive")

    base = Path(__file__).resolve().parent
    session = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "n": args.n,
        "rounds": args.rounds,
        "order": args.order,
        "no_hint": args.no_hint,
        "runs": [],
    }
    session_dir = base / "Logs" / "compare" / datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    session_dir.mkdir(parents=True, exist_ok=True)

    for round_id in range(1, args.rounds + 1):
        if args.order == "no-tool-first":
            order = ("no-tool", "tool")
        elif args.order == "tool-first":
            order = ("tool", "no-tool")
        else:
            order = ("no-tool", "tool") if round_id % 2 else ("tool", "no-tool")

        for mode in order:
            print(f"\n===== Round {round_id}/{args.rounds}: {mode} =====")
            summary_path = session_dir / f"round_{round_id:02d}_{mode}.json"
            result = run_branch(base, mode, args.n, args.no_hint, summary_path)
            result["round"] = round_id
            session["runs"].append(result)
            (session_dir / "manifest.json").write_text(
                json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            if result["returncode"] != 0:
                raise SystemExit(
                    f"WebShop {mode} branch failed with exit code {result['returncode']}"
                )

    comparisons = []
    for round_id in range(1, args.rounds + 1):
        by_mode = {
            run["mode"]: run["metrics"]
            for run in session["runs"]
            if run["round"] == round_id and "metrics" in run
        }
        if set(by_mode) == {"no-tool", "tool"}:
            comparisons.append({
                "round": round_id,
                "average_reward_delta": (
                    by_mode["tool"]["average_reward"]
                    - by_mode["no-tool"]["average_reward"]
                ),
                "success_rate_delta": (
                    by_mode["tool"]["success_rate"]
                    - by_mode["no-tool"]["success_rate"]
                ),
                "total_time_delta_seconds": (
                    by_mode["tool"]["total_time"]
                    - by_mode["no-tool"]["total_time"]
                ),
            })
    session["comparisons"] = comparisons
    (session_dir / "manifest.json").write_text(
        json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nComparison manifest: {session_dir / 'manifest.json'}")
