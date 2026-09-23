"""
Functional stepping UI over stdlib HTTP (no new dependencies).

Serves stepping_ui.html plus JSON endpoints over src/api.py snapshot
and sim_* backends. Single stepping session (module api state).
Usage: python ui/serve_ui.py [--port 8000] [--synth-dir data/synthetic_output]
Requires: numpy, pandas.
"""
import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import api

ROOT = Path(__file__).resolve().parent
_backends_ready = False


def ensure_backends(synth_dir: Path | str | None = None) -> None:
    """
    Init snapshot backend once; sim session starts on first request.

    Args:
        synth_dir: snapshot CSV directory (defaults to 2020-2023 output).

    Returns:
        None.
    """
    global _backends_ready
    if _backends_ready:
        return
    if synth_dir is None:
        api.init()
    else:
        api.init(synth_dir)
    _backends_ready = True


def snapshot() -> dict:
    """
    Serve all six static UI boxes plus agent summaries in one payload.

    Returns:
        Dict with orders, forecast, actions, proposals, inventory,
        schedule, and agents keys.
    """
    ensure_backends()
    return {"orders": api.customers_orders(limit=50),
            "forecast": api.forecast_3mo(),
            "actions": api.action_items(),
            "proposals": api.proposed_orders(),
            "inventory": api.inventory_status(limit=50),
            "schedule": api.production_schedule(limit=50),
            "agents": {"failures": api._state.get("ag_failures", {}).get("text", ""),
                       "delays": api._state.get("ag_delays", {}).get("text", ""),
                       "orders": api._state.get("ag_orders", {}).get("text", "")}}


def sim_boxes() -> dict:
    """
    Serve all six live UI boxes for the current sim date in one payload.

    Returns:
        Dict with customers_orders, forecast, actions, proposed_orders,
        inventory, and schedule keys from the sim_* backends.
    """
    return {"customers_orders": api.sim_customers_orders(limit=50),
            "forecast": api.sim_forecast_3mo(),
            "actions": api.sim_action_items(),
            "proposed_orders": api.sim_proposals(),
            "inventory": api.sim_inventory_status(),
            "schedule": api.sim_production_schedule(limit=50)}


class Handler(BaseHTTPRequestHandler):
    """
    Routes / to the UI page and /api/* to JSON backend calls.
    """

    def log_message(self,
                    fmt: str,
                    *args: object) -> None:
        """
        Silence default request logging.

        Args:
            fmt: format string.
            args: format arguments.

        Returns:
            None.
        """

    def _send(self,
              payload: object,
              status: int = 200) -> None:
        """
        Send a JSON payload with headers.

        Args:
            payload: JSON-serializable object.
            status: HTTP status code.

        Returns:
            None.
        """
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        """
        Parse an optional JSON request body.

        Returns:
            Body dict, or empty dict when absent/unparseable.
        """
        try:
            n = int(self.headers.get("Content-Length", 0))
        except ValueError:
            return {}
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return {}

    def do_GET(self) -> None:
        """
        Serve the UI page, snapshot payload, or sim reads.

        Returns:
            None.
        """
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            page = (ROOT / "stepping_ui.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
        elif path == "/api/snapshot":
            self._send(snapshot())
        elif path == "/api/sim/proposals":
            self._send(api.sim_proposals())
        elif path == "/api/sim/score":
            self._send(api.sim_score())
        elif path == "/api/sim/history":
            self._send(api.sim_history())
        elif path == "/api/sim/boxes":
            self._send(sim_boxes())
        else:
            self._send({"error": f"unknown route {path}"}, 404)

    def do_POST(self) -> None:
        """
        Handle sim session writes (init/start/approve/advance).

        Returns:
            None.
        """
        path = urlparse(self.path).path
        body = self._body()
        if path == "/api/sim/init":
            self._send(api.sim_init())
        elif path == "/api/sim/start":
            self._send(api.sim_start(str(body.get("date", "2024-01-01")),
                                     int(body.get("opening_cover_days", 30))))
        elif path == "/api/sim/approve":
            self._send(api.sim_approve(str(body.get("id", ""))))
        elif path == "/api/sim/advance":
            self._send(api.sim_advance(float(body.get("holding_per_unit", 1.0))))
        else:
            self._send({"error": f"unknown route {path}"}, 404)


def main(argv: list | None = None) -> None:
    """
    Start the UI server until interrupted.

    Args:
        argv: argument list (defaults to process args).

    Returns:
        None; blocks serving on the requested port.
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--synth-dir", default=None)
    a = ap.parse_args(argv)
    ensure_backends(a.synth_dir)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"serving stepping UI at http://127.0.0.1:{srv.server_port}/")
    srv.serve_forever()


if __name__ == "__main__":
    main()
