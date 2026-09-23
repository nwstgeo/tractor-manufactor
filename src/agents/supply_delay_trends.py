"""
Supply Delay Trends agent (supplies S delay histories).
"""
import pandas as pd


def summarize(flat: pd.DataFrame,
              top_n: int = 5) -> dict:
    """
    Supply per-supplier delay histories for S.fit_flat.

    Args:
        flat: joined rows with Supplier and Supplier_Delay_Days.
        top_n: retained for API stability; ranking is not supplied
            (S needs histories only).

    Returns:
        Dict with delays_by_supplier histories and a text summary.
    """
    hists = {s: [float(v) for v in g.Supplier_Delay_Days.tolist()]
             for s, g in flat.groupby("Supplier")}
    med = float(flat.Supplier_Delay_Days.median()) if len(flat) else 0.0
    return {"delays_by_supplier": hists,
            "text": f"overall median delay {med:.1f}d"}
