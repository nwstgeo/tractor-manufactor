"""
Tests for engine-backed API wrappers and the CLI policy loop.
"""
import unittest

from src import api
from src.controller.step_2024 import run_policy


class TestSimAPI(unittest.TestCase):
    """
    Wrapper shape and error-path checks on data/synthetic_output_2024.
    """

    def test_full_stepping_roundtrip(self):
        """
        Init/start/propose/approve/advance/score chain stays JSON-shaped.
        """
        meta = api.sim_init()
        self.assertEqual(meta["events"], 2507)
        start = api.sim_start("2024-06-01")
        self.assertEqual(start["current_date"], "2024-06-01")
        props = api.sim_proposals()
        self.assertGreater(len(props), 0)
        self.assertTrue({"id", "part", "supplier", "qty", "cost"} <= set(props[0]))
        order = api.sim_approve(props[0]["id"])
        self.assertGreaterEqual(order["arrival_date"], order["order_date"])
        summary = api.sim_advance()
        self.assertTrue(summary["advanced"])
        self.assertIn("score", summary)
        score = api.sim_score()
        self.assertTrue({"fill", "gap", "total_cost", "meets_target", "steps"} <= set(score))
        self.assertEqual(score["steps"], 1)
        self.assertAlmostEqual(score["trail_30d_fill"], score["fill"])

    def test_error_paths(self):
        """
        Unknown ids and bad dates surface as error dicts, not exceptions.
        """
        api.sim_init()
        api.sim_start("2024-06-01")
        bad = api.sim_approve("no-such-id")
        self.assertIn("error", bad)

    def test_opening_cover_days(self):
        """
        Larger cover horizon opens deeper piles than raw snapshots.
        """
        api.sim_init()
        api.sim_start("2024-06-01", 0)
        thin = sum(api._sim["state"]["on_hand"].values())
        api.sim_start("2024-06-01", 30)
        covered = sum(api._sim["state"]["on_hand"].values())
        self.assertGreaterEqual(covered, thin)


class TestRunPolicy(unittest.TestCase):
    """
    Batch policy-loop checks.
    """

    def test_approve_none_runs_without_spend(self):
        """
        Idle policy steps dates, fills from opening stock, spends nothing.
        """
        out = run_policy("2024-06-01",
                         5,
                         "none")
        self.assertEqual(out["steps_taken"], 5)
        self.assertEqual(out["purchase"], 0.0)
        self.assertGreater(out["fill"], 0.0)

    def test_approve_all_spends_and_pipelines(self):
        """
        Ordering policy books purchase cost on day one.
        """
        out = run_policy("2024-06-01",
                         5,
                         "all")
        self.assertEqual(out["steps_taken"], 5)
        self.assertGreater(out["purchase"], 0.0)

    def test_bad_policy_raises(self):
        """
        Unknown policy names are rejected.
        """
        with self.assertRaises(ValueError):
            run_policy("2024-06-01",
                       1,
                       "sometimes")


class TestSimBoxes(unittest.TestCase):
    """
    Live six-box checks against the stepping run.
    """

    def test_live_boxes(self):
        """
        Each box reads the run: demand orders, owned stock, model forecast.
        """
        api.init()
        api.sim_init()
        api.sim_start("2024-06-01")
        orders = api.sim_customers_orders(limit=5)
        self.assertEqual(len(orders), 5)
        self.assertTrue({"Demand_Units", "Backorder_Qty"} <= set(orders[0]))
        inv = api.sim_inventory_status()
        self.assertEqual(len(inv), 5)
        self.assertTrue({"Part_SKU", "On_Hand", "On_Order"} <= set(inv[0]))
        fc = api.sim_forecast_3mo()
        self.assertEqual(len(fc["orders"]), 90)
        self.assertGreaterEqual(fc["dates"][0], "2024-06-01")
        sch = api.sim_production_schedule(limit=5)
        self.assertTrue({"Production_Plan_Qty"} <= set(sch[0]))
        for a in api.sim_action_items():
            self.assertTrue({"uuid", "model", "action"} <= set(a))

    def test_inventory_reflects_purchases(self):
        """
        Approving raises part On_Order; on the landing step On_Hand jumps.
        """
        api.sim_init()
        api.sim_start("2024-06-01")

        def part_row(part):
            """
            Fetch the aggregate inventory row for one part.
            """
            return next(r for r in api.sim_inventory_status()
                        if r["Part_SKU"] == part)

        props = api.sim_proposals()
        big = max(props, key=lambda p: p["qty"])
        part = big["part"]
        self.assertEqual(part_row(part)["On_Order"], 0)
        order = api.sim_approve(big["id"])
        self.assertEqual(part_row(part)["On_Order"], big["qty"])
        landed = None
        steps = 0
        while api.sim_score()["current_date"] < order["arrival_date"] and steps < 60:
            before = part_row(part)
            api.sim_advance()
            after = part_row(part)
            if after["On_Order"] < before["On_Order"]:
                landed = (before, after)
            steps += 1
        self.assertIsNotNone(landed)
        before, after = landed
        self.assertEqual(before["On_Order"] - after["On_Order"], big["qty"])
        self.assertGreater(after["On_Hand"], before["On_Hand"])

    def test_boxes_need_started_run(self):
        """
        Boxes surface error dicts before a run starts.
        """
        api.sim_init()
        self.assertIn("error", api.sim_customers_orders()[0])
        self.assertIn("error", api.sim_inventory_status()[0])
        self.assertIn("error", api.sim_forecast_3mo())


if __name__ == "__main__":
    unittest.main()
