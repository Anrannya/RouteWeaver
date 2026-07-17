# VG-DoT: Verifier-Gated Division-of-Thoughts

VG-DoT extends Division-of-Thoughts (DoT) with verifier-gated,
non-parametric evidence. DoT still decomposes each query, constructs the DAG,
and assigns each node to a local SLM or cloud LLM. VG-DoT changes the evidence
available to that routed executor; it does not replace model routing.

## Method: the Evidence Lifecycle

Every benchmark implements the same six-stage contract:

1. **Target** — select the query, DAG node, or environment action that may
   benefit from external evidence.
2. **Produce** — generate a candidate using a symbolic operator, retrieved
   knowledge, bounded search, or action grounding.
3. **Verify** — apply a task-appropriate, non-generative check to the candidate.
4. **Control** — decide whether accepted evidence should enter the current
   execution, using deterministic rules or a learned policy.
5. **Integrate** — use one of three explicit outcomes:
   `REPLACE` (skip the corresponding model call), `ASSIST` (inject a verified
   hint), or `FALLBACK` (execute the original DoT path).
6. **Update** — record acceptance, corrections, failures, latency, and token
   use; CSQA additionally learns the evidence-placement policy offline.

The domain implementations are:

- **MATH:** symbolic candidates are checked for grounded arguments and valid
  execution, then replace or assist selected DAG nodes.
- **CSQA:** retrieved knowledge is validated before a sequential GRPO policy
  decides where to inject it as assistance.
- **P3:** bounded candidate search uses the benchmark `sat(x)` predicate as a
  validity verifier; accepted candidates replace the query-level answer and
  failed search falls back to DoT. This is a task-specific oracle setting and
  should not be described as a general knowledge tool.
- **WebShop:** proposed actions are grounded against legal page actions;
  accepted actions replace malformed actions and failures preserve the
  original policy behavior.

### Evidence Lifecycle versus experiment harness

The **Evidence Lifecycle is the method inside one inference run**: it specifies
what evidence may enter reasoning, how it is verified, and how failure recovers
to DoT.

The **harness is outside the method**: it selects `--tool` or `--no-tool`,
orders paired branches, repeats runs, initializes logs, and aggregates metrics.
A harness does not produce or verify evidence. Keeping these layers separate
prevents benchmark-specific launch code from being mistaken for the paper's
technical contribution.

## Environment

The current experiments use Python 3, the `DoT_env` Conda environment, a local
Ollama OpenAI-compatible server, and a DeepSeek-compatible API:

```bash
conda activate DoT_env
export DEEPSEEK_API_KEY="..."
ollama serve
```

The default local endpoint is `http://localhost:11434/v1`; model names and
cloud model aliases are stored in each benchmark's `*_config.json`. Never
commit API credentials.

MATH, CSQA, and P3 read the processed datasets under `Task_Datasets/`.
The repository includes the frozen decomposition/allocation records used by
the step-2 comparisons:

- `MATH_Trys/TmpRes/step2In_MATH_last.json`
- `Puzzle_Trys/TmpRes/step2In_Puzzle_last.json`
- `CSQA_Trys/TmpRes/step2In_csqa_last.json`
- `WebShop/updated_first_file.json`

## Protocol checks

Run these checks before a paper experiment:

```bash
cd /data1/chenshangxiao/DoT/DoT
python CSQA_Trys/test_protocol_integrity.py
python Puzzle_Trys/test_protocol_integrity.py
python MATH_Trys/tests/test_phase25_assignment_semantics.py
python MATH_Trys/audit_current_assignments.py
```

The released CSQA and P3 depth maps omit boundary nodes in 9 and 7 records.
`CSQA_Trys/protocol.py` and `Puzzle_Trys/protocol.py` reconstruct canonical DAG
layers for every compared branch. Results produced before this correction
must not be mixed with corrected runs.

## Standard runner contract

Each benchmark exposes two public entry points:

- a single-branch runner with `--tool` and `--no-tool`;
- a comparison harness that runs both branches under one protocol.

Legacy step-2 files are retained as implementation modules and for backward
compatibility. The commands below are the supported public interface.
Use the comparison harnesses for all reported paper numbers. Single-branch
runners are intended for branch reproduction and debugging; historical MATH
retry behavior and P3 exception accounting differ from the paired harness and
must not be mixed into the same result table.

### MATH

Single branch:

```bash
cd /data1/chenshangxiao/DoT/DoT/MATH_Trys
python MATH_dotrun.py --no-tool --n 200
python MATH_dotrun.py --tool --n 200
```

Paired, order-balanced paper comparison:

```bash
python MATH_dotrun_step2_compare.py \
  --rounds 2 --n 200 --order auto --seed 42
```

Results are written under `MATH_Trys/Logs/compare log/<timestamp>/`.

### CSQA

For the paper interface, `--tool` means validated evidence with the
`seqmdp_grpo` placement policy; `--no-tool` means `no_inject`.

```bash
cd /data1/chenshangxiao/DoT/DoT/CSQA_Trys
python CSQA_dotrun.py --no-tool --n 200 --temperature 1
python CSQA_dotrun.py --tool --n 200 --temperature 1
```

Paired comparison:

```bash
python CSQA_dotrun_step2_grpo_compare.py \
  --rounds 3 --n 200 --temperature 1 \
  --modes no_inject,seqmdp_grpo
```

The trained policy is
`CSQA_Trys/GRPO/cache/seqmdp_grpo_sampled_policy.json`. Results and a
machine-readable `summary.json` are written under
`CSQA_Trys/Logs/grpo_compare/<timestamp>/`.

### P3

Single branch:

```bash
cd /data1/chenshangxiao/DoT/DoT/Puzzle_Trys
python Puzzle_dotrun.py --no-tool --n 200
python Puzzle_dotrun.py --tool --n 200
```

Paired comparison:

```bash
python Puzzle_dotrun_step2_compare.py --rounds 3 --n 200
```

Results are written under `Puzzle_Trys/Logs/compare log/<timestamp>/`.

### WebShop

Install and start the original WebShop environment first. The default URL is
`http://127.0.0.1:3000`; override it without editing code:

```bash
export WEBSHOP_URL="http://127.0.0.1:3000"
cd /data1/chenshangxiao/DoT/DoT/WebShop
python webshop_dot.py --no-tool --n 100
python webshop_dot.py --tool --n 100
```

Sequential, order-balanced comparison:

```bash
python webshop_dot_compare.py --rounds 2 --n 100 --order auto
```

Branch logs are written under `WebShop/Logs/DOT/`; commands, branch metrics,
and per-round deltas are recorded in
`WebShop/Logs/compare/<timestamp>/manifest.json`.

## Rebuilding evidence annotations

The paper comparison uses frozen records so both branches share decomposition,
DAG structure, and model allocation. Rebuild only the deterministic MATH/P3
evidence annotations with:

```bash
cd /data1/chenshangxiao/DoT/DoT/MATH_Trys
python build_with_tool.py

cd /data1/chenshangxiao/DoT/DoT/Puzzle_Trys
python build_with_tool.py
```

Running `*_dotrun_step1.py` regenerates decomposition, but it does not reproduce
the frozen model allocation by itself. Adapter training/application remains a
separate pipeline inherited from DoT. Therefore, use the checked-in step-2
records for exact evaluation reproduction and report regeneration experiments
separately.

## Reproducibility rules

- Compare DoT and VG-DoT on identical question IDs, canonical DAGs, model
  assignments, prompts, temperatures, and judge settings.
- Treat a tool failure or verifier rejection as `FALLBACK`, not as an error
  removed from the denominator.
- Preserve per-question predictions, wrong-to-right/right-to-wrong
  transitions, token usage, wall time, and all exceptions.
- Record the exact command, commit hash, model endpoints/versions, start time,
  and WebShop environment version for each run.
- Do not combine numbers from `/DoT_fault/DoT` with this repository's main
  paired table; the model and protocol configurations differ.

## Paper artifacts

- `paper/abstract.tex`, `paper/method.tex`, `paper/experiments.tex`
- `paper/evidence_index.md`: source and validity status of numerical claims
- `paper/submission_strategy_zh.md`: writing and experiment strategy
- `paper/framework_vgdot.svg`: editable framework source
- `paper/framework_vgdot.pdf`: LaTeX-ready export
- `paper/framework_vgdot.pptx`: editable PowerPoint version

Regenerate the vector figure with:

```bash
cd /data1/chenshangxiao/DoT/DoT
conda run -n DoT_env python paper/draw_framework.py
```
