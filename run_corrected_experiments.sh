#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
  echo "DEEPSEEK_API_KEY is not set; refusing to launch scientific reruns." >&2
  exit 2
fi

cd "$ROOT"
conda run -n DoT_env python "$ROOT/CSQA_Trys/test_protocol_integrity.py"
conda run -n DoT_env python "$ROOT/Puzzle_Trys/test_protocol_integrity.py"
conda run -n DoT_env python "$ROOT/MATH_Trys/tests/test_phase25_assignment_semantics.py"

cd "$ROOT/CSQA_Trys"
conda run -n DoT_env python CSQA_dotrun_step2_grpo_compare.py \
  --rounds "${CSQA_ROUNDS:-3}" \
  --n "${CSQA_N:-200}" \
  --temperature 1 \
  --modes no_inject,seqmdp_grpo

cd "$ROOT/Puzzle_Trys"
conda run -n DoT_env python Puzzle_dotrun_step2_compare.py \
  --rounds "${P3_ROUNDS:-3}" \
  --n "${P3_N:-200}"
