"""
Interactive stepping engine over chronological 2024 events.

State evolves independently of the CSV snapshots: CSVs supply the
demand/backlog/plan stream plus opening levels; on_hand/pipeline are ours.
Model inputs flow via src/agents (failure rates, delay histories); the
engine reads frames only for event iteration and opening snapshots.
"""
from pathlib import Path

import pandas as pd

from .. import data as D
from ..agents import failure_compilation as AG_fail
from ..agents import supply_delay_trends as AG_del
from ..model import h as H
from ..model import r as R
from ..model import s as S
from . import scoring as SC

SYNTH_2024 = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic_output_2024"

LEADS = {"Supplier A": 10,
         "Supplier B": 12,
         "Supplier C": 14,
         "Supplier D": 18,
         "Supplier E": 7}

PIPELINE_COVER_DAYS = 7
REVIEW_DAYS = 7


def init(synth_dir: Path | str = SYNTH_2024) -> dict:
    """
    Load 2024 CSVs and cache agent-supplied model inputs plus date index.

    Args:
        synth_dir: directory holding events.csv, parts.csv, flat_view.csv.

    Returns:
        Mutable engine state dict (unstarted: current_date None).
    """
    events, parts, flat = D.load(synth_dir)
    events = events.sort_values("Date").reset_index(drop=True)
    flat = flat.sort_values("Date").reset_index(drop=True)
    ag_fail = AG_fail.summarize(parts)
    ag_del = AG_del.summarize(flat)
    return _init_from_frames(events,
                             parts,
                             flat,
                             ag_fail["by_part"],
                             ag_del["delays_by_supplier"])


def _init_from_frames(events: pd.DataFrame,
                      parts: pd.DataFrame,
                      flat: pd.DataFrame,
                      fail_by_part: dict,
                      delays_by_supplier: dict) -> dict:
    """
    Assemble engine state from frames plus agent-supplied inputs.

    Args:
        events: parent event rows sorted by Date.
        parts: child part rows.
        flat: joined view sorted by Date.
        fail_by_part: dict Part_SKU -> mean failure rate (via agent).
        delays_by_supplier: dict supplier -> delay history (via agent).

    Returns:
        Mutable engine state dict (unstarted: current_date None).
    """
    s_model = S.fit_flat(delays_by_supplier)
    p50 = {s: float(v) for s, v in s_model["p50"].items()}
    costs = {(p, s): float(g.Unit_Cost.median())
             for (p, s), g in flat.groupby(["Part_SKU", "Supplier"])}
    dates = sorted(events.Date.dt.normalize().unique().tolist())
    return {"events": events,
            "parts": parts,
            "flat": flat,
            "fail_by_part": {k: float(v) for k, v in fail_by_part.items()},
            "delays_by_supplier": delays_by_supplier,
            "s_p50": p50,
            "costs": costs,
            "dates": dates,
            "current_date": None,
            "on_hand": {},
            "pipeline": [],
            "proposals_cache": [],
            "filled": 0,
            "unfilled": 0,
            "spent": 0.0,
            "holding": 0.0,
            "history": []}


def start(state: dict,
          date: str = "2024-01-01",
          opening_cover_days: int = 30) -> dict:
    """
    Start (or restart) the run at a date, seeding on_hand from snapshots.

    Tops each pile up to estimated need over the opening window so a run
    does not open in a lead-time hole it can never fill back.

    Args:
        state: engine state from init.
        date: ISO date string; first event date on/after it is used.
        opening_cover_days: top-up horizon in days (0 keeps raw snapshots).

    Returns:
        Summary dict with current_date and event count on that date.
    """
    dates = state["dates"]
    target = pd.Timestamp(date).normalize()
    cur = next((d for d in dates if d >= target), dates[-1])
    flat = state["flat"]
    snap = flat[flat.Date.dt.normalize() <= cur].sort_values("Date")
    cover_end = cur + pd.Timedelta(days=int(opening_cover_days))
    window = state["events"][(state["events"].Date >= cur)
                             & (state["events"].Date < cover_end)]
    on_hand = {}
    models = sorted(state["events"].Tractor_Model.unique().tolist())
    warehouses = sorted(state["events"].Warehouse_Location.unique().tolist())
    parts_list = sorted(state["parts"].Part_SKU.unique().tolist())
    for m in models:
        for p in parts_list:
            pile = 0
            for w in warehouses:
                g = snap[(snap.Tractor_Model == m)
                         & (snap.Warehouse_Location == w)
                         & (snap.Part_SKU == p)]
                pile += int(g.Inventory_Levels.iloc[-1]) if len(g) else 0
            est = 0
            if int(opening_cover_days) > 0:
                fail = float(state["fail_by_part"].get(p, 0.05))
                gm = window[window.Tractor_Model == m]
                est = sum(int(d) + round(int(d) * fail)
                          for d in gm.Demand_Units.tolist())
            on_hand[(m, p)] = max(pile, est)
    state["current_date"] = cur
    state["on_hand"] = on_hand
    state["pipeline"] = []
    state["proposals_cache"] = []
    state["filled"] = 0
    state["unfilled"] = 0
    state["spent"] = 0.0
    state["holding"] = 0.0
    state["history"] = []
    n = int((state["events"].Date.dt.normalize() == cur).sum())
    return {"current_date": str(cur.date()),
            "n_events": n}


def proposals(state: dict,
              cover_days: int = PIPELINE_COVER_DAYS) -> list:
    """
    Build R-routed order proposals for Model groups on the date.

    Only pipeline arriving within cover_days counts as on-order position;
    far-future arrivals must not suppress today's need (lead times run
    16-36 days, so full-pipeline deduction chronically starves shelves).
    Gross need covers lead-time demand per bucket (supplier lead + S p50
    + review days); without cover, arrivals land on bucket-days with no
    events while event-days starve, capping fill near 0.5.

    Args:
        state: engine state from start.
        cover_days: pipeline arrivals within this many days count as on-order.

    Returns:
        List of proposal dicts with id, m, w, part, supplier, qty, cost.
    """
    _require_started(state)
    cur = state["current_date"]
    horizon = cur + pd.Timedelta(days=int(cover_days))
    day = state["events"][state["events"].Date.dt.normalize() == cur]
    out = []
    eng_costs = {s: state["costs"].get(("ENG-01", s), 0.0) for s in state["s_p50"]}
    ranked = H.rank_suppliers(state["s_p50"],
                              eng_costs)
    for m, g in day.groupby("Tractor_Model"):
        demand = int(g.Demand_Units.sum())
        plan = int(g.Production_Plan_Qty.sum())
        backlog = int(g.Backorder_Qty.sum())
        urgent = plan > 0 and backlog / plan > R.EXPEDITE_PCT
        costs = {(p, s): state["costs"].get((p, s), 0.0)
                 for p in sorted(state["parts"].Part_SKU.unique().tolist())
                 for s in state["s_p50"]}
        net = {}
        for p in sorted(state["parts"].Part_SKU.unique().tolist()):
            on_order = sum(o["qty"] for o in state["pipeline"]
                           if o["m"] == m and o["part"] == p
                           and pd.Timestamp(o["arrival_date"]) <= horizon)
            fail = float(state["fail_by_part"].get(p, 0.05))
            pick = (min(state["s_p50"], key=state["s_p50"].get) if urgent
                    else min(state["s_p50"],
                             key=lambda s, p=p: costs[(p, s)]))
            h_days = int(LEADS[pick] + round(state["s_p50"][pick]) + REVIEW_DAYS)
            net[p] = H.net_need(float(plan) * h_days,
                                float(backlog),
                                float(H.spares(float(demand) * h_days,
                                               float(fail))),
                                float(state["on_hand"].get((m, p), 0)),
                                float(on_order))
        lines = R.propose_orders(net,
                                 ranked,
                                 costs,
                                 state["s_p50"],
                                 LEADS,
                                 urgent=urgent)
        for line in lines:
            pid = f"{cur.date()}:{m}:{line['part']}:{line['supplier']}"
            out.append({"id": pid,
                        "m": m,
                        "order_date": str(cur.date()),
                        **line})
    state["proposals_cache"] = out
    return out


def approve(state: dict,
            proposal_id: str) -> dict:
    """
    Approve one proposal, placing it on the inbound pipeline.

    Args:
        state: engine state with a proposals cache.
        proposal_id: proposal id from proposals.

    Returns:
        Order dict with scheduled arrival_date, or error dict.
    """
    _require_started(state)
    match = next((p for p in state["proposals_cache"] if p["id"] == proposal_id), None)
    if match is None:
        return {"error": f"unknown proposal {proposal_id}"}
    arrival = pd.Timestamp(match["order_date"]) + pd.Timedelta(
        days=int(LEADS[match["supplier"]] + round(state["s_p50"][match["supplier"]])))
    order = {**match,
             "arrival_date": str(arrival.date())}
    state["pipeline"].append(order)
    state["spent"] += float(match["cost"])
    return order


def advance(state: dict,
            holding_per_unit: float = 1.0) -> dict:
    """
    Jump to the next event date, applying arrivals then consumption.

    Args:
        state: engine state from start.
        holding_per_unit: holding cost per on-hand unit per day stepped.

    Returns:
        Summary dict with from/to dates, arrivals, need, filled, costs, score.
    """
    _require_started(state)
    dates = state["dates"]
    cur = state["current_date"]
    idx = dates.index(cur)
    if idx + 1 >= len(dates):
        return {"advanced": False,
                "current_date": str(cur.date())}
    nxt = dates[idx + 1]
    arrived = [o for o in state["pipeline"] if pd.Timestamp(o["arrival_date"]) <= nxt]
    for o in arrived:
        key = (o["m"], o["part"])
        state["on_hand"][key] = state["on_hand"].get(key, 0) + int(o["qty"])
    state["pipeline"] = [o for o in state["pipeline"]
                         if pd.Timestamp(o["arrival_date"]) > nxt]
    day = state["events"][state["events"].Date.dt.normalize() == nxt]
    need_total = 0
    filled_total = 0
    for _, row in day.iterrows():
        m = row.Tractor_Model
        demand = int(row.Demand_Units)
        for p in sorted(state["parts"].Part_SKU.unique().tolist()):
            fail = float(state["fail_by_part"].get(p, 0.05))
            need = demand + round(demand * fail)
            need_total += need
            key = (m, p)
            avail = state["on_hand"].get(key, 0)
            use = min(need, avail)
            state["on_hand"][key] = avail - use
            filled_total += use
    state["filled"] += filled_total
    state["unfilled"] += need_total - filled_total
    days = max((nxt - cur).days, 1)
    state["holding"] += float(holding_per_unit) * sum(state["on_hand"].values()) * days
    state["current_date"] = nxt
    state["proposals_cache"] = []
    fill_so_far = R.fill_rate(float(state["filled"] + state["unfilled"]),
                              float(state["unfilled"]))
    entry = {"date": str(nxt.date()),
             "need": need_total,
             "filled": filled_total,
             "spent": float(state["spent"]),
             "holding": float(state["holding"]),
             "fill_so_far": fill_so_far}
    state["history"].append(entry)
    return {"advanced": True,
            "from": str(cur.date()),
            "to": str(nxt.date()),
            "n_events": int(len(day)),
            "arrived": len(arrived),
            "need": need_total,
            "filled": filled_total,
            "spent": float(state["spent"]),
            "holding": float(state["holding"]),
            "fill_so_far": fill_so_far,
            "score": SC.score(float(state["filled"]),
                              float(state["unfilled"]),
                              float(state["spent"]),
                              float(state["holding"]))}


def _require_started(state: dict) -> None:
    """
    Raise when the engine has no current date.

    Args:
        state: engine state from init.

    Returns:
        None.
    """
    if state.get("current_date") is None:
        raise ValueError("call start(state, date) first")
