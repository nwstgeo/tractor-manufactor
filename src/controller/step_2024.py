"""
Stepping-engine CLI over data/synthetic_output_2024.

Batch mode approves per-step proposals under a policy loop so forward
fill can climb; interactive mode exposes start/proposals/approve/advance.
Usage: python -m src.controller.step_2024 [--start-date 2024-06-01] [--steps 30]
    [--approve all|none] [--holding-per-unit 1.0] [--interactive]
Requires: numpy, pandas.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.sim import scoring as SC
from src.sim import stepper

POLICIES = ("all", "none")


def run_policy(start_date: str = "2024-06-01",
               steps: int = 30,
               approve: str = "all",
               holding_per_unit: float = 1.0,
               opening_cover_days: int = 30,
               synth_dir: Path | str = stepper.SYNTH_2024) -> dict:
    """
    Run a sustained per-step order policy and score it forward.

    Args:
        start_date: ISO date starting the run.
        steps: number of event-date advances to execute.
        approve: "all" approves every proposal each step; "none" orders nothing.
        holding_per_unit: holding cost per on-hand unit per day stepped.
        opening_cover_days: opening stock top-up horizon (0 keeps snapshots).
        synth_dir: directory holding the 2024 CSVs.

    Returns:
        Dict with start, steps taken, final score, and trailing-30d fill.
    """
    if approve not in POLICIES:
        raise ValueError(f"approve must be one of {POLICIES}")
    st = stepper.init(synth_dir)
    start = stepper.start(st,
                          start_date,
                          opening_cover_days)
    taken = 0
    for _ in range(max(int(steps), 0)):
        if approve == "all":
            for p in stepper.proposals(st):
                stepper.approve(st,
                                p["id"])
        summary = stepper.advance(st,
                                  float(holding_per_unit))
        if not summary.get("advanced"):
            break
        taken += 1
    score = SC.score(float(st["filled"]),
                     float(st["unfilled"]),
                     float(st["spent"]),
                     float(st["holding"]))
    score["steps_taken"] = taken
    score["start"] = start["current_date"]
    score["current_date"] = str(st["current_date"].date())
    score["trail_30d_fill"] = SC.window_fill(st["history"],
                                             30)["fill"]
    return score


def repl(synth_dir: Path | str = stepper.SYNTH_2024) -> None:
    """
    Interactively step: start, proposals, approve, advance, score.

    Args:
        synth_dir: directory holding the 2024 CSVs.

    Returns:
        None; exits on quit/eof.
    """
    st = stepper.init(synth_dir)
    print("step_2024 repl: help | start [date] | proposals | approve <id|all> | advance [n] | score | history [n] | quit")
    while True:
        try:
            raw = input("step> ").strip().split()
        except EOFError:
            break
        if not raw or raw[0] in ("quit", "exit"):
            break
        cmd = raw[0]
        arg = raw[1] if len(raw) > 1 else ""
        if cmd == "help":
            print("start [date] / proposals / approve <id|all> / advance [n] / score / history [n] / quit")
        elif cmd == "start":
            print(stepper.start(st,
                                arg or "2024-01-01"))
        elif cmd == "proposals":
            try:
                for p in stepper.proposals(st):
                    print(p)
            except ValueError as e:
                print({"error": str(e)})
        elif cmd == "approve":
            try:
                if arg == "all":
                    ids = [p["id"] for p in stepper.proposals(st)]
                    print({"approved": [stepper.approve(st,
                                                        i)["arrival_date"] for i in ids]})
                else:
                    print(stepper.approve(st,
                                          arg))
            except ValueError as e:
                print({"error": str(e)})
        elif cmd == "advance":
            try:
                for _ in range(int(arg) if arg else 1):
                    summary = stepper.advance(st)
                    print({k: summary[k] for k in ("to", "arrived", "need", "filled", "fill_so_far")})
                    if not summary.get("advanced"):
                        break
            except ValueError as e:
                print({"error": str(e)})
        elif cmd == "score":
            print(SC.score(float(st.get("filled", 0)),
                           float(st.get("unfilled", 0)),
                           float(st.get("spent", 0.0)),
                           float(st.get("holding", 0.0))))
        elif cmd == "history":
            for e in st.get("history", [])[-(int(arg) if arg else 5):]:
                print(e)
        else:
            print(f"unknown command {cmd}")


def main(argv: list | None = None) -> None:
    """
    Parse CLI args and run batch policy or interactive repl.

    Args:
        argv: argument list (defaults to process args).

    Returns:
        None; prints the run score or starts the repl.
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-date", default="2024-06-01")
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--approve", default="all", choices=list(POLICIES))
    ap.add_argument("--holding-per-unit", type=float, default=1.0)
    ap.add_argument("--opening-cover-days", type=int, default=30)
    ap.add_argument("--interactive", action="store_true")
    a = ap.parse_args(argv)
    if a.interactive:
        repl()
    else:
        print(run_policy(a.start_date,
                         a.steps,
                         a.approve,
                         a.holding_per_unit,
                         a.opening_cover_days))


if __name__ == "__main__":
    main()
