"""
Order/Servicing/Repair/Feedback agent (supplies O, F, and R inputs).
"""
import numpy as np
import pandas as pd


def summarize(events: pd.DataFrame,
              top_n: int = 3) -> dict:
    """
    Supply O seasonal/series inputs, F paired inputs, and R totals.

    Args:
        events: parent event rows with Date, Tractor_Model,
            Warehouse_Location, Demand_Units, Backorder_Qty, and
            Market_Trend_Index.
        top_n: retained for API stability; rankings are not supplied.

    Returns:
        Dict with o_overall, o_seasonal, o_series, f_overall, f_pairs,
        total_demand, total_backlog, and a text summary.
    """
    tot_d = float(events.Demand_Units.sum()) if len(events) else 0.0
    tot_b = float(events.Backorder_Qty.sum()) if len(events) else 0.0
    fill = 1.0 - tot_b / tot_d if tot_d else 1.0
    daily = events.groupby(["Date", "Tractor_Model", "Warehouse_Location"],
                           as_index=False).agg(Demand_Units=("Demand_Units", "mean"))
    daily["Date"] = pd.to_datetime(daily["Date"])
    daily["month"] = daily.Date.dt.month
    o_overall = float(daily.Demand_Units.mean()) if len(daily) else 0.0
    seas = daily.groupby(["Tractor_Model", "Warehouse_Location", "month"]
                       ).Demand_Units.mean().to_dict() if o_overall and len(daily) else {}
    series = {}
    for (m, w), g in daily.groupby(["Tractor_Model", "Warehouse_Location"]) if len(daily) else []:
        g = g.sort_values("Date")
        t = (g.Date - g.Date.min()).dt.days.to_numpy().tolist()
        y = g.Demand_Units.to_numpy().tolist()
        series[(m, w)] = {"t": t,
                          "y": y,
                          "t0": g.Date.min(),
                          "base": float(sum(y) / len(y)) if y else 0.0}
    f_overall = float(events.Demand_Units.mean()) if len(events) else 0.0
    pairs = [(float(d), float(m)) for d, m in zip(events.Demand_Units.tolist(),
                                                  events.Market_Trend_Index.tolist())] if len(events) else []
    return {"o_overall": o_overall,
            "o_seasonal": {k: float(v) for k, v in seas.items()},
            "o_series": series,
            "f_overall": f_overall,
            "f_pairs": pairs,
            "total_demand": tot_d,
            "total_backlog": tot_b,
            "text": f"demand {tot_d:.0f}, backlog {tot_b:.0f}, fill {fill:.3f}"}
