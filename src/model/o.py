"""
O: Overall Demand Prediction (seasonal naive + linear trend).
"""
import numpy as np
import pandas as pd


# Replaced by src/agents/order_feedback.py (supplies overall, seasonal means, series).
# def _data_for_fit(daily: pd.DataFrame) -> tuple:
#     """
#     Extract plain inputs needed by fit from the daily demand frame.
#
#     Args:
#         daily: DataFrame with Date, Tractor_Model, Warehouse_Location,
#             Demand_Units (one row per day, e.g. from data.demand_daily).
#
#     Returns:
#         Tuple (overall, seasonal_means, series): overall mean float,
#         per (model, warehouse, month) mean dict, and per (model, warehouse)
#         history dict with time/demand points, origin, and base.
#     """
#     df = daily.copy()
#     df["month"] = df.Date.dt.month
#     overall = float(df.Demand_Units.mean())
#     seasonal_means = (df.groupby(["Tractor_Model", "Warehouse_Location", "month"]
#                                  ).Demand_Units.mean().to_dict())
#     series = {}
#     for (m, w), g in df.groupby(["Tractor_Model", "Warehouse_Location"]):
#         g = g.sort_values("Date")
#         t = (g.Date - g.Date.min()).dt.days.to_numpy().tolist()
#         y = g.Demand_Units.to_numpy().tolist()
#         series[(m, w)] = {"t": t,
#                           "y": y,
#                           "t0": g.Date.min(),
#                           "base": float(sum(y) / len(y)) if y else 0.0}
#     return (overall,
#             {k: float(v) for k, v in seasonal_means.items()},
#             series)


def fit(overall: float,
        seasonal_means: dict,
        series: dict) -> dict:
    """
    Fit seasonal indices and linear trends per Model x Warehouse.

    Args:
        overall: overall mean demand across the training window.
        seasonal_means: dict (model, warehouse, month) -> mean demand.
        series: dict (model, warehouse) -> history dict with time/demand
            points, origin, and base (associated histories kept together).

    Returns:
        Model dict with overall mean, (model, warehouse, month) seasonal
        multipliers, and per-series slope/base/origin for the trend.
    """
    seas = {k: v / overall for k, v in seasonal_means.items()}
    # linear trend per Model x Warehouse (units per day)
    trends = {}
    for (m, w), s in series.items():
        slope = float(np.polyfit(s["t"], s["y"], 1)[0]) if len(s["y"]) > 1 else 0.0
        trends[(m, w)] = {"slope": slope, "t0": s["t0"], "base": s["base"]}
    return {"overall": float(overall), "seasonal": seas, "trends": trends}


def forecast(model: dict,
             dates: pd.Series | list | pd.DatetimeIndex,
             m: str,
             w: str) -> pd.Series:
    """
    Forecast demand for a Model x Warehouse over given dates.

    Args:
        model: fitted dict from fit().
        dates: iterable of dates to forecast.
        m: tractor model string.
        w: warehouse string.

    Returns:
        Series of non-negative forecasted demand values.
    """
    dates = pd.to_datetime(pd.Series(dates))
    out = []
    for d in dates:
        seas = model["seasonal"].get((m, w, d.month), 1.0)
        tr = model["trends"][(m, w)]
        t = (d - tr["t0"]).days
        out.append(max(0.0, tr["base"] * seas + tr["slope"] * t))
    return pd.Series(out, index=dates.index)


def mae(y_true: np.ndarray | list | pd.Series,
        y_pred: np.ndarray | list | pd.Series) -> float:
    """
    Compute mean absolute error between aligned true and predicted values.

    Args:
        y_true: array-like of observed values.
        y_pred: array-like of predicted values.

    Returns:
        MAE as float.
    """
    y_true = np.asarray(y_true, float)
    y_pred = np.asarray(y_pred, float)
    return float(np.mean(np.abs(y_true - y_pred)))
