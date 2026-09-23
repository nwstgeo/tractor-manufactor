"""
Seeded synthetic tractor supply-chain generator (locked_spec_v1_2026-09-23).

Emits normalized output + flat view (all seeded, no external data):
  events.csv (10k parent rows), parts.csv (~50k child rows), flat_view.csv (join).

Usage: python data/generator/generate_synthetic.py [--seed 42] [--n-events 10000] [--out data/synthetic_output]
Requires: numpy, pandas.
"""
import argparse
import uuid
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent

MODELS = ["TX-100", "TX-200", "TX-300", "TX-400", "TX-500"]
MODEL_BASE = {"TX-100": 250, "TX-200": 270, "TX-300": 260, "TX-400": 280, "TX-500": 300}
WAREHOUSES = ["CA", "FL", "IL", "NY", "TX"]
WH_MULT = {"CA": 1.10, "TX": 1.05, "FL": 1.00, "IL": 0.95, "NY": 0.90}
SUPPLIERS = ["Supplier A", "Supplier B", "Supplier C", "Supplier D", "Supplier E"]
SHORT = {"Supplier A": "A", "Supplier B": "B", "Supplier C": "C",
         "Supplier D": "D", "Supplier E": "E"}
DELAY_MEAN = {"Supplier A": 13, "Supplier B": 15, "Supplier C": 16,
              "Supplier D": 18, "Supplier E": 9}          # uniform +-7, clamp 0-29
LEAD = {"Supplier A": 10, "Supplier B": 12, "Supplier C": 14,
        "Supplier D": 18, "Supplier E": 7}                # base lead-time days
MARKUP = {"Supplier A": 0.00, "Supplier B": 0.03, "Supplier C": 0.05,
          "Supplier D": -0.02, "Supplier E": 0.08}
PARTS = ["ENG-01", "TRN-02", "HYD-03", "ELEC-04", "CHS-05"]
PART_BASE = {"ENG-01": 4500, "TRN-02": 2800, "HYD-03": 1200,
             "ELEC-04": 800, "CHS-05": 1500}
FAIL_TIER = {"ENG-01": 0.07, "ELEC-04": 0.06, "TRN-02": 0.05,
             "HYD-03": 0.04, "CHS-05": 0.03}              # uniform +-0.02, clamp 0-0.10


def seasonal(dayofyear: np.ndarray | int) -> np.ndarray | float:
    """
    Compute the seasonal demand multiplier for day(s) of year.

    Args:
        dayofyear: day-of-year number(s), 1-365/366.

    Returns:
        Multiplier peaking in spring (1.25) and troughing in autumn (0.75).
    """
    return 1.0 + 0.25 * np.sin(2 * np.pi * (dayofyear - 90) / 365.0)


def main(seed: int = 42,
         n_events: int = 10000,
         out: str | Path = DATA_DIR / "synthetic_output") -> None:
    """
    Run the seeded stateful simulator and write events/parts/flat CSVs.

    Generates macro series, seasonal demand, a daily base-stock inventory
    simulation per Model x Warehouse x Part with exogenous supplier delays,
    then samples parent snapshots with 5 child part rows each.

    Args:
        seed: RNG seed for full reproducibility.
        n_events: number of parent event rows to sample.
        out: output directory for events.csv, parts.csv, flat_view.csv.
    """
    rng = np.random.default_rng(seed)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)

    days = pd.date_range("2020-01-01", "2023-12-30", freq="D")
    n_days = len(days)  # 1460
    doy = days.dayofyear.to_numpy()
    year = days.year.to_numpy()

    # --- Macro series: monthly inflation AR(1) fwd-filled; daily market uniform ---
    months = pd.period_range("2020-01", "2023-12", freq="M")
    infl_m = np.empty(len(months))
    v = 3.0
    for i in range(len(months)):
        v = 0.9 * v + 0.1 * 3.75 + rng.normal(0, 0.3)
        v = float(np.clip(v, 1.5, 6.0))
        infl_m[i] = round(v, 2)
    infl_map = dict(zip(months.astype(str), infl_m))
    infl_daily = np.array([infl_map[str(pd.Period(d, freq="M"))] for d in days])
    market_daily = np.round(rng.uniform(0, 1, n_days), 2)

    # --- Cost drift index per part: monthly RW 1% + 0.5x inflation pass-through ---
    cost_idx = {}
    for p in PARTS:
        f = np.ones(len(months))
        for i in range(1, len(months)):
            d_inf = (infl_m[i] - infl_m[i - 1]) / 100.0
            f[i] = f[i - 1] * (1 + rng.normal(0, 0.01)) * (1 + 0.5 * d_inf)
        cost_idx[p] = dict(zip(months.astype(str), f / f[0]))
    month_of_day = np.array([str(pd.Period(d, freq="M")) for d in days])

    # --- Daily demand per Model x Warehouse (25 series) ---
    dem = {}  # (model, wh) -> int array
    for m in MODELS:
        for w in WAREHOUSES:
            base = MODEL_BASE[m] * WH_MULT[w]
            trend = 1.0 + 0.02 * (year - 2020)
            noise = 1.0 + rng.uniform(-0.15, 0.15, n_days)
            vals = np.round(base * seasonal(doy) * trend * noise).astype(int)
            dem[(m, w)] = np.clip(vals, 50, 499)

    # --- Stateful inventory sim per Model x Warehouse x Part ---
    # Supplier rotation per Model x Warehouse x Day (balanced).
    sup_idx = rng.integers(0, 5, size=(len(MODELS), len(WAREHOUSES), n_days))
    on_hand = {  # closing stock state
        (m, w, p): np.zeros(n_days, dtype=int)
        for m in MODELS for w in WAREHOUSES for p in PARTS
    }
    for mi, m in enumerate(MODELS):
        for wi, w in enumerate(WAREHOUSES):
            backlog = 0
            for p in PARTS:
                # init at target: forecast(avg lead+7d demand) x buffer
                avg_lead = float(np.mean(list(LEAD.values())))
                tgt0 = int(dem[(m, w)][: int(avg_lead) + 7].mean()
                           * (1 + 0.10 + 2 * FAIL_TIER[p]))
                pipe = {}  # arrival_day -> qty
                oh = tgt0
                ft = FAIL_TIER[p]
                for t in range(n_days):
                    s = SUPPLIERS[sup_idx[mi, wi, t]]
                    oh += pipe.pop(t, 0)
                    need = int(dem[(m, w)][t]) + backlog
                    use = min(need, oh)
                    fall = rng.binomial(use, min(max(ft, 0.0), 1.0))
                    oh -= min(oh, use + fall)
                    # base-stock order against this day's supplier lead:
                    # target ~= lead-time demand cover x buffer
                    horizon = LEAD[s] + 7
                    fut = dem[(m, w)][t: t + horizon]
                    fcast = float(fut.mean()) if len(fut) else float(dem[(m, w)][t])
                    target = int(fcast * horizon * (1 + 0.10 + 2 * ft))
                    position = oh + sum(pipe.values()) - backlog // 5
                    order = max(0, target - position)
                    if order > 0:
                        dl = int(np.clip(
                            rng.integers(-7, 8) + DELAY_MEAN[s], 0, 29))
                        pipe[t + LEAD[s] + dl] = pipe.get(t + LEAD[s] + dl, 0) + order
                    on_hand[(m, w, p)][t] = oh
                # shared backlog update per day from limiting part (approx via ENG-01 pass
                # is skipped; backlog evolves in export via locked Binomial instead).
                _ = backlog  # export-stage backlog; sim tracks availability only

    # --- Sample ~n_events snapshots across day/model/warehouse + random supplier ---
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
        eid = str(uuid.UUID(bytes=rng.bytes(16)))  # seeded, reproducible
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
    parts = pd.DataFrame(prows, columns=[
        "uuid", "Part_SKU", "Supplier_Delay_Days", "Component_Failure_Rate",
        "Inventory_Levels", "Unit_Cost"])
    flat = events.merge(parts, on="uuid", suffixes=("", "_part"))
    events.to_csv(out / "events.csv", index=False)
    parts.to_csv(out / "parts.csv", index=False)
    flat.to_csv(out / "flat_view.csv", index=False)
    print(f"seed={seed} events={len(events)} parts={len(parts)} "
          f"flat={len(flat)} -> {out}")
    print(f"demand mean={events.Demand_Units.mean():.1f} "
          f"backorder mean={events.Backorder_Qty.mean():.1f} "
          f"plan mean={events.Production_Plan_Qty.mean():.1f}")
    print(f"delay mean={parts.Supplier_Delay_Days.mean():.2f} "
          f"failure mean={parts.Component_Failure_Rate.mean():.4f} "
          f"inv mean={parts.Inventory_Levels.mean():.0f} "
          f"cost mean={parts.Unit_Cost.mean():.0f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n-events", type=int, default=10000)
    ap.add_argument("--out", default=DATA_DIR / "synthetic_output")
    a = ap.parse_args()
    main(seed=a.seed, n_events=a.n_events, out=a.out)
