"""
Backend tests for the per-box API functions on generated data.
"""
import unittest

from src import api


class TestAPI(unittest.TestCase):
    """
    Endpoint shape checks against the real synthetic output.
    """

    @classmethod
    def setUpClass(cls):
        """
        Fit baselines once for the whole case.
        """
        api.init()

    def test_customers_orders(self):
        """
        Order rows carry identity, demand, and backlog fields.
        """
        rows = api.customers_orders(limit=5)
        self.assertEqual(len(rows), 5)
        self.assertTrue({"uuid", "Demand_Units", "Backorder_Qty"} <= set(rows[0]))

    def test_forecast_3mo(self):
        """
        Forecast returns 90 points for the requested box.
        """
        fc = api.forecast_3mo()
        self.assertEqual(len(fc["orders"]), 90)
        self.assertTrue(all(v >= 0 for v in fc["orders"]))

    def test_inventory_and_schedule(self):
        """
        Inventory rows are part-grained, schedule rows carry the plan.
        """
        inv = api.inventory_status(limit=5)
        self.assertTrue({"Part_SKU", "Inventory_Levels"} <= set(inv[0]))
        sch = api.production_schedule(limit=5)
        self.assertTrue({"Production_Plan_Qty"} <= set(sch[0]))

    def test_proposals_and_actions(self):
        """
        Proposals route every positive need, actions stay well-formed.
        """
        props = api.proposed_orders()
        self.assertTrue(len(props) > 0)
        self.assertTrue({"part", "supplier", "qty", "cost"} <= set(props[0]))
        for a in api.action_items():
            self.assertTrue({"uuid", "model", "action"} <= set(a))

    def test_approve(self):
        """
        Approvals append to the log and count up.
        """
        before = api.approve_proposal("t-1")["count"]
        after = api.approve_proposal("t-2")["count"]
        self.assertEqual(after, before + 1)


if __name__ == "__main__":
    unittest.main()
