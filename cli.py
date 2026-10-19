"""TripMate command line.

    python cli.py                                  # sample Lisbon girls' trip
    python cli.py --demo                           # force offline demo brain (no API key needed)
    python cli.py --offline                        # use bundled sample data instead of live APIs
    python cli.py --chat                           # then chat to change the plan
    python cli.py -d Nashville -s 2026-11-06 -e 2026-11-09 -p 5 -b 700 \
        -v "Bachelorette weekend" -n "Must do a line-dancing class. One friend is vegetarian. No 6am starts."
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from tripmate import TripRequest, make_llm, plan_trip, revise_trip  # noqa: E402

DIM, BOLD, PINK, GREEN, RESET = "\033[2m", "\033[1m", "\033[95m", "\033[92m", "\033[0m"


def on_event(ev: dict) -> None:
    t = ev["type"]
    if t == "stage":
        print(f"\n{BOLD}{PINK}▶ {ev['label']}{RESET}")
    elif t == "start":
        print(f"  {ev['emoji']} {BOLD}{ev['agent']}{RESET} started  {DIM}tools: {', '.join(ev['tools']) or '—'}{RESET}")
    elif t == "tool_call":
        args = json.dumps(ev["input"], ensure_ascii=False)
        print(f"     {DIM}↳ {ev['agent']} → {ev['tool']}({args[:90]}){RESET}")
    elif t == "done":
        extra = ""
        if ev.get("output") and "approved" in ev["output"]:
            o = ev["output"]
            extra = f"  → {'APPROVED' if o['approved'] else 'CHANGES REQUESTED'} ({o['score']}/10) {'; '.join(o['issues'])}"
        print(f"  {GREEN}✓{RESET} {ev['agent']} done in {ev['seconds']:.1f}s{extra}")


def main() -> None:
    nxt = date.today() + timedelta(days=(4 - date.today().weekday()) % 7 or 7)  # next Friday
    ap = argparse.ArgumentParser(description="TripMate: multi-agent group trip planner")
    ap.add_argument("-d", "--destination", default="Lisbon")
    ap.add_argument("-s", "--start", default=nxt.isoformat())
    ap.add_argument("-e", "--end", default=(nxt + timedelta(days=3)).isoformat())
    ap.add_argument("-p", "--people", type=int, default=4)
    ap.add_argument("-b", "--budget", type=float, default=900, help="USD per person, excluding flights")
    ap.add_argument("-v", "--vibe", default="Birthday girls' trip")
    ap.add_argument("-n", "--notes", default="We love brunch and pretty photo spots. One of us is vegetarian. No clubbing.")
    ap.add_argument("--demo", action="store_true", help="offline demo brain instead of Claude")
    ap.add_argument("--offline", action="store_true", help="bundled sample data instead of live APIs")
    ap.add_argument("-o", "--out", default="trip_plan.md")
    ap.add_argument("--chat", action="store_true", help="after planning, chat to revise the plan")
    a = ap.parse_args()

    req = TripRequest(a.destination, a.start, a.end, a.people, a.budget, a.vibe, a.notes)
    llm = make_llm(demo=True if a.demo else None)
    print(f"{BOLD}✈️  TripMate{RESET} · {req.destination} · {req.start_date} → {req.end_date} · brain: {llm.name}")
    plan = asyncio.run(plan_trip(req, llm=llm, emit=on_event, offline=a.offline))

    Path(a.out).write_text(plan.markdown, encoding="utf-8")
    s = plan.stats
    print(f"\n{BOLD}Done in {s['seconds']}s{RESET} · {s['agents']} agents · {s['agent_runs']} agent runs · "
          f"{s['tool_calls']} tool calls · {s['revisions']} revision(s) · review {s['review_score']}/10 · "
          f"tokens {s['tokens_in']:,} in / {s['tokens_out']:,} out · data: {', '.join(s['data_sources'])}")
    print(f"Plan saved to {BOLD}{a.out}{RESET}")

    # ---- conversational revision ---------------------------------------- #
    if a.chat:
        print(f"\n{BOLD}Want to change anything?{RESET} e.g. 'make Day 2 more relaxed', 'add a beach afternoon', "
              "'one of us is vegan now'. Press Enter to finish.")
        while True:
            msg = input(f"{PINK}you ›{RESET} ").strip()
            if not msg:
                break
            plan = asyncio.run(revise_trip(plan, msg, llm=llm, emit=on_event))
            print(f"{GREEN}TripMate ›{RESET} {plan.history[-1]['summary']}")
            Path(a.out).write_text(plan.markdown, encoding="utf-8")
        print(f"Final plan saved to {BOLD}{a.out}{RESET}")


if __name__ == "__main__":
    main()
