"""
S: Supply Limitation Prediction (per-supplier delay quantiles).
"""
import numpy as np
import pandas as pd


# Replaced by src/agents/supply_delay_trends.py (supplies delays_by_supplier).
# def _data_for_fit_flat(flat_train: pd.DataFrame) -> dict:
#     """
#     Extract plain delay histories needed by fit_flat.
#
#     Args:
#         flat_train: training rows of the flat view with Supplier and
#             Supplier_Delay_Days columns.
#
#     Returns:
#         Dict mapping supplier name to its list of delay values.
#     """
#     return {s: [float(v) for v in g.Supplier_Delay_Days.tolist()]
#             for s, g in flat_train.groupby("Supplier")}


def fit_flat(delays_by_supplier: dict) -> dict:
    """
    Fit per-supplier delay quantiles from delay histories.

    Args:
        delays_by_supplier: dict supplier name -> list of delay values
            (one history per supplier).

    Returns:
        Dict with p50 and p90 delay dicts keyed by supplier name.
    """
    return {"p50": {s: float(np.median(v)) for s, v in delays_by_supplier.items()},
            "p90": {s: float(np.quantile(v, 0.9)) for s, v in delays_by_supplier.items()}}


def predict(model: dict,
            supplier: str) -> float:
    """
    Predict delay for a supplier as its training median (p50).

    Args:
        model: fitted dict from fit_flat().
        supplier: supplier name.

    Returns:
        Predicted delay in days as float.
    """
    return float(model["p50"][supplier])


# Evaluation pairs are built by the caller from holdout data and model output.
# def _data_for_mae(flat_holdout: pd.DataFrame,
#                   model: dict) -> tuple:
#     """
#     Extract plain actual/predicted pairs needed by mae.
#
#     Args:
#         flat_holdout: holdout rows with Supplier and Supplier_Delay_Days.
#         model: fitted dict from fit_flat().
#
#     Returns:
#         Tuple (actual, pred): parallel lists of actual and predicted delays.
#     """
#     actual = [float(v) for v in flat_holdout.Supplier_Delay_Days.tolist()]
#     pred = [float(model["p50"][s]) for s in flat_holdout.Supplier.tolist()]
#     return (actual,
#             pred)


def mae(actual: list,
        pred: list) -> float:
    """
    Compute MAE of p50 delay predictions on holdout flat rows.

    Args:
        actual: list of observed delays.
        pred: list of predicted delays, aligned with actual.

    Returns:
        MAE in days as float.
    """
    return float(sum(abs(a - p) for a, p in zip(actual, pred)) / max(len(actual), 1))
