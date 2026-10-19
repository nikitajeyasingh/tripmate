"""Run:  pytest -q      (no API key or internet needed)"""
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["TRIPMATE_DEMO_FAST"] = "1"  # skip the demo's fake 'thinking' pauses
sys.path.insert(0, str(ROOT))

from tripmate import TripRequest, plan_trip  # noqa: E402
from tripmate.demo_llm import DemoLLM  # noqa: E402
from tripmate.mcp_client import MCPToolbox  # noqa: E402
from tripmate.skills import SkillRegistry  # noqa: E402


def test_budget_split_adds_up():
    split = SkillRegistry().skills["budget-splitter"].tools["calculate_budget_split"][1]
    r = split(budget_per_person=800, people=4, nights=3, style="balanced")
    assert abs(sum(r["per_person"].values()) - 800) < 0.05
    assert r["group_total"] == 3200


def test_budget_split_warns_when_lodging_too_expensive():
    split = SkillRegistry().skills["budget-splitter"].tools["calculate_budget_split"][1]
    r = split(budget_per_person=300, people=2, nights=3, lodging_per_night_total=250)
    assert r["warnings"], "expected a lodging warning"


def test_skills_discovered_with_progressive_disclosure():
    reg = SkillRegistry()
    assert {"budget-splitter", "itinerary-builder", "packing-list"} <= set(reg.skills)
    catalog = reg.catalog(["packing-list"])
    assert "packing-list" in catalog and "Rules" not in catalog  # only the summary, not the body
    assert "Rules" in reg.load("packing-list")


def test_mcp_server_exposes_tools_and_answers():
    async def go():
        async with MCPToolbox(offline=True) as box:
            assert {"geocode_city", "get_weather", "get_country_info", "convert_currency",
                    "find_places_nearby"} <= set(box.schemas)
            geo = json.loads(await box.call("geocode_city", {"city": "Lisbon"}))
            assert geo["country_code"] == "PT"
            assert "safety" in (await box.read_resource("tripmate://safety-checklist")).lower()
    asyncio.run(go())


def test_full_pipeline_in_demo_mode():
    req = TripRequest("Lisbon", "2026-11-06", "2026-11-09", 4, 900, "Birthday girls' trip",
                      "We love brunch. One of us is vegetarian. No clubbing.")
    plan = asyncio.run(plan_trip(req, llm=DemoLLM(), offline=True))
    assert set(plan.sections) == {"Itinerary", "Weather", "Budget", "Local intel", "Packing list", "Safety"}
    assert plan.brief["nights"] == 3 and plan.brief["budget_style"] == "treat-yourself"
    assert plan.stats["revisions"] == 1            # reviewer caught a gap and the designer fixed it
    assert "emergency" in plan.sections["Itinerary"].lower()
    assert "Day 4" in plan.sections["Itinerary"]


def _demo_plan():
    req = TripRequest("Tulum", "2026-11-06", "2026-11-09", 3, 1100, "Chill wellness escape", "Want cenotes.")
    return asyncio.run(plan_trip(req, llm=DemoLLM(), offline=True))


def test_chat_revision_changes_only_what_was_asked():
    from tripmate import revise_trip
    plan = _demo_plan()
    new = asyncio.run(revise_trip(plan, "make day 2 more relaxed", llm=DemoLLM()))
    assert "Sleep in, then a slow coffee" in new.sections["Itinerary"]
    assert new.sections["Weather"] == plan.sections["Weather"]          # untouched
    assert new.history[-1]["request"] == "make day 2 more relaxed"
    vegan = asyncio.run(revise_trip(new, "one of us is vegan now", llm=DemoLLM()))
    assert "Vegan" in vegan.brief["preferences"]


def test_big_changes_ask_to_replan():
    from tripmate import revise_trip
    plan = _demo_plan()
    new = asyncio.run(revise_trip(plan, "change the budget to $500", llm=DemoLLM()))
    assert new.sections == plan.sections and "Plan our trip" in new.history[-1]["summary"]
