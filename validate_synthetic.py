"""
Validate synthetic output vs reference CSV + locked spec.

Checks (FAIL stops nothing; all results printed, exit 1 if any FAIL):
  counts, nulls, uuid uniqueness + FK integrity, bounds, means within 10%
  of reference (delay/failure exempted note: tiered means ~14.2/~0.05),
  categorical balance 18-22%, backorder<=demand, plan>=demand+backorder,
  cost within 0.5-2x base, inventory >= 0.

Usage: python validate_synthetic.py [--ref data/<csv>] [--synth data/synthetic_output]
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

PART_BASE = {"ENG-01": 4500, "TRN-02": 2800, "HYD-03": 1200,
             "ELEC-04": 800, "CHS-05": 1500}
results = []


def check(name: str,
          ok: bool,
          detail: str = "") -> None:
    """
    Record and print one validation check result.

    Args:
        name: human-readable check label.
        ok: whether the check passed.
        detail: optional supporting numbers shown after the label.
    """
    results.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


def main(ref: str | Path,
         synth: str | Path) -> None:
    """
    Validate synthetic output against the reference CSV and locked spec.

    Runs count, null, key-integrity, bound, mean-tolerance, balance, and
    consistency checks, printing PASS/FAIL per check plus expected
    by-design diffs. Exits nonzero when any check fails.

    Args:
        ref: path to the reference example CSV.
        synth: directory containing events.csv and parts.csv.
    """
    ref = pd.read_csv(ref)
    ev = pd.read_csv(Path(synth) / "events.csv")
    pa = pd.read_csv(Path(synth) / "parts.csv")

    check("event count ~10k", 9500 <= len(ev) <= 10500, f"n={len(ev)}")
    check("child rows = 5x events", len(pa) == 5 * len(ev),
          f"parts={len(pa)}")
    check("no nulls", not ev.isna().any().any() and not pa.isna().any().any())
    check("uuid unique (parent)", ev.uuid.is_unique)
    check("FK integrity", set(pa.uuid) <= set(ev.uuid),
          f"orphans={len(set(pa.uuid) - set(ev.uuid))}")

    # bounds
    check("demand 50-499", ev.Demand_Units.between(50, 499).all(),
          f"min={ev.Demand_Units.min()} max={ev.Demand_Units.max()}")
    check("delay 0-29", pa.Supplier_Delay_Days.between(0, 29).all())
    check("failure 0-0.10", pa.Component_Failure_Rate.between(0, 0.10).all())
    check("inflation 1.5-6", ev.Inflation_Rate.between(1.5, 6).all())
    check("market 0-1", ev.Market_Trend_Index.between(0, 1).all())
    check("inventory >= 0", (pa.Inventory_Levels >= 0).all(),
          f"mean={pa.Inventory_Levels.mean():.0f} (ref ~2562; scale break by design)")
    ok_cost = all((pa[pa.Part_SKU == p].Unit_Cost.between(0.5 * b, 2.0 * b)).all()
                  for p, b in PART_BASE.items())
    check("cost within 0.5-2x base", ok_cost)
    check("backorder 0..demand", ((ev.Backorder_Qty >= 0)
                                  & (ev.Backorder_Qty <= ev.Demand_Units)).all(),
          f"mean={ev.Backorder_Qty.mean():.1f}")
    check("plan >= demand+backorder",
          (ev.Production_Plan_Qty >= ev.Demand_Units + ev.Backorder_Qty).all())

    # means within 10% of reference (delay/failure tiered by design, same targets)
    for col, tol_note in [("Demand_Units", ""), ("Supplier_Delay_Days", ""),
                          ("Component_Failure_Rate", ""), ("Inflation_Rate", ""),
                          ("Market_Trend_Index", "")]:
        r = ref[col].mean()
        s = (ev if col in ev else pa)[col].mean()
        ok = abs(s - r) / max(abs(r), 1e-9) <= 0.10
        check(f"mean {col} ~ref", ok, f"ref={r:.3f} synth={s:.3f}")

    # categorical balance 18-22% (5 cats each)
    for col, df in [("Tractor_Model", ev), ("Supplier", ev),
                    ("Warehouse_Location", ev)]:
        shares = df[col].value_counts(normalize=True)
        ok = ((shares >= 0.18) & (shares <= 0.22)).all()
        check(f"balance {col}", ok,
              f"range={shares.min():.3f}-{shares.max():.3f}")

    # date range
    check("date range 2020-2023",
          ev.Date.min() >= "2020-01-01" and ev.Date.max() <= "2023-12-30",
          f"{ev.Date.min()}..{ev.Date.max()}")

    print("\nBy-design diffs (expected, not failures): seasonality/trend in demand, "
          "supplier/part tiers, delay->backlog linkage, stateful inventory, cost drift, "
          "part-units inventory scale.")
    fails = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(fails)}/{len(results)} passed.")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref",
                    default=Path(__file__).resolve().parent / "data" / "Senior Agentic Engineer Technical Interview Synthetic_Supply_Chain_Dataset.csv")
    ap.add_argument("--synth", default=Path(__file__).resolve().parent / "data" / "synthetic_output")
    a = ap.parse_args()
    main(a.ref, a.synth)
