"""
API backend: one function per UI-mock box (+ approval). JSON-serializable.
"""
from pathlib import Path

import pandas as pd

from . import data as D
from .agents import failure_compilation as AG_fail
from .agents import order_feedback as AG_ord
from .agents import supply_delay_trends as AG_del
from .model import f as F
from .model import h as H
from .model import o as O
from .model import r as R
from .model import s as S
from .sim import scoring as SC
from .sim import stepper as STEP

_state = {}
_sim = {}


def init(synth_dir: Path | str = D.SYNTH_DIR) -> dict:
    """
    Load data, fit O/S/F baselines, and cache state for API calls.

    Args:
        synth_dir: directory containing the generated CSVs.

    Returns:
        The module-level state dict (events, parts, flat, fitted O/S/F
        models, approval log). Must be called once before other api functions.
    """
    events, parts, flat = D.load(synth_dir)
    (tr_e, tr_p, tr_f), (ho_e, ho_p, ho_f) = D.split(events, parts, flat)
    ag_failures = AG_fail.summarize(tr_p)
    ag_delays = AG_del.summarize(tr_f)
    ag_orders = AG_ord.summarize(tr_e)
    o_model = O.fit(ag_orders["o_overall"],
                    ag_orders["o_seasonal"],
                    ag_orders["o_series"])
    s_model = S.fit_flat(ag_delays["delays_by_supplier"])
    f_model = F.fit(ag_orders["f_overall"],
                    ag_orders["f_pairs"])
    _state.update(events=events, parts=parts, flat=flat, o=o_model, s=s_model,
                  f=f_model, ag_failures=ag_failures, ag_delays=ag_delays,
                  ag_orders=ag_orders, approved=[])
    return _state


def customers_orders(limit: int = 50) -> list:
    """
    Serve the Customers Orders Table (H): latest order snapshots.

    Args:
        limit: maximum rows to return.

    Returns:
        List of stringified record dicts, newest first.
    """
    e = _state["events"].sort_values("Date", ascending=False).head(limit)
    return e[["uuid", "Date", "Tractor_Model", "Warehouse_Location", "Supplier",
              "Demand_Units", "Backorder_Qty"]].astype(str).to_dict("records")


def forecast_3mo(model: str = "TX-500",
                 warehouse: str = "CA") -> dict:
    """
    Serve the 3-month Forecast of Orders (O&F via R): 90 macro-adjusted days.

    Args:
        model: tractor model string.
        warehouse: warehouse code.

    Returns:
        Dict with model, warehouse, date list, and forecasted order values.
    """
    last = _state["events"].Date.max()
    dates = pd.date_range(last + pd.Timedelta(days=1), periods=90, freq="D")
    o = _state["o"]
    raw = O.forecast(o, dates, model, warehouse)
    adj = [F.adjust(_state["f"], v, 0.5) for v in raw]
    return {"model": model, "warehouse": warehouse,
            "dates": [str(d.date()) for d in dates],
            "orders": [round(float(v), 1) for v in adj]}


def inventory_status(limit: int = 50) -> list:
    """
    Serve the Supply Inventory Table (H): latest part-level stock rows.

    Args:
        limit: maximum rows to return.

    Returns:
        List of stringified record dicts, newest first.
    """
    f = _state["flat"].sort_values("Date", ascending=False).head(limit)
    return f[["uuid", "Date", "Tractor_Model", "Warehouse_Location", "Part_SKU",
              "Inventory_Levels", "Supplier"]].astype(str).to_dict("records")


def production_schedule(limit: int = 50) -> list:
    """
    Serve the Production Schedule (H): latest plan and backlog rows.

    Args:
        limit: maximum rows to return.

    Returns:
        List of stringified record dicts, newest first.
    """
    e = _state["events"].sort_values("Date", ascending=False).head(limit)
    return e[["uuid", "Date", "Tractor_Model", "Warehouse_Location",
              "Production_Plan_Qty", "Backorder_Qty"]].astype(str).to_dict("records")


def _latest_position(m: str = "TX-500",
                     w: str = "CA",
                     part: str = "ENG-01") -> pd.Series | None:
    """
    Fetch the latest flat row for one Model x Warehouse x Part.

    Args:
        m: tractor model.
        w: warehouse code.
        part: Part_SKU.

    Returns:
        The newest matching row, or None when no rows match.
    """
    f = _state["flat"]
    g = f[(f.Tractor_Model == m) & (f.Warehouse_Location == w)
          & (f.Part_SKU == part)].sort_values("Date").tail(30)
    if len(g) == 0:
        return None
    row = g.iloc[-1]
    return row


def proposed_orders() -> list:
    """
    Serve Proposed Orders to Approve (R): net needs routed by urgency.

    Builds one proposal line per part from the latest TX-500/CA position,
    routing to the fastest supplier when backlog exceeds 5% of plan and to
    the cheapest supplier otherwise.

    Returns:
        List of {part, supplier, qty, cost} proposal dicts.
    """
    parts = ["ENG-01", "TRN-02", "HYD-03", "ELEC-04", "CHS-05"]
    row = _latest_position()
    ag_fail = _state["ag_failures"]
    net = {p: H.net_need(plan=int(row.Production_Plan_Qty),
                          backlog=int(row.Backorder_Qty),
                          spare_qty=H.spares(int(row.Demand_Units),
                                             float(ag_fail["by_part"].get(p, ag_fail["overall_mean"]))),
                          on_hand=int(_latest_position(part=p).Inventory_Levels),
                          on_order=0) for p in parts}
    costs = {(p, s): float(_state["flat"][
        (_state["flat"].Part_SKU == p)
        & (_state["flat"].Supplier == s)].Unit_Cost.median())
        for p in parts for s in ["Supplier A", "Supplier B", "Supplier C",
                                 "Supplier D", "Supplier E"]}
    ranked = H.rank_suppliers(_state["s"]["p50"],
                              {s: costs.get(("ENG-01", s), 0) for s in _state["s"]["p50"]})
    leads = {"Supplier A": 10, "Supplier B": 12, "Supplier C": 14,
             "Supplier D": 18, "Supplier E": 7}
    plan, bo = int(row.Production_Plan_Qty), int(row.Backorder_Qty)
    urgent = plan > 0 and bo / plan > R.EXPEDITE_PCT
    return R.propose_orders(net, ranked, costs, _state["s"]["p50"], leads,
                            urgent=urgent)


def action_items() -> list:
    """
    Serve Action Items to do (R): expedite/substitute flags, latest 50.

    Scans the 200 most recent events and returns trailing action flags.

    Returns:
        List of {uuid, action} dicts (empty when nothing breaches thresholds).
    """
    e = _state["events"].sort_values("Date").tail(200)
    acts = []
    for _, r in e.iterrows():
        for a in R.actions(int(r.Backorder_Qty), int(r.Production_Plan_Qty),
                           float(_state["s"]["p50"][r.Supplier]), slack=14):
            acts.append({"uuid": r.uuid, "model": r.Tractor_Model, "action": a})
    return acts[-50:]


def approve_proposal(proposal_id: str) -> dict:
    """
    Record approval of a proposed order (in-memory approval log).

    Args:
        proposal_id: opaque proposal identifier string.

    Returns:
        Dict with the approved id and the running approval count.
    """
    _state["approved"].append(proposal_id)
    return {"approved": proposal_id, "count": len(_state["approved"])}


def sim_init(synth_dir: Path | str = STEP.SYNTH_2024) -> dict:
    """
    Start a stepping-engine session over the 2024 chronological stream.

    Args:
        synth_dir: directory holding the 2024 events/parts/flat CSVs.

    Returns:
        Summary dict with session dates range and event count.
    """
    st = STEP.init(synth_dir)
    _sim.update(state=st)
    dates = st["dates"]
    return {"events": len(st["events"]),
            "first": str(dates[0].date()),
            "last": str(dates[-1].date())}


def sim_start(date: str = "2024-01-01",
              opening_cover_days: int = 30) -> dict:
    """
    Start (or restart) the stepping run at a date.

    Args:
        date: ISO date string; first event date on/after it is used.
        opening_cover_days: opening stock top-up horizon (0 keeps snapshots).

    Returns:
        Summary dict with current_date and event count, or error dict.
    """
    if "state" not in _sim:
        return {"error": "call sim_init() first"}
    return STEP.start(_sim["state"],
                      date,
                      opening_cover_days)


def sim_proposals() -> list:
    """
    Build R-routed order proposals for the current stepping date.

    Returns:
        List of proposal dicts, or single-element error list.
    """
    if "state" not in _sim:
        return [{"error": "call sim_init() first"}]
    try:
        return STEP.proposals(_sim["state"])
    except ValueError as e:
        return [{"error": str(e)}]


def sim_approve(proposal_id: str) -> dict:
    """
    Approve one stepping proposal onto the inbound pipeline.

    Args:
        proposal_id: proposal id from sim_proposals.

    Returns:
        Order dict with arrival_date, or error dict.
    """
    if "state" not in _sim:
        return {"error": "call sim_init() first"}
    try:
        return STEP.approve(_sim["state"],
                            proposal_id)
    except ValueError as e:
        return {"error": str(e)}


def sim_advance(holding_per_unit: float = 1.0) -> dict:
    """
    Jump the stepping run to the next event date with arrivals/consumption.

    Args:
        holding_per_unit: holding cost per on-hand unit per day stepped.

    Returns:
        Advance summary dict with score, or error dict.
    """
    if "state" not in _sim:
        return {"error": "call sim_init() first"}
    try:
        return STEP.advance(_sim["state"],
                            holding_per_unit)
    except ValueError as e:
        return {"error": str(e)}


def sim_score() -> dict:
    """
    Score the stepping run to date against the R fill target.

    Returns:
        Score dict with fill, gap, costs, verdict, and history length.
    """
    if "state" not in _sim:
        return {"error": "call sim_init() first"}
    st = _sim["state"]
    out = SC.score(float(st.get("filled", 0)),
                   float(st.get("unfilled", 0)),
                   float(st.get("spent", 0.0)),
                   float(st.get("holding", 0.0)))
    out["steps"] = len(st.get("history", []))
    out["trail_30d_fill"] = SC.window_fill(st.get("history", []),
                                           30)["fill"]
    out["current_date"] = str(st["current_date"].date()) if st.get("current_date") is not None else None
    return out


def sim_history() -> list:
    """
    Return the stepping run history (one entry per advanced date).

    Returns:
        List of {date, need, filled, spent, holding, fill_so_far} dicts.
    """
    if "state" not in _sim:
        return [{"error": "call sim_init() first"}]
    return _sim["state"].get("history", [])


def _sim_started() -> dict | None:
    """
    Fetch the stepping state, or an error dict when unusable.

    Returns:
        Engine state dict, or None when no run is started.
    """
    st = _sim.get("state")
    if st is None or st.get("current_date") is None:
        return None
    return st


def sim_customers_orders(limit: int = 50) -> list:
    """
    Serve live Customers Orders Table (H): 2024 demand at/before sim date.

    Args:
        limit: maximum rows to return.

    Returns:
        Demand rows newest-first, or single-element error list.
    """
    st = _sim_started()
    if st is None:
        return [{"error": "call sim_init() then sim_start() first"}]
    e = st["events"][st["events"].Date.dt.normalize() <= st["current_date"]]
    e = e.sort_values("Date", ascending=False).head(limit)
    return e[["uuid", "Date", "Tractor_Model", "Warehouse_Location", "Supplier",
              "Demand_Units", "Backorder_Qty"]].astype(str).to_dict("records")


def sim_inventory_status() -> list:
    """
    Serve live Supply Inventory Table (H): owned stock aggregated by part.

    Every purchased unit lands here on arrival; consumption draws it down.
    Aggregated over models and warehouses to one row per BOM part.

    Returns:
        Five {Part_SKU, On_Hand, On_Order} dicts, or single-element
        error list.
    """
    st = _sim_started()
    if st is None:
        return [{"error": "call sim_init() then sim_start() first"}]
    totals = {}
    for (m, p), qty in st["on_hand"].items():
        inbound = sum(o["qty"] for o in st["pipeline"]
                      if o["m"] == m and o["part"] == p)
        hand, order = totals.get(p, (0, 0))
        totals[p] = (hand + int(qty), order + int(inbound))
    return [{"Part_SKU": p, "On_Hand": hand, "On_Order": order}
            for p, (hand, order) in sorted(totals.items())]


def sim_forecast_3mo(model: str = "TX-500",
                     warehouse: str = "CA") -> dict:
    """
    Serve live 3-month Forecast (O&F): 90 days from after the sim date.

    Args:
        model: tractor model string.
        warehouse: warehouse code.

    Returns:
        Forecast dict anchored on the sim date, or error dict.
    """
    st = _sim_started()
    if st is None:
        return {"error": "call sim_init() then sim_start() first"}
    if "o" not in _state or "f" not in _state:
        return {"error": "call init() first"}
    dates = pd.date_range(st["current_date"] + pd.Timedelta(days=1), periods=90, freq="D")
    raw = O.forecast(_state["o"], dates, model, warehouse)
    adj = [F.adjust(_state["f"], v, 0.5) for v in raw]
    return {"model": model, "warehouse": warehouse,
            "from": str(st["current_date"].date()),
            "dates": [str(d.date()) for d in dates],
            "orders": [round(float(v), 1) for v in adj]}


def sim_production_schedule(limit: int = 50) -> list:
    """
    Serve live Production Schedule (H): 2024 plan/backlog at/before sim date.

    Args:
        limit: maximum rows to return.

    Returns:
        Schedule rows newest-first, or single-element error list.
    """
    st = _sim_started()
    if st is None:
        return [{"error": "call sim_init() then sim_start() first"}]
    e = st["events"][st["events"].Date.dt.normalize() <= st["current_date"]]
    e = e.sort_values("Date", ascending=False).head(limit)
    return e[["uuid", "Date", "Tractor_Model", "Warehouse_Location",
              "Production_Plan_Qty", "Backorder_Qty"]].astype(str).to_dict("records")


def sim_action_items() -> list:
    """
    Serve live Action Items (R): flags over recent 2024 events to sim date.

    Returns:
        Trailing up-to-50 {uuid, action} dicts, or single-element error list.
    """
    st = _sim_started()
    if st is None:
        return [{"error": "call sim_init() then sim_start() first"}]
    e = st["events"][st["events"].Date.dt.normalize() <= st["current_date"]]
    e = e.sort_values("Date").tail(200)
    acts = []
    for _, r in e.iterrows():
        for a in R.actions(int(r.Backorder_Qty), int(r.Production_Plan_Qty),
                           float(st["s_p50"][r.Supplier]), slack=14):
            acts.append({"uuid": r.uuid, "model": r.Tractor_Model, "action": a})
    return acts[-50:]
