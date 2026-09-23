"""
Tractor Failure Compilation agent (supplies H failure rates).
"""
import pandas as pd


def summarize(parts: pd.DataFrame,
              top_n: int = 3) -> dict:
    """
    Supply per-part failure means for H.spares.

    Args:
        parts: child part rows with Part_SKU and Component_Failure_Rate.
        top_n: retained for API stability; rankings are not supplied.

    Returns:
        Dict with overall_mean, by_part means, and a text summary.
    """
    means = parts.groupby("Part_SKU").Component_Failure_Rate.mean().to_dict()
    overall = float(parts.Component_Failure_Rate.mean()) if len(parts) else 0.0
    return {"overall_mean": overall,
            "by_part": {k: float(v) for k, v in means.items()},
            "text": f"overall failure {overall:.3f}"}
