# Tractor Supply Chain Prototype

LLM/ML-assisted supply-chain optimizer prototype: demand, delay, and failure
models (H/O/S/F) plus a recommendation layer (R), run against a seeded
synthetic tractor dataset and a chronological 2024 stepping engine with a
live web UI. Full design in `docs/system_design.md`; locked data/design spec
in `data_scope_and_column_context.txt`.

## Layout

- `data/` — reference CSV, `synthetic_output/` (2020-2023, seed 42),
  `synthetic_output_2024/` (chronological, seed 2024), `generator/` scripts.
- `src/model/` (H/O/S/F/R, plain scalar/dict inputs only), `src/agents/`
  (sole DataFrame readers), `src/sim/` (stepping engine + scoring),
  `src/controller/` (policy CLI), `src/api.py` (snapshot + sim backends).
- `ui/` — stdlib web server + interactive six-box page (no new dependencies).
- `docs/` — Stage-1 artifacts (regenerate via `generate_stage1_artifacts.py`).
- `tests/` — unit + backend + live-server tests.

## Setup and verify

Requires: numpy, pandas (`pip install numpy pandas`).

- `python validate_synthetic.py` — 23/23 data checks.
- `python run_baselines.py` — O MAE ~31, S MAE ~3.7, tiers E9/A13/B15/C16/D18, fill 0.928.
- `python -m unittest discover tests` — full suite green (47 tests).

## Status (measured)

- Full-year approve-all from 2024-01-01 with 30-day opening cover: cumulative
  fill 1.000, clearing the 0.98 R target (~10.5B purchase + ~0.67B holding).
- Scoring reads trailing-30d fill as the headline metric; cumulative fill is
  capped by cold-start lead-time physics (a thin Jan-1 start measured 0.968
  with zero unfilled after January). Details in `docs/system_design.md`.
- What's next lives in `future_work.txt` (cost-disciplined policy, scale
  tuning, UI polish).

## Run

- UI: `python ui/serve_ui.py` → http://127.0.0.1:8000/ (init, start with
  cover days, approve proposals, advance, watch fill vs the 0.98 target).
- CLI: `python -m src.controller.step_2024 --steps 30 --approve all`
  (`--interactive` for a REPL, `--opening-cover-days` for opening stock).
- Regenerate data (seeded, reproducible): `python data/generator/generate_synthetic.py`,
  `python data/generator/generate_2024.py --help` for options.
