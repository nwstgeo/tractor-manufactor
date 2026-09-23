"""
Server tests: page serve plus JSON roundtrips on an ephemeral port.
"""
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from ui import serve_ui
from src import api


def call(srv,
         method,
         path,
         body=None):
    """
    Issue one JSON HTTP request against the test server.

    Args:
        srv: running test server instance.
        method: HTTP method string.
        path: request path.
        body: optional JSON-serializable body.

    Returns:
        Decoded JSON response plus status code as (payload, status).
    """
    url = f"http://127.0.0.1:{srv.server_port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code


class TestServeUI(unittest.TestCase):
    """
    Page and endpoint checks against a live local server.
    """

    @classmethod
    def setUpClass(cls):
        """
        Start one server for the whole case.
        """
        serve_ui.ensure_backends()
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), serve_ui.Handler)
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        """
        Stop the test server.
        """
        cls.srv.shutdown()
        cls.thread.join()

    def test_page_serves(self):
        """
        Root path returns the stepping UI HTML page.
        """
        url = f"http://127.0.0.1:{self.srv.server_port}/"
        with urllib.request.urlopen(url) as r:
            body = r.read().decode()
        self.assertIn("Customers Orders Table", body)
        self.assertIn("Supply Inventory Table", body)
        self.assertIn("/api/sim/boxes", body)

    def test_snapshot(self):
        """
        Snapshot payload carries all six boxes plus agents.
        """
        payload, status = call(self.srv, "GET", "/api/snapshot")
        self.assertEqual(status, 200)
        self.assertTrue({"orders", "forecast", "actions", "proposals",
                         "inventory", "schedule", "agents"} <= set(payload))
        self.assertEqual(len(payload["forecast"]["orders"]), 90)

    def test_sim_roundtrip(self):
        """
        Sim session walks init/start/approve/advance/score/history live.
        """
        meta, _ = call(self.srv, "POST", "/api/sim/init", {})
        self.assertEqual(meta["events"], 2507)
        start, _ = call(self.srv, "POST", "/api/sim/start", {"date": "2024-06-01"})
        self.assertEqual(start["current_date"], "2024-06-01")
        props, _ = call(self.srv, "GET", "/api/sim/proposals")
        self.assertGreater(len(props), 0)
        order, _ = call(self.srv, "POST", "/api/sim/approve", {"id": props[0]["id"]})
        self.assertIn("arrival_date", order)
        summary, _ = call(self.srv, "POST", "/api/sim/advance", {})
        self.assertTrue(summary["advanced"])
        score, _ = call(self.srv, "GET", "/api/sim/score")
        self.assertIn("fill", score)
        hist, _ = call(self.srv, "GET", "/api/sim/history")
        self.assertEqual(len(hist), 1)
        self.assertEqual(api.sim_score()["steps"], 1)

    def test_unknown_route(self):
        """
        Unknown paths return a JSON 404.
        """
        _, status = call(self.srv, "GET", "/api/nope")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
