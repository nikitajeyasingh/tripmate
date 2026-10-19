"""Conversational revision: change the plan by chatting, e.g.
    "make Day 2 more relaxed"   "add a beach afternoon"   "one of us is vegan now"

Flow (small on purpose):
    traveler message -> ✏️ Trip Editor (edits only what was asked)
                     -> ✅ Quality Reviewer re-checks the itinerary
                     -> if it finds issues, the editor fixes them once (self-correction)
Big changes (destination, dates, group size, budget) need fresh research, so the
editor asks the traveler to re-plan instead of guessing.
"""
from __future__ import annotations

import json
from dataclasses import replace

from .agents import Agent, AgentResult, EventFn
from .contracts import EDIT_TOOL, TripPlan
from .llm import LLM, make_llm
from .orchestrator import REVIEWER, TONE, _ctx, build_markdown
from .skills import SkillRegistry

EDITOR = Agent(
    "Trip Editor", "✏️",
    "You are TripMate's Trip Editor. The travelers already have a plan and want one change. "
    "Apply ONLY what they ask and keep everything else exactly as it is. Use only real places from "
    "the facts in <context>. Update the packing list only if the change affects what to pack "
    "(e.g. a new beach day); otherwise return \"\" for it. If they ask to change the destination, "
    "dates, number of people or budget, do not edit anything: return empty strings and tell them to "
    "re-plan the trip, because that needs fresh research. " + TONE,
    output_tool=EDIT_TOOL,
)


async def revise_trip(plan: TripPlan, request: str, *, llm: LLM | None = None,
                      emit: EventFn | None = None) -> TripPlan:
    llm = llm or make_llm()
    registry = SkillRegistry()

    async def run(agent: Agent, task: str) -> AgentResult:
        return await agent.run(task, llm=llm, toolbox=None, registry=registry, emit=emit)

    base = dict(brief=plan.brief, facts=plan.facts, itinerary=plan.sections["Itinerary"],
                packing_list=plan.sections["Packing list"], earlier_changes=plan.history)
    task = _ctx(**base) + f"\n<change_request>\n{request}\n</change_request>\nApply this change."
    edit = (await run(EDITOR, task)).output or {}

    sections = dict(plan.sections)
    review = None
    if edit.get("itinerary", "").strip():
        # Self-correction: the reviewer checks the edited itinerary; one fix round if needed.
        for attempt in range(2):
            review = (await run(REVIEWER, _ctx(brief=plan.brief, facts=plan.facts, budget=sections["Budget"],
                                               itinerary=edit["itinerary"]) + "\nReview this itinerary.")).output or {}
            if review.get("approved", True) or attempt == 1:
                break
            fixed = (await run(EDITOR, task + "\n<your_previous_edit>\n" + edit["itinerary"] + "\n</your_previous_edit>"
                               + "\n<reviewer_feedback>\n" + json.dumps(review, ensure_ascii=False)
                               + "\n</reviewer_feedback>\nFix every issue in your edit.")).output or {}
            if fixed.get("itinerary", "").strip():
                edit["itinerary"] = fixed["itinerary"]
        sections["Itinerary"] = edit["itinerary"]
    if edit.get("packing_list", "").strip():
        sections["Packing list"] = edit["packing_list"]

    brief = dict(plan.brief)
    if edit.get("new_preferences"):
        brief["preferences"] = list(brief.get("preferences", [])) + edit["new_preferences"]

    turn = {"request": request, "summary": edit.get("change_summary", "Done."),
            "review_score": (review or {}).get("score")}
    return replace(plan, brief=brief, sections=sections, markdown=build_markdown(brief, sections),
                   history=plan.history + [turn])
