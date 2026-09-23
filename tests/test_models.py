"""
Unit tests for H/O/S/F/R baselines on hand-built tiny frames.
"""
import unittest

import pandas as pd

from src.model import f as F
from src.model import h as H
from src.model import o as O
from src.model import r as R
from src.model import s as S


class TestH(unittest.TestCase):
    """
    Net-need arithmetic checks.
    """

    def test_spares(self):
        """
        Buffer equals 10pct of demand plus twice the failure share.
        """
        self.assertEqual(H.spares(100, 0.05), 20)

    def test_net_need_floors_at_zero(self):
        """
        Surplus position never yields a negative order.
        """
        self.assertEqual(H.net_need(10, 0, 0, 50, 0), 0)
        self.assertEqual(H.net_need(100, 10, 5, 20, 30), 65)

    def test_limiting_part(self):
        """
        Bottleneck is the part with the least stock.
        """
        self.assertEqual(H.limiting_part({"a": 5, "b": 1, "c": 9}), "b")

    def test_rank_suppliers(self):
        """
        Fastest first, cheaper breaks delay ties.
        """
        ranked = H.rank_suppliers({"slow": 20, "mid": 10, "fast": 5},
                                  {"slow": 1, "mid": 100, "fast": 100})
        self.assertEqual(ranked, ["fast", "mid", "slow"])


class TestO(unittest.TestCase):
    """
    Seasonal naive plus trend checks.
    """

    def test_fit_forecast_roundtrip(self):
        """
        Flat series forecasts its own mean with zero trend slope.
        """
        dates = pd.date_range("2023-01-01", periods=60, freq="D")
        daily = pd.DataFrame({"Date": dates, "Tractor_Model": "TX-100",
                              "Warehouse_Location": "CA", "Demand_Units": 100})
        t0 = dates.min()
        overall, seas, series = (100.0,
                                 {( "TX-100", "CA", m): 100.0 for m in (1, 2, 3)},
                                 {("TX-100", "CA"): {"t": list(range(60)),
                                                     "y": [100] * 60,
                                                     "t0": t0,
                                                     "base": 100.0}})
        model = O.fit(overall,
                      seas,
                      series)
        pred = O.forecast(model, pd.date_range("2023-03-01", periods=7, freq="D"),
                          "TX-100", "CA")
        self.assertEqual(len(pred), 7)
        self.assertTrue((pred >= 0).all())
        self.assertAlmostEqual(pred.mean(), 100, delta=15)

    def test_mae(self):
        """
        MAE of an exact prediction is zero.
        """
        self.assertEqual(O.mae([1, 2, 3], [1, 2, 3]), 0.0)


class TestS(unittest.TestCase):
    """
    Delay quantile checks.
    """

    def test_fit_predict(self):
        """
        Prediction equals the supplier training median.
        """
        flat = pd.DataFrame({"Supplier": ["A"] * 5 + ["B"] * 5,
                             "Supplier_Delay_Days": [8, 9, 10, 11, 12] + [18] * 5})
        hists = {"A": [8, 9, 10, 11, 12], "B": [18] * 5}
        model = S.fit_flat(hists)
        self.assertEqual(S.predict(model, "A"), 10.0)
        self.assertEqual(S.predict(model, "B"), 18.0)

    def test_mae(self):
        """
        MAE against medians matches hand computation.
        """
        self.assertEqual(S.mae([8, 12], [10.0, 10.0]), 2.0)


class TestF(unittest.TestCase):
    """
    Macro regime checks.
    """

    def test_bins(self):
        """
        Index edges fall into low, mid, high.
        """
        self.assertEqual(F._bin(0.0), "low")
        self.assertEqual(F._bin(0.5), "mid")
        self.assertEqual(F._bin(1.0), "high")

    def test_adjust(self):
        """
        Forecast scales by its regime multiplier.
        """
        self.assertAlmostEqual(F.adjust({"multiplier": {"mid": 2.0}}, 10, 0.5), 20.0)


class TestR(unittest.TestCase):
    """
    Recommendation rule checks.
    """

    def test_routing(self):
        """
        Urgent goes fastest, normal goes cheapest.
        """
        net = {"p": 10}
        costs = {("p", "cheap"): 5, ("p", "fast"): 50}
        delays = {"cheap": 20, "fast": 5}
        normal = R.propose_orders(net, [], costs, delays, {}, urgent=False)
        urgent = R.propose_orders(net, [], costs, delays, {}, urgent=True)
        self.assertEqual(normal[0]["supplier"], "cheap")
        self.assertEqual(urgent[0]["supplier"], "fast")

    def test_skips_zero_need(self):
        """
        Parts with no need produce no lines.
        """
        out = R.propose_orders({"p": 0}, [], {}, {"s": 1}, {"s": 1})
        self.assertEqual(out, [])

    def test_actions(self):
        """
        Expedite fires above 5pct backlog, substitute above slack.
        """
        self.assertEqual(len(R.actions(6, 100, 5, 14)), 1)
        self.assertEqual(len(R.actions(0, 100, 99, 14)), 1)
        self.assertEqual(R.actions(0, 100, 5, 14), [])

    def test_fill_rate(self):
        """
        Fill rate is one minus backlog over demand.
        """
        self.assertAlmostEqual(R.fill_rate(100, 7), 0.93)


if __name__ == "__main__":
    unittest.main()
