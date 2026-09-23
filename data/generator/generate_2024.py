"""
Seeded 2024 extension for interactive stepping (locked_spec_v1 + 2024 addon).

Emits chronologically ordered snapshots at the same sampling frequency as
the 2020-2023 output (~6.85 events/day), continuing demand trend (+2%/yr),
macro, and cost drift from end-2023 levels. Opening on-hand per Model x
Warehouse x Part is seeded from the latest 2020-2023 flat rows.

Usage: python data/generator/generate_2024.py [--seed 2024] [--n-events 2507] [--out data/synthetic_output_2024]
Requires: numpy, pandas.
"""
import argparse
import uuid
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent

from generate_synthetic import DELAY_MEAN
from generate_synthetic import FAIL_TIER
from generate_synthetic import LEAD
from generate_synthetic import MARKUP
from generate_synthetic import MODEL_BASE
from generate_synthetic import MODELS
from generate_synthetic import PART_BASE
from generate_synthetic import PARTS
from generate_synthetic import SUPPLIERS
from generate_synthetic import WAREHOUSES
from generate_synthetic import WH_MULT
from generate_synthetic import seasonal


def main(seed: int = 2024,
         n_events: int = 2507,
         out: str | Path = DATA_DIR / "synthetic_output_2024",
         base: str | Path = DATA_DIR / "synthetic_output") -> None:
    """
    Generate the 2024 extension and write events/parts/flat CSVs in date order.

    Runs a daily base-stock simulation for 2024-01-01..2024-12-31 opened
    from end-2023 state, then samples parent snapshots with 5 child rows
    each, sorted chronologically for date-stepping.

    Args:
        seed: RNG seed for full reproducibility (independent stream from base).
        n_events: number of parent event rows (~6.85/day matches base rate).
        out: output directory for events.csv, parts.csv, flat_view.csv.
        base: directory holding the 2020-2023 output used for opening state.
    """
    rng = np.random.default_rng(seed)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    base = Path(base)

    prev_e = pd.read_csv(base / "events.csv", parse_dates=["Date"])
    prev_f = pd.read_csv(base / "flat_view.csv", parse_dates=["Date"])

    days = pd.date_range("2024-01-01", "2024-12-31", freq="D")
    n_days = len(days)  # 366
    doy = days.dayofyear.to_numpy()

    # --- Opening state from end-2023 ---
    dec_e = prev_e[prev_e.Date >= "2023-12-01"]
    infl0 = float(dec_e.sort_values("Date").Inflation_Rate.iloc[-1])
    open_inv = {}
    for m in MODELS:
        for w in WAREHOUSES:
            for p in PARTS:
                g = prev_f[(prev_f.Tractor_Model == m)
                           & (prev_f.Warehouse_Location == w)
                           & (prev_f.Part_SKU == p)].sort_values("Date")
                open_inv[(m, w, p)] = int(g.Inventory_Levels.iloc[-1]) if len(g) else 0
    dec_f = prev_f[prev_f.Date >= "2023-12-01"]
    cost_level = {}
    for p in PARTS:
        g = dec_f[dec_f.Part_SKU == p]
        if len(g):
            ratios = [r.Unit_Cost / (PART_BASE[p] * (1 + MARKUP[r.Supplier]))
                      for r in g.itertuples()]
            cost_level[p] = float(np.median(ratios))
        else:
            cost_level[p] = 1.0

    # --- Macro series: monthly inflation AR(1) from Dec-2023; daily market uniform ---
    months = pd.period_range("2024-01", "2024-12", freq="M")
    infl_m = np.empty(len(months))
    v = infl0
    for i in range(len(months)):
        v = 0.9 * v + 0.1 * 3.75 + rng.normal(0, 0.3)
        v = float(np.clip(v, 1.5, 6.0))
        infl_m[i] = round(v, 2)
    infl_map = dict(zip(months.astype(str), infl_m))
    infl_daily = np.array([infl_map[str(pd.Period(d, freq="M"))] for d in days])
    market_daily = np.round(rng.uniform(0, 1, n_days), 2)

    # --- Cost drift index per part: monthly RW from Dec-2023 level ---
    cost_idx = {}
    for p in PARTS:
        f = np.empty(len(months))
        f[0] = cost_level[p]
        for i in range(1, len(months)):
            d_inf = (infl_m[i] - infl_m[i - 1]) / 100.0
            f[i] = f[i - 1] * (1 + rng.normal(0, 0.01)) * (1 + 0.5 * d_inf)
        cost_idx[p] = dict(zip(months.astype(str), f))
    month_of_day = np.array([str(pd.Period(d, freq="M")) for d in days])

    # --- Daily demand per Model x Warehouse, trend continued (+2%/yr) ---
    dem = {}
    for m in MODELS:
        for w in WAREHOUSES:
            base_v = MODEL_BASE[m] * WH_MULT[w]
            trend = 1.0 + 0.02 * (2024 - 2020)
            noise = 1.0 + rng.uniform(-0.15, 0.15, n_days)
            vals = np.round(base_v * seasonal(doy) * trend * noise).astype(int)
            dem[(m, w)] = np.clip(vals, 50, 499)

    # --- Stateful inventory sim opened from end-2023 on-hand ---
    sup_idx = rng.integers(0, 5, size=(len(MODELS), len(WAREHOUSES), n_days))
    on_hand = {(m, w, p): np.zeros(n_days, dtype=int)
               for m in MODELS for w in WAREHOUSES for p in PARTS}
    for mi, m in enumerate(MODELS):
        for wi, w in enumerate(WAREHOUSES):
            for p in PARTS:
                pipe = {}
                oh = open_inv[(m, w, p)]
                ft = FAIL_TIER[p]
                for t in range(n_days):
                    s = SUPPLIERS[sup_idx[mi, wi, t]]
                    oh += pipe.pop(t, 0)
                    need = int(dem[(m, w)][t])
                    use = min(need, oh)
                    fall = rng.binomial(use, min(max(ft, 0.0), 1.0))
                    oh -= min(oh, use + fall)
                    horizon = LEAD[s] + 7
                    fut = dem[(m, w)][t: t + horizon]
                    fcast = float(fut.mean()) if len(fut) else float(dem[(m, w)][t])
                    target = int(fcast * horizon * (1 + 0.10 + 2 * ft))
                    position = oh + sum(pipe.values())
                    order = max(0, target - position)
                    if order > 0:
                        dl = int(np.clip(
                            rng.integers(-7, 8) + DELAY_MEAN[s], 0, 29))
                        pipe[t + LEAD[s] + dl] = pipe.get(t + LEAD[s] + dl, 0) + order
                    on_hand[(m, w, p)][t] = oh

    # --- Sample snapshots across day/model/warehouse + random supplier ---
    grid = [(t, mi, wi) for t in range(n_days)
            for mi in range(len(MODELS)) for wi in range(len(WAREHOUSES))]
    pick = rng.choice(len(grid), size=n_events, replace=False)
    sup_pick = rng.integers(0, 5, size=n_events)

    erows, prows = [], []
    for k, gi in enumerate(pick):
        t, mi, wi = grid[gi]
        m, w = MODELS[mi], WAREHOUSES[wi]
        s = SUPPLIERS[sup_pick[k]]
        d = dem[(m, w)][t]
        dm = DELAY_MEAN[s]
        delays = [int(np.clip(rng.integers(-7, 8) + dm, 0, 29)) for _ in PARTS]
        fails = [round(float(np.clip(
            rng.uniform(-0.02, 0.02) + FAIL_TIER[p], 0, 0.10)), 3) for p in PARTS]
        mean_dl = float(np.mean(delays))
        mean_f = float(np.mean(fails))
        p = min(0.03 + 0.003 * mean_dl, 0.35)
        bo = int(rng.binomial(int(d), p))
        plan = int(d) + bo + int(round(
            float(d) * (0.10 + 2 * mean_f) * (1 + rng.uniform(-0.05, 0.05))))
        eid = str(uuid.UUID(bytes=rng.bytes(16)))
        date = str(days[t].date())
        erows.append([eid, date, m, w, s, int(d), bo, max(plan, 0),
                      infl_daily[t], market_daily[t]])
        mstr = month_of_day[t]
        for j, part in enumerate(PARTS):
            inv = int(on_hand[(m, w, part)][t])
            raw = PART_BASE[part] * (1 + MARKUP[s]) * cost_idx[part][mstr] \
                * (1 + rng.normal(0, 0.02))
            lo, hi = 0.5 * PART_BASE[part], 2.0 * PART_BASE[part]
            cost = int(round(float(np.clip(raw, lo, hi))))
            prows.append([eid, part, delays[j], fails[j], inv, cost])

    events = pd.DataFrame(erows, columns=[
        "uuid", "Date", "Tractor_Model", "Warehouse_Location", "Supplier",
        "Demand_Units", "Backorder_Qty", "Production_Plan_Qty",
        "Inflation_Rate", "Market_Trend_Index"])
    events = events.sort_values(["Date", "Tractor_Model", "Warehouse_Location",
                                 "Supplier"]).reset_index(drop=True)
    parts = pd.DataFrame(prows, columns=[
        "uuid", "Part_SKU", "Supplier_Delay_Days", "Component_Failure_Rate",
        "Inventory_Levels", "Unit_Cost"])
    flat = events.merge(parts, on="uuid", suffixes=("", "_part"))
    events.to_csv(out / "events.csv", index=False)
    parts.to_csv(out / "parts.csv", index=False)
    flat.to_csv(out / "flat_view.csv", index=False)
    print(f"seed={seed} events={len(events)} parts={len(parts)} "
          f"flat={len(flat)} -> {out}")
    print(f"date range {events.Date.min()}..{events.Date.max()} "
          f"rate={len(events) / n_days:.2f}/day")
    print(f"demand mean={events.Demand_Units.mean():.1f} "
          f"backorder mean={events.Backorder_Qty.mean():.1f} "
          f"delay mean={parts.Supplier_Delay_Days.mean():.2f} "
          f"inv mean={parts.Inventory_Levels.mean():.0f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=2024)
    ap.add_argument("--n-events", type=int, default=2507)
    ap.add_argument("--out", default=DATA_DIR / "synthetic_output_2024")
    ap.add_argument("--base", default=DATA_DIR / "synthetic_output")
    a = ap.parse_args()
    main(seed=a.seed, n_events=a.n_events, out=a.out, base=a.base)
