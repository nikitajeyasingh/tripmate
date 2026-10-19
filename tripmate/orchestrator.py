"""TripMate orchestrator: plans a group trip with a team of specialist agents.

    Trip request
        |
    [1] Planner ------------ turns messy input into a structured TripBrief
        |
    [2] Weather Scout  \
        Local Expert    >--- run IN PARALLEL, each with its own MCP tools
        Budget Planner /
        |
    [3] Itinerary Designer - builds day-by-day plan from shared research ("blackboard")
        |
    [4] Quality Reviewer --- checks the plan; if it finds issues the designer
        |                    revises once (evaluator-optimizer loop)
    [5] Packing Assistant -- weather + activity aware checklist
        |
    Final trip plan (markdown) + full agent trace
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import date

from .agents import Agent, AgentResult, EventFn
from .contracts import BRIEF_TOOL, REVIEW_TOOL, TripPlan, TripRequest
from .llm import LLM, make_llm
from .mcp_client import MCPToolbox
from .skills import SkillRegistry


TONE = ("Write for a group of friends in their twenties: warm, practical, a little fun, never cheesy. "
        "Be specific and concise. Use markdown.")

# --------------------------------------------------------------------------- #
# The agent team
# --------------------------------------------------------------------------- #
PLANNER = Agent(
    "Planner", "🧭",
    "You are TripMate's Planner. Read the trip request and the free-text notes and turn them "
    "into a precise TripBrief. Infer budget_style from the vibe (bachelorette/birthday/spa -> "
    "treat-yourself; student/cheap -> budget; otherwise balanced). Extract every preference, "
    "must-do and thing to avoid from the notes. Don't invent preferences that aren't there.",
    output_tool=BRIEF_TOOL,
)

WEATHER = Agent(
    "Weather Scout", "🌤️",
    "You are TripMate's Weather Scout. Geocode the destination, then fetch weather for the exact "
    "trip dates. Report: a one-line overall summary; a compact per-day line (date, high/low °F, "
    "conditions); the best day(s) for outdoor plans and any day to keep indoors. Say whether the "
    "data is a live forecast, typical weather from last year, or offline sample data. " + TONE,
    mcp_tools=["geocode_city", "get_weather"],
)

LOCAL = Agent(
    "Local Expert", "📍",
    "You are TripMate's Local Expert. Geocode the destination, then (in parallel) get country info "
    "and real notable places nearby. Report: 'Know before you go' (language, currency, emergency "
    "number, driving side, plug adapter needs for US travelers), then the 10-12 best real places from "
    "the tool results for this group's vibe, each with a one-line reason. Only list places that came "
    "back from find_places_nearby. " + TONE,
    mcp_tools=["geocode_city", "get_country_info", "find_places_nearby"],
)

BUDGET = Agent(
    "Budget Planner", "💸",
    "You are TripMate's Budget Planner. Load your budget-splitter skill and follow it exactly. "
    "Geocode the destination and get country info to learn the local currency. " + TONE,
    mcp_tools=["geocode_city", "get_country_info", "convert_currency"],
    skills=["budget-splitter"],
)

ITINERARY = Agent(
    "Itinerary Designer", "🗓️",
    "You are TripMate's Itinerary Designer. Load your itinerary-builder skill and follow it exactly. "
    "Build the plan only from the research in <context>. If the reviewer sent feedback, fix every "
    "issue and return the full revised itinerary. " + TONE,
    mcp_tools=["find_places_nearby"],
    skills=["itinerary-builder"],
)

REVIEWER = Agent(
    "Quality Reviewer", "✅",
    "You are TripMate's Quality Reviewer, a strict but fair editor. Check the itinerary against the "
    "brief and research: (1) every named place appears in the research places list; (2) outdoor plans "
    "sit on good-weather days; (3) costs fit the daily spending cap; (4) every preference, must-do and "
    "avoid is honored; (5) pacing is realistic (max 3 anchors/day, light arrival/departure); "
    "(6) it mentions the local emergency number somewhere. Approve only if all pass. "
    "Meals are described by type and neighborhood ON PURPOSE, because we have no restaurant data; "
    "never ask for named restaurants or cafés. Named landmarks must still come from the research. "
    "Issues must be specific and fixable.",
    output_tool=REVIEW_TOOL,
)

PACKING = Agent(
    "Packing Assistant", "🧳",
    "You are TripMate's Packing Assistant. Load your packing-list skill and follow it exactly, "
    "using the weather and itinerary in <context>. " + TONE,
    skills=["packing-list"],
)

TEAM = [PLANNER, WEATHER, LOCAL, BUDGET, ITINERARY, REVIEWER, PACKING]


def _ctx(**data) -> str:
    return "<context>\n" + json.dumps(data, indent=1, ensure_ascii=False, default=str) + "\n</context>"


def _facts(*results: AgentResult) -> dict:
    """Shared 'blackboard': the raw tool outputs from research agents, so later
    agents are grounded in real data rather than in each other's prose."""
    facts: dict = {}
    places: dict[str, dict] = {}          # every place from EVERY find_places_nearby call
    for r in results:
        for t in r.tool_log:
            if t["tool"] == "load_skill":
                continue
            try:
                data = json.loads(t["output"])
            except (json.JSONDecodeError, TypeError):
                data = t["output"]
            if t["tool"] == "find_places_nearby" and isinstance(data, dict):
                # Agents search several neighborhoods. Merge them all; keeping only the
                # last call meant the reviewer saw one neighborhood and rejected the rest.
                for p in data.get("places", []):
                    places.setdefault(p["name"], p)
                data = {**data, "places": list(places.values())}
            facts[t["tool"]] = data
    return facts


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
async def plan_trip(req: TripRequest, *, llm: LLM | None = None, emit: EventFn | None = None,
                    offline: bool = False, max_revisions: int = 1) -> TripPlan:
    llm = llm or make_llm()
    registry = SkillRegistry()
    t0 = time.perf_counter()
    results: dict[str, AgentResult] = {}

    async def stage(label: str):
        if emit:
            out = emit({"type": "stage", "label": label})
            if asyncio.iscoroutine(out):
                await out

    async with MCPToolbox(offline=offline) as toolbox:
        all_runs: list[AgentResult] = []

        async def run(agent: Agent, task: str) -> AgentResult:
            r = await agent.run(task, llm=llm, toolbox=toolbox, registry=registry, emit=emit)
            all_runs.append(r)
            return r

        # 1. Planner -> structured brief
        await stage("1 · Understanding your trip")
        r = await run(PLANNER, _ctx(request=req.__dict__, today=date.today().isoformat())
                      + "\nCreate the trip brief.")
        results[PLANNER.name] = r
        brief = r.output or {}
        # deterministic guardrails on top of the LLM's interpretation
        brief.update(start_date=req.start_date, end_date=req.end_date, people=req.people,
                     budget_per_person_usd=req.budget_per_person)
        brief["nights"] = max(1, (date.fromisoformat(req.end_date) - date.fromisoformat(req.start_date)).days)

        # 2. Research in parallel
        await stage("2 · Researching (3 agents in parallel)")
        w, l, b = await asyncio.gather(
            run(WEATHER, _ctx(brief=brief) + "\nResearch the weather for this trip."),
            run(LOCAL, _ctx(brief=brief) + "\nResearch the destination for this group."),
            run(BUDGET, _ctx(brief=brief) + "\nBuild the budget for this group."),
        )
        results.update({WEATHER.name: w, LOCAL.name: l, BUDGET.name: b})
        facts = _facts(w, l, b)
        research = {"weather": w.text, "local": l.text, "budget": b.text}

        # 3 + 4. Design -> review -> revise (evaluator-optimizer loop)
        await stage("3 · Designing your itinerary")
        task = _ctx(brief=brief, research=research, facts=facts) + "\nWrite the itinerary."
        it = await run(ITINERARY, task)
        designs = [it]
        reviews = []
        for attempt in range(max_revisions + 1):
            await stage("4 · Quality check" + (f" (round {attempt + 1})" if attempt else ""))
            # include places the designer looked up itself, so the reviewer can verify them
            facts = _facts(w, l, b, *designs)
            rv = await run(REVIEWER, _ctx(brief=brief, facts=facts, budget=b.text, itinerary=it.text)
                           + "\nReview this itinerary.")
            reviews.append(rv)
            if (rv.output or {}).get("approved", True) or attempt == max_revisions:
                break
            await stage("3b · Revising itinerary from reviewer feedback")
            it = await run(ITINERARY, task + "\n\n<previous_itinerary>\n" + it.text + "\n</previous_itinerary>"
                           + "\n<reviewer_feedback>\n" + json.dumps(rv.output, ensure_ascii=False) + "\n</reviewer_feedback>"
                           + "\nRevise the itinerary to fix every issue.")
            designs.append(it)
        results[ITINERARY.name] = it
        results[REVIEWER.name] = reviews[-1]

        # 5. Packing
        await stage("5 · Packing list")
        p = await run(PACKING, _ctx(brief=brief, weather=w.text, weather_data=facts.get("get_weather"),
                                    country=facts.get("get_country_info"), itinerary=it.text) + "\nWrite the packing list.")
        results[PACKING.name] = p

        safety = await toolbox.read_resource("tripmate://safety-checklist")  # MCP resource

    # ---- assemble ---------------------------------------------------------- #
    sections = {
        "Itinerary": it.text, "Weather": w.text, "Budget": b.text,
        "Local intel": l.text, "Packing list": p.text, "Safety": safety,
    }
    all_results = all_runs
    sources = sorted({str(v.get("source")) for v in facts.values() if isinstance(v, dict) and v.get("source")})
    review = reviews[-1].output or {}
    stats = {
        "model": llm.name,
        "agents": len(TEAM),
        "agent_runs": len(all_results),
        "tool_calls": sum(len(r.tool_log) for r in all_results),
        "revisions": len(reviews) - 1,
        "review_score": review.get("score"),
        "review_note": review.get("praise"),
        "tokens_in": sum(r.usage["input"] for r in all_results),
        "tokens_out": sum(r.usage["output"] for r in all_results),
        "seconds": round(time.perf_counter() - t0, 1),
        "data_sources": sources,
    }
    return TripPlan(brief, sections, build_markdown(brief, sections), results, facts=facts, stats=stats)


def build_markdown(brief: dict, sections: dict[str, str]) -> str:
    """Join all sections into one downloadable markdown document."""
    title = f"# ✈️ {brief.get('vibe', 'Trip').title()} in {brief.get('destination', '')}\n"
    sub = (f"**{brief['start_date']} → {brief['end_date']}** · {brief['nights']} nights · "
           f"{brief['people']} travelers · ${brief['budget_per_person_usd']:,.0f}/person\n")
    return title + sub + "".join(f"\n---\n\n## {k}\n\n{v}\n" for k, v in sections.items())
