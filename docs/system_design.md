# Stage-1 System Design (Tractor Supply Chain)

Diagram: `system_diagram.svg` (boxes below mirror `Information Sources.pdf`, see `info_source_transcript.txt`).

## Pipeline

Info Sources -> 3 topic agents (stubs in `src/agents/`) -> 5 models (`src/model/`) -> API (`src/api.py`) -> 6 UI boxes.

Stepping path: `data/synthetic_output_2024/` -> engine (`src/sim/stepper.py`, scoring in `src/sim/scoring.py`) -> `sim_*` API -> policy CLI (`src/controller/step_2024.py`) or live UI (`ui/serve_ui.py` + `ui/stepping_ui.html`). Generators live in `data/generator/`.

## Models: inputs / outputs

- H (`src/model/h.py`): inputs plan, backlog, spare qty, on-hand, on-order scalars + delay/cost dicts. Outputs net needs, limiting part, supplier ranking.
- O (`src/model/o.py`): inputs overall float, seasonal-means dict, per-series history dict (from Order agent). Output 90-day demand forecast per Model x Warehouse.
- S (`src/model/s.py`): input per-supplier delay histories (from Delay agent). Outputs p50/p90 per supplier.
- F (`src/model/f.py`): inputs overall float + (demand, market) pairs (from Order agent). Output per-regime multiplier (pass-through ~1.0 by design).
- R (`src/model/r.py`): inputs net needs, costs, delays, backlog/plan. Outputs routed proposals + expedite/substitute actions, fill metric (target >= 0.98).

## Agents: sources / consumers

- `failure_compilation.py`: reads `parts.csv`; supplies per-part failure means -> H spares.
- `supply_delay_trends.py`: reads `flat_view.csv`; supplies delay histories -> S.
- `order_feedback.py`: reads `events.csv`; supplies O series/seasonal, F pairs, R totals -> O/F/R.
- Supply Chain Trends: out of scope (removed; see `data_scope_and_column_context.txt`).

## Data sources

- `data/synthetic_output/events.csv` (10k, uuid PK), `parts.csv` (50k), `flat_view.csv`; seed 42, 2020-01-01..2023-12-30.
- `data/synthetic_output_2024/events.csv` (2507, chronological) + `parts.csv` (12535) + `flat_view.csv`; seed 2024, 2024-01-01..2024-12-31, opened from end-2023 state (~6.85 events/day).
- Reference: example CSV (10k, flat uniform); macro numeric indicators in scope, news/ag-econ/market-expansion out of scope.

## UI boxes (all live in `docs/ui_mockup.html`)

Customers Orders Table (H), 3-month Forecast (O&F via R), Action Items (R), Proposed Orders + approve (R), Supply Inventory (H), Production Schedule (H).

Live UI (`ui/stepping_ui.html` via `python ui/serve_ui.py`): same six boxes backed by `/api/sim/*` on the current run date, plus run control, score vs 0.98, and history. The static `docs/ui_mockup.html` snapshot is unchanged.

## Stepping runs (engine `src/sim/stepper.py`, scoring `src/sim/scoring.py`)

- State: per-(model, part) piles (warehouse and supplier origin pooled — origin does not matter once received); arrivals land on order date + lead + S p50; consumption draws event demand + defect fallout.
- Ordering policy: proposals group demand by model and size route-aware lead-time cover (supplier lead + S p50 + 7 review days); only pipeline arriving within 7 days counts as on-order position.
- Opening: `start()` tops each pile to max(snapshot, first-30-day estimated need) (`opening_cover_days=30`; 0 keeps raw snapshots).
- Scoring: fill = filled / (filled + unfilled) in part-units vs R target 0.98; cost = purchase + holding. Cumulative fill is capped by cold-start lead-time physics (a thin Jan-1 start measured 0.968 with zero unfilled after January); trailing-30d fill is the fair forward scoreboard. Full-year approve-all holds trailing 1.000 from day 90.
- Placeholder scales (untuned): `holding_per_unit=1.0`, `PIPELINE_COVER_DAYS=7`, `REVIEW_DAYS=7`.
