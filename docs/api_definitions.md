# API Definitions (backend in `src/api.py`; call `init()` once first)

Conventions: JSON-serializable lists/dicts of strings and numbers. All reads serve newest-first snapshots unless noted.

## `customers_orders(limit=50)` — Customers Orders Table (H)

- Returns: list of `{uuid, Date, Tractor_Model, Warehouse_Location, Supplier, Demand_Units, Backorder_Qty}` (stringified).
- Source: `events.csv` sorted by Date desc.

## `forecast_3mo(model="TX-500", warehouse="CA")` — 3-month Forecast (O&F via R)

- Returns: `{model, warehouse, dates[90], orders[90]}`; dates start day after max event Date; orders macro-adjusted, rounded to 0.1, non-negative.
- Models: `O.forecast` + `F.adjust`.

## `action_items()` — Action Items (R)

- Returns: trailing up-to-50 `{uuid, model, action}` from the 200 most recent events.
- Rules: expedite when backlog > 5% of plan; substitute when p50 delay forecast exceeds 14d slack.

## `proposed_orders()` — Proposed Orders (R)

- Returns: list of `{part, supplier, qty, cost}` per part with positive net need, from latest TX-500/CA position.
- Routing: urgent (backlog/plan > 5%) -> fastest supplier (E); else cheapest per (part, supplier) median cost.
- Spares: per-part failure means from Failure agent (was hardcoded 0.05).

## `inventory_status(limit=50)` — Supply Inventory (H)

- Returns: list of `{uuid, Date, Tractor_Model, Warehouse_Location, Part_SKU, Inventory_Levels, Supplier}` newest-first from flat view.

## `production_schedule(limit=50)` — Production Schedule (H)

- Returns: list of `{uuid, Date, Tractor_Model, Warehouse_Location, Production_Plan_Qty, Backorder_Qty}` newest-first from events.

## `approve_proposal(proposal_id)` — approval

- Args: `proposal_id` opaque string. Returns `{approved, count}`; appends to in-memory log.

## Stepping session over 2024 (`sim_*`, engine in `src/sim/stepper.py`)

- `sim_init(synth_dir=data/synthetic_output_2024)` — opens a session. Returns `{events, first, last}`.
- `sim_start(date="2024-01-01", opening_cover_days=30)` — seeds on-hand from snapshots topped to opening-window need. Returns `{current_date, n_events}` or `{error}`.
- `sim_proposals()` — R-routed proposals for the current date. Returns list of `{id, m, order_date, part, supplier, qty, cost}`.
- `sim_approve(proposal_id)` — pipelines one proposal. Returns order with `arrival_date` (order date + lead + S p50) or `{error}`.
- `sim_advance(holding_per_unit=1.0)` — jumps to next event date applying arrivals then consumption. Returns `{to, arrived, need, filled, spent, holding, fill_so_far, score}`.
- `sim_score()` — cumulative `score()` vs the 0.98 R target plus `steps`, trailing-30d fill, and `current_date`.
- Live six boxes (read the run, not static snapshots): `sim_customers_orders(limit)` (2024 demand ≤ sim date), `sim_inventory_status()` (5 aggregate `{Part_SKU, On_Hand, On_Order}` rows — purchased stock lands here), `sim_forecast_3mo(model, warehouse)` (O&F, 90d from sim date), `sim_production_schedule(limit)` (2024 plan/backlog ≤ sim date), `sim_action_items()` (R flags over recent 2024 events), plus `sim_proposals()`; `GET /api/sim/boxes` bundles all six.
- CLI: `python -m src.controller.step_2024 [--start-date] [--steps] [--approve all|none] [--holding-per-unit] [--opening-cover-days] [--interactive]`; `run_policy()` is the importable batch loop.

## Forward scoring (`src/sim/scoring.py`)

- `score(filled, unfilled, spent, holding, target=0.98)` — `{fill, gap, purchase, holding, total_cost, cost_per_filled, meets_target}`; fill in part-units.
- `window_fill(history, n=30)` — trailing-n-step fill; the fair forward scoreboard (cumulative is capped by cold-start lead-time physics: a thin Jan-1 start measured 0.968 with zero unfilled after January).
- `sim_history()` — per-step `{date, need, filled, spent, holding, fill_so_far}` entries.

## Functional UI (`ui/serve_ui.py` + `ui/stepping_ui.html`, stdlib only)

- Run: `python ui/serve_ui.py [--port 8000]`; open http://127.0.0.1:8000/. Single stepping session.
- `GET /` — interactive page (run control, score vs 0.98, proposals with approve buttons, history).
- `GET /api/snapshot` — all six static boxes plus agent summaries in one payload.
- `GET /api/sim/proposals|score|history`; `POST /api/sim/init|start|approve|advance` (JSON bodies).
