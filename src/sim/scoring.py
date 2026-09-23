"""
Forward fill/cost scoring for stepped runs.

Compares engine-owned cumulative outcomes against the R fill target.
All inputs are plain scalars/lists; no DataFrame reads.
"""
from ..model import r as R

HOLDING_PER_UNIT_DEFAULT = 1.0


def score(filled: float,
          unfilled: float,
          spent: float,
          holding: float,
          target: float = R.FILL_TARGET) -> dict:
    """
    Score cumulative run outcomes against the fill target.

    Args:
        filled: filled part-units to date.
        unfilled: unfilled part-units to date.
        spent: purchase cost to date.
        holding: accrued holding cost to date.
        target: fill-rate target (default R 0.98).

    Returns:
        Dict with fill, gap to target, cost breakdown, and verdict.
    """
    total = float(filled) + float(unfilled)
    fill = R.fill_rate(total,
                       float(unfilled))
    total_cost = float(spent) + float(holding)
    return {"fill": fill,
            "target": float(target),
            "gap": float(target) - fill,
            "purchase": float(spent),
            "holding": float(holding),
            "total_cost": total_cost,
            "cost_per_filled": total_cost / float(filled) if filled else 0.0,
            "meets_target": fill >= float(target)}


def window_fill(history: list,
                n: int = 30) -> dict:
    """
    Fill rate over the trailing steps of run history.

    Args:
        history: per-step entries with need and filled keys.
        n: number of trailing steps to include.

    Returns:
        Dict with steps used, need, filled, and fill rate.
    """
    tail = history[-n:] if n > 0 else []
    need = sum(float(e.get("need", 0)) for e in tail)
    filled = sum(float(e.get("filled", 0)) for e in tail)
    return {"steps": len(tail),
            "need": need,
            "filled": filled,
            "fill": R.fill_rate(need,
                                need - filled)}
