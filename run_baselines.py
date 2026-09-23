"""
Fit baselines, evaluate on 2023 holdout, smoke-test the API backend."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import api, data as D
from src.agents import order_feedback as AG_ord
from src.agents import supply_delay_trends as AG_del
from src.model import f as F
from src.model import h as H
from src.model import o as O
from src.model import r as R
from src.model import s as S

st = api.init()
events, parts, flat = st["events"], st["parts"], st["flat"]
(tr_e, tr_p, tr_f), (ho_e, ho_p, ho_f) = D.split(events, parts, flat)

# Agents supply model inputs; models never read frames directly.
ag_orders = AG_ord.summarize(tr_e)
ag_delays = AG_del.summarize(tr_f)

# O: forecast holdout demand daily per Model x Warehouse, MAE over daily means
daily_ho = D.demand_daily(ho_e)
o_model = O.fit(ag_orders["o_overall"],
                ag_orders["o_seasonal"],
                ag_orders["o_series"])
errs, n = 0.0, 0
for (m, w), g in daily_ho.groupby(["Tractor_Model", "Warehouse_Location"]):
    if (m, w) not in o_model["trends"]:
        continue
    pred = O.forecast(o_model, g.Date, m, w)
    errs += float((g.Demand_Units.to_numpy() - pred.to_numpy()).__abs__().mean())
    n += 1
print(f"O seasonal-naive+trend MAE (daily demand, holdout avg over {n} series): {errs / max(n, 1):.1f}")

# S: delay p50 MAE on holdout
s_model = S.fit_flat(ag_delays["delays_by_supplier"])
s_actual = [float(v) for v in ho_f.Supplier_Delay_Days.tolist()]
s_pred = [float(s_model["p50"][s]) for s in ho_f.Supplier.tolist()]
print(f"S supplier-p50 delay MAE (holdout): {S.mae(s_actual, s_pred):.2f} days")
print(f"  learned p50 by supplier: { {k: round(v, 1) for k, v in s_model['p50'].items()} }")

# F: regime multipliers
f_model = F.fit(ag_orders["f_overall"],
                ag_orders["f_pairs"])
print(f"F macro multipliers: { {k: round(v, 3) for k, v in f_model['multiplier'].items()} }")

# H: example net-need + bottleneck on latest TX-500/CA snapshot
frow = flat[(flat.Tractor_Model == "TX-500") & (flat.Warehouse_Location == "CA")].sort_values("Date").tail(5)
inv = {r.Part_SKU: int(r.Inventory_Levels) for _, r in frow.iterrows()}
print(f"H limiting part (latest TX-500/CA): {H.limiting_part(inv)} stock={inv}")
ex = frow.iloc[-1]
need = H.net_need(int(ex.Production_Plan_Qty), int(ex.Backorder_Qty),
                  H.spares(int(ex.Demand_Units), float(ex.Component_Failure_Rate)),
                  int(ex.Inventory_Levels), 0)
print(f"H net need example: plan={ex.Production_Plan_Qty} backlog={ex.Backorder_Qty} "
      f"on_hand={ex.Inventory_Levels} -> net={need}")

# R: fill rate on holdout + proposal sample
ag_ho = AG_ord.summarize(ho_e)
print(f"R observed fill rate (holdout): {R.fill_rate(ag_ho['total_demand'], ag_ho['total_backlog']):.4f} (target >= 0.98)")
props = api.proposed_orders()
print(f"R sample proposals ({len(props)} lines): {props[:3]}")
print(f"API smoke: orders={len(api.customers_orders())} "
      f"forecast_pts={len(api.forecast_3mo()['orders'])} "
      f"actions={len(api.action_items())} "
      f"inventory={len(api.inventory_status())} "
      f"schedule={len(api.production_schedule())}")
print(api.approve_proposal("demo-001"))
print("BASELINES OK")
