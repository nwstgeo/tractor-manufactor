"""
Forward fill/cost scoring tests.
"""
import unittest

from src.model import r as R
from src.sim import scoring as SC
from src.sim import stepper


class TestScore(unittest.TestCase):
    """
    Plain-input scoring math checks.
    """

    def test_meets_target(self):
        """
        Fill at target yields zero gap and a passing verdict.
        """
        s = SC.score(98.0,
                     2.0,
                     1000.0,
                     100.0)
        self.assertAlmostEqual(s["fill"], 0.98)
        self.assertAlmostEqual(s["gap"], 0.0)
        self.assertAlmostEqual(s["total_cost"], 1100.0)
        self.assertAlmostEqual(s["cost_per_filled"], 1100.0 / 98.0)
        self.assertTrue(s["meets_target"])

    def test_shortfall(self):
        """
        Fill below target yields a positive gap and a failing verdict.
        """
        s = SC.score(90.0,
                     10.0,
                     500.0,
                     50.0)
        self.assertAlmostEqual(s["fill"], 0.9)
        self.assertAlmostEqual(s["gap"], R.FILL_TARGET - 0.9)
        self.assertFalse(s["meets_target"])

    def test_zero_demand(self):
        """
        Empty run scores perfect fill with zero unit cost.
        """
        s = SC.score(0.0,
                     0.0,
                     0.0,
                     0.0)
        self.assertEqual(s["fill"], 1.0)
        self.assertEqual(s["cost_per_filled"], 0.0)
        self.assertTrue(s["meets_target"])

    def test_custom_target(self):
        """
        Explicit target overrides the R default.
        """
        s = SC.score(90.0,
                     10.0,
                     0.0,
                     0.0,
                     0.90)
        self.assertTrue(s["meets_target"])


class TestWindowFill(unittest.TestCase):
    """
    Trailing-window fill checks.
    """

    def test_trailing_window(self):
        """
        Only the last n steps count toward window fill.
        """
        hist = [{"need": 100, "filled": 50},
                {"need": 100, "filled": 100},
                {"need": 100, "filled": 100}]
        w = SC.window_fill(hist,
                           2)
        self.assertEqual(w["steps"], 2)
        self.assertEqual(w["need"], 200)
        self.assertEqual(w["fill"], 1.0)
        full = SC.window_fill(hist,
                              10)
        self.assertEqual(full["steps"], 3)
        self.assertAlmostEqual(full["fill"], 250 / 300)

    def test_empty_history(self):
        """
        Empty history scores perfect fill over zero steps.
        """
        w = SC.window_fill([],
                           30)
        self.assertEqual(w["steps"], 0)
        self.assertEqual(w["fill"], 1.0)


class TestEngineScoring(unittest.TestCase):
    """
    Engine history and cost accrual checks.
    """

    def test_advance_records_history_and_costs(self):
        """
        Advances append history, accrue holding, and attach a score.
        """
        st = stepper.init()
        stepper.start(st,
                      "2024-06-01")
        props = stepper.proposals(st)
        stepper.approve(st,
                        props[0]["id"])
        spent = st["spent"]
        self.assertGreater(spent, 0.0)
        first = stepper.advance(st)
        second = stepper.advance(st)
        self.assertEqual(len(st["history"]), 2)
        self.assertLess(first["to"], second["to"])
        self.assertGreaterEqual(st["holding"], 0.0)
        self.assertIn("score", second)
        self.assertAlmostEqual(second["score"]["fill"], second["fill_so_far"])
        self.assertEqual(second["score"]["purchase"], second["spent"])
        w = SC.window_fill(st["history"],
                           30)
        self.assertEqual(w["steps"], 2)

    def test_start_resets_scoring(self):
        """
        Restarting clears filled, costs, and history.
        """
        st = stepper.init()
        stepper.start(st,
                      "2024-06-01")
        stepper.advance(st)
        stepper.start(st,
                      "2024-06-01")
        self.assertEqual(st["filled"], 0)
        self.assertEqual(st["spent"], 0.0)
        self.assertEqual(st["holding"], 0.0)
        self.assertEqual(st["history"], [])


if __name__ == "__main__":
    unittest.main()
