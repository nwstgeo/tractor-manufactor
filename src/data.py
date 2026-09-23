"""
Shared data loading for H/O/S/F/R baselines. Reads data/synthetic_output/*.csv.
"""
from pathlib import Path

import pandas as pd

SYNTH_DIR = Path(__file__).resolve().parent.parent / "data" / "synthetic_output"
HOLDOUT_START = "2023-01-01"


def load(synth_dir: Path | str = SYNTH_DIR) -> tuple:
    """
    Load generated CSVs into DataFrames.

    Args:
        synth_dir: directory containing events.csv, parts.csv, flat_view.csv.

    Returns:
        Tuple (events, parts, flat) with Date columns parsed as datetimes.
    """
    synth_dir = Path(synth_dir)
    events = pd.read_csv(synth_dir / "events.csv", parse_dates=["Date"])
    parts = pd.read_csv(synth_dir / "parts.csv")
    flat = pd.read_csv(synth_dir / "flat_view.csv", parse_dates=["Date"])
    return events, parts, flat


def split(events: pd.DataFrame,
          parts: pd.DataFrame,
          flat: pd.DataFrame,
          holdout_start: str = HOLDOUT_START) -> tuple:
    """
    Split data into train and holdout sets at a cutoff date.

    Events/flat split on their Date column; child part rows follow their
    parent event via uuid membership (parts carry no Date of their own).

    Args:
        events: parent event rows.
        parts: child part rows.
        flat: joined view.
        holdout_start: ISO date string; rows on/after it are holdout.

    Returns:
        ((train_events, train_parts, train_flat), (holdout_events, ...)).
    """
    tr_e = events[events.Date < holdout_start].copy()
    ho_e = events[events.Date >= holdout_start].copy()
    tr_ids = set(tr_e.uuid)
    tr_p = parts[parts.uuid.isin(tr_ids)].copy()
    ho_p = parts[~parts.uuid.isin(tr_ids)].copy()
    tr_f = flat[flat.Date < holdout_start].copy()
    ho_f = flat[flat.Date >= holdout_start].copy()
    return (tr_e, tr_p, tr_f), (ho_e, ho_p, ho_f)


def demand_daily(events: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate event snapshots to one demand series per Model x Warehouse.

    Averages Demand_Units (and Backorder/Plan/macro fields) over any same-day
    supplier repeats so each Model x Warehouse has a single daily value.

    Args:
        events: parent event rows with Date, Tractor_Model, Warehouse_Location.

    Returns:
        DataFrame with one row per (Date, Tractor_Model, Warehouse_Location).
    """
    g = events.groupby(["Date", "Tractor_Model", "Warehouse_Location"],
                       as_index=False).agg(Demand_Units=("Demand_Units", "mean"),
                                           Backorder_Qty=("Backorder_Qty", "mean"),
                                           Production_Plan_Qty=("Production_Plan_Qty", "mean"),
                                           Inflation_Rate=("Inflation_Rate", "mean"),
                                           Market_Trend_Index=("Market_Trend_Index", "mean"))
    return g
