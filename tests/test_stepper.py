"""
Stepping-engine tests on the 2024 chronological stream.
"""
import unittest

import pandas as pd

from src.sim import scoring as SC
from src.sim import stepper


class TestStepper(unittest.TestCase):
    """
    Start/propose/approve/advance checks against data/synthetic_output_2024.
    """

    @classmethod
    def setUpClass(cls):
        """
        Load the engine once for the whole case.
        """
        cls.st = stepper.init()

    def test_init_loads_2024_stream(self):
        """
        Engine sees the full 2024 event stream in date order.
        """
        self.assertEqual(len(self.st["events"]), 2507)
        self.assertEqual(len(self.st["dates"]), 364)
        self.assertEqual(self.st["dates"], sorted(self.st["dates"]))

    def test_start_seeds_on_hand(self):
        """
        Starting seeds non-negative on-hand for every Model x Warehouse x Part.
        """
        summary = stepper.start(self.st,
                                "2024-01-01")
        self.assertEqual(summary["current_date"], "2024-01-01")
        self.assertGreater(summary["n_events"], 0)
        self.assertEqual(len(self.st["on_hand"]), 5 * 5)
        self.assertTrue(all(v >= 0 for v in self.st["on_hand"].values()))

    def test_propose_approve_advance(self):
        """
        Proposals are well-formed, approvals pipeline, advance steps a date.
        """
        stepper.start(self.st,
                      "2024-03-01")
        props = stepper.proposals(self.st)
        self.assertGreater(len(props), 0)
        self.assertTrue({"id", "m", "part", "supplier", "qty", "cost"} <= set(props[0]))
        order = stepper.approve(self.st,
                                props[0]["id"])
        self.assertGreaterEqual(order["arrival_date"], order["order_date"])
        self.assertEqual(len(self.st["pipeline"]), 1)
        summary = stepper.advance(self.st)
        self.assertTrue(summary["advanced"])
        self.assertGreater(summary["need"], 0)

    def test_cover_sizing(self):
        """
        Empty-shelf proposals cover lead-time demand, not one day.
        """
        st = stepper.init()
        stepper.start(st,
                      "2024-01-01")
        for k in list(st["on_hand"]):
            st["on_hand"][k] = 0
        props = stepper.proposals(st)
        self.assertGreater(len(props), 0)
        day = st["events"][st["events"].Date.dt.normalize() == st["current_date"]]
        for line in props:
            g = day[day.Tractor_Model == line["m"]]
            self.assertGreater(line["qty"], 20 * int(g.Demand_Units.sum()))

    def test_received_stock_pools_across_suppliers(self):
        """
        Arrivals from different suppliers merge into one pile.
        """
        st = stepper.init()
        stepper.start(st,
                      "2024-06-01")
        nxt = st["dates"][st["dates"].index(st["current_date"]) + 1]
        key = ("TX-500", "ENG-01")
        oh0 = st["on_hand"][key]
        st["pipeline"].append({"m": key[0], "part": key[1],
                               "supplier": "Supplier A", "qty": 100000,
                               "arrival_date": str(nxt.date())})
        st["pipeline"].append({"m": key[0], "part": key[1],
                               "supplier": "Supplier D", "qty": 100000,
                               "arrival_date": str(nxt.date())})
        summary = stepper.advance(st)
        self.assertTrue(summary["advanced"])
        day = st["events"][(st["events"].Date.dt.normalize() == nxt)
                           & (st["events"].Tractor_Model == key[0])]
        fail = float(st["fail_by_part"][key[1]])
        need = sum(int(r.Demand_Units) + round(int(r.Demand_Units) * fail)
                   for _, r in day.iterrows())
        self.assertEqual(st["on_hand"][key], oh0 + 200000 - need)
        self.assertTrue(all(len(k) == 2 for k in st["on_hand"]))

    def test_order_effects_visible(self):
        """
        An approved order visibly raises stock versus an idle run.
        """
        st_buy = stepper.init()
        st_idle = stepper.init()
        stepper.start(st_buy,
                      "2024-06-01")
        stepper.start(st_idle,
                      "2024-06-01")
        props = stepper.proposals(st_buy)
        big = max(props, key=lambda p: p["qty"])
        key = (big["m"], big["part"])
        stepper.approve(st_buy,
                        big["id"])
        arrival = pd.Timestamp(
            next(o for o in st_buy["pipeline"] if o["id"] == big["id"])["arrival_date"])
        steps = 0
        while st_buy["current_date"] < arrival and steps < 60:
            stepper.advance(st_buy)
            stepper.advance(st_idle)
            steps += 1
        self.assertGreaterEqual(st_buy["current_date"], arrival)
        self.assertFalse([o for o in st_buy["pipeline"] if o["id"] == big["id"]])
        self.assertGreaterEqual(st_buy["on_hand"][key], st_idle["on_hand"][key])
        self.assertGreaterEqual(st_buy["filled"], st_idle["filled"])


    def test_opening_cover_month(self):
        """
        Default opening cover fills the first month with no orders.
        """
        st = stepper.init()
        stepper.start(st,
                      "2024-01-01")
        for _ in range(30):
            summary = stepper.advance(st)
            if not summary.get("advanced"):
                break
        self.assertGreaterEqual(SC.window_fill(st["history"],
                                               30)["fill"], 0.99)


if __name__ == "__main__":
    unittest.main()
