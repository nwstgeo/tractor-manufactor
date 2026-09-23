"""
R: Recommendation Synthesis (rule-based).

Objective: minimize purchase + holding cost subject to >=98% fill rate.
Rules: expedite when backlog > 5% of plan; substitute supplier/part when
forecast delay exceeds lead-time slack.
"""
import pandas as pd
from . import h as H

FILL_TARGET = 0.98
EXPEDITE_PCT = 0.05


def propose_orders(net_needs: dict,
                   ranked_suppliers: list,
                   unit_costs: dict,
                   delay_p50: dict,
                   leads: dict,
                   holding_per_unit: float = 1.0,
                   urgent: bool = False) -> list:
    """
    Build supplier-allocated order proposals from net needs.

    Urgent (backlog over threshold) -> fastest supplier; otherwise cheapest.
    ranked_suppliers unused beyond compatibility; kept for API stability.

    Args:
        net_needs: dict part -> quantity to order.
        ranked_suppliers: supplier names best-first (informational).
        unit_costs: dict (part, supplier) -> unit cost (fallback: part -> cost).
        delay_p50: dict supplier -> median delay in days.
        leads: dict supplier -> base lead time in days.
        holding_per_unit: reserved for holding-cost weighting (unused).
        urgent: if True, route every line to the fastest supplier.

    Returns:
        List of {part, supplier, qty, cost} dicts, skipping zero needs.
    """
    proposals = []
    for part, qty in net_needs.items():
        if qty <= 0:
            continue
        part_costs = {s: float(unit_costs.get((part, s), float("inf")))
                      for s in delay_p50}
        pick = (min(delay_p50, key=delay_p50.get) if urgent
                else min(part_costs, key=part_costs.get))
        proposals.append({"part": part, "supplier": pick, "qty": int(qty),
                          "cost": int(qty) * float(unit_costs.get((part, pick),
                                                                  unit_costs.get(part, 0)))})
    return proposals


def actions(backlog: float,
            plan: float,
            delay_forecast: float,
            slack: float) -> list:
    """
    Derive rule-based action items for one planning snapshot.

    Args:
        backlog: unfilled tractor backlog.
        plan: production plan quantity.
        delay_forecast: predicted supplier delay in days.
        slack: tolerable delay in days before substitution is advised.

    Returns:
        List of human-readable action strings (expedite and/or substitute).
    """
    acts = []
    if plan > 0 and backlog / plan > EXPEDITE_PCT:
        acts.append(f"expedite: backlog {backlog} > 5% of plan {plan}")
    if delay_forecast > slack:
        acts.append(f"substitute: forecast delay {delay_forecast} exceeds slack {slack}")
    return acts


# Replaced by src/agents/order_feedback.py (supplies total_demand, total_backlog).
# def _data_for_fill_rate(events: pd.DataFrame) -> tuple:
#     """
#     Extract plain totals needed by fill_rate.
#
#     Args:
#         events: event rows with Demand_Units and Backorder_Qty.
#
#     Returns:
#         Tuple (total_demand, total_backlog) as floats.
#     """
#     return (float(events.Demand_Units.sum()),
#             float(events.Backorder_Qty.sum()))


def fill_rate(total_demand: float,
              total_backlog: float) -> float:
    """
    Compute observed order fill rate (1 - backlog / demand).

    Args:
        total_demand: summed demand units.
        total_backlog: summed backorder units.

    Returns:
        Fill rate in [0, 1]; 1.0 when total demand is zero.
    """
    return 1.0 - total_backlog / total_demand if total_demand else 1.0
