"""
Generate Stage-1 artifacts from live backend state (no fabricated numbers).
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import api
from src.sim import scoring as SC
from src.sim import stepper as STEP

st = api.init()
out = Path(__file__).resolve().parent / "docs"
out.mkdir(exist_ok=True)

orders = api.customers_orders(limit=5)
fc = api.forecast_3mo()
acts = api.action_items()[-5:]
props = api.proposed_orders()[:5]
inv = api.inventory_status(limit=5)
sched = api.production_schedule(limit=5)
fill = st["ag_orders"]["text"] if "ag_orders" in st else ""
agents = {"failures": st.get("ag_failures", {}).get("text", ""),
          "delays": st.get("ag_delays", {}).get("text", ""),
          "orders": st.get("ag_orders", {}).get("text", "")}

sim = STEP.init(str(Path(__file__).resolve().parent / "data" / "synthetic_output_2024"))
STEP.start(sim,
           "2024-06-01")
for _ in range(14):
    for p in STEP.proposals(sim):
        STEP.approve(sim,
                     p["id"])
    STEP.advance(sim)
sim_score = SC.score(float(sim["filled"]),
                     float(sim["unfilled"]),
                     float(sim["spent"]),
                     float(sim["holding"]))
sim_line = (f"14d approve-all from 2024-06-01: fill={sim_score['fill']:.3f} "
            f"gap={sim_score['gap']:.3f} cost={sim_score['total_cost']:.0f} "
            f"target={sim_score['target']:.2f}")


def row(d):
    """
    Render one record dict as HTML table cells.
    """
    return "<tr>" + "".join(f"<td>{k}={v}</td>" for k, v in d.items()) + "</tr>"


def box(title,
        model,
        body):
    """
    Wrap one UI box with title, contributing model, and body HTML.
    """
    return f"<section><h2>{title} <small>[{model}]</small></h2>{body}</section>"


html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Tractor Supply Chain UI Mockup</title>
<style>body{{font-family:sans-serif;margin:16px}}main{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
section{{border:1px solid #999;padding:8px}}table{{border-collapse:collapse;font-size:12px}}
td{{border:1px solid #ccc;padding:2px 4px}}small{{color:#555}}</style></head>
<body><h1>Tractor Supply Chain UI Mockup (live backend snapshot)</h1>
<p>Agents: failures [{agents["failures"]}] / delays [{agents["delays"]}] / orders [{agents["orders"]}]</p>
<main>
{box("Customers Orders Table", "H", "<table>" + "".join(row(r) for r in orders) + "</table>")}
{box("3 month Forecast of Orders", "O&amp;F (R)", f"<p>{fc['model']}/{fc['warehouse']}: next 90d, first 5: {fc['orders'][:5]}</p>")}
{box("Action Items to do", "R", "<table>" + "".join(row(r) for r in acts) + "</table>")}
{box("Proposed Orders to Approve", "R", "<table>" + "".join(row(r) for r in props) + "</table>")}
{box("Supply Inventory Table", "H", "<table>" + "".join(row(r) for r in inv) + "</table>")}
{box("Production Schedule", "H", "<table>" + "".join(row(r) for r in sched) + "</table>")}
{box("Stepping Run (sim)", "R", f"<p>{sim_line}</p>")}
</main></body></html>"""
(out / "ui_mockup.html").write_text(html)
print(f"wrote {out / 'ui_mockup.html'} fill={fill}")
