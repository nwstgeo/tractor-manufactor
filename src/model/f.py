"""
F: Forecasting Overall Market, indicator mode (macro-conditioned scaling).
"""
# This model does not functionally do anything, as its overall market forecasting is out of scope.
# It's been kept in as an example of possible implementation.

import pandas as pd


def _bin(market: float) -> str:
    """
    Bin a market-trend index into a low/mid/high regime label.

    Args:
        market: Market_Trend_Index value in [0, 1].

    Returns:
        'low' (<0.33), 'high' (>0.66), else 'mid'.
    """
    if market < 0.33:
        return "low"
    if market > 0.66:
        return "high"
    return "mid"


# Replaced by src/agents/order_feedback.py (supplies overall and pairs).
# def _data_for_fit(events_train: pd.DataFrame) -> tuple:
#     """
#     Extract plain demand/market inputs needed by fit.
#
#     Args:
#         events_train: training event rows with Demand_Units and
#             Market_Trend_Index.
#
#     Returns:
#         Tuple (overall, pairs): overall mean demand float and list of
#         (demand, market) pairs with association kept together.
#     """
#     return (float(events_train.Demand_Units.mean()),
#             [(float(d), float(m)) for d, m in zip(events_train.Demand_Units.tolist(),
#                                                   events_train.Market_Trend_Index.tolist())])


def fit(overall: float,
        pairs: list) -> dict:
    """
    Fit per-regime demand multipliers from training events.

    Args:
        overall: overall mean demand across the training window.
        pairs: list of (demand, market) pairs with association kept together.

    Returns:
        Dict with a multiplier per market regime (low/mid/high).
    """
    sums = {}
    counts = {}
    for dem, mkt in pairs:
        r = _bin(mkt)
        sums[r] = sums.get(r, 0.0) + dem
        counts[r] = counts.get(r, 0) + 1
    mult = {r: (sums[r] / counts[r]) / overall for r in sums}
    return {"multiplier": mult}


def adjust(model: dict,
           forecast_value: float,
           market_index: float) -> float:
    """
    Scale a demand forecast by the multiplier of the current regime.

    Args:
        model: fitted dict from fit().
        forecast_value: base forecast.
        market_index: current Market_Trend_Index value.

    Returns:
        Macro-adjusted forecast as float.
    """
    return float(forecast_value) * float(
        model["multiplier"].get(_bin(market_index), 1.0))
