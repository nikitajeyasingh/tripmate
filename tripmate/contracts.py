"""Data contracts: the shapes of data passed between the user, the orchestrator and the agents.

Design these FIRST. If everyone agrees on the shape of the data, each agent can be
built and tested on its own.

  * TripRequest  - what the user types in
  * TripPlan     - what the system hands back
  * *_TOOL       - JSON schemas that force an agent to answer in a fixed shape
                   ("structured output"). The agent must "call" this tool, and the
                   arguments it passes ARE the answer.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .agents import AgentResult


@dataclass
class TripRequest:
    destination: str
    start_date: str            # YYYY-MM-DD
    end_date: str              # YYYY-MM-DD
    people: int = 4
    budget_per_person: float = 800
    vibe: str = "Girls' weekend"
    notes: str = ""


@dataclass
class TripPlan:
    brief: dict                         # structured version of the request (from the Planner)
    sections: dict[str, str]            # "Itinerary", "Weather", "Budget", ... -> markdown
    markdown: str                       # everything joined, ready to download
    results: dict[str, AgentResult]     # each agent's output + tool calls (the trace)
    facts: dict = field(default_factory=dict)    # raw API data the agents fetched
    stats: dict = field(default_factory=dict)    # timing, tool calls, tokens, ...
    history: list[dict] = field(default_factory=list)  # chat revisions: [{"request", "summary"}]


# --------------------------------------------------------------------------- #
# Structured-output schemas
# --------------------------------------------------------------------------- #
BRIEF_TOOL = {
    "name": "submit_trip_brief",
    "description": "Submit the structured trip brief.",
    "input_schema": {
        "type": "object",
        "properties": {
            "destination": {"type": "string", "description": "City name only, e.g. 'Lisbon'"},
            "start_date": {"type": "string"}, "end_date": {"type": "string"},
            "people": {"type": "integer"},
            "budget_per_person_usd": {"type": "number"},
            "budget_style": {"type": "string", "enum": ["budget", "balanced", "treat-yourself"]},
            "vibe": {"type": "string", "description": "One short phrase, e.g. 'birthday girls trip, foodie + photos'"},
            "preferences": {"type": "array", "items": {"type": "string"}, "description": "Dietary, accessibility, interests"},
            "must_do": {"type": "array", "items": {"type": "string"}},
            "avoid": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["destination", "start_date", "end_date", "people", "budget_per_person_usd",
                     "budget_style", "vibe", "preferences", "must_do", "avoid"],
    },
}

REVIEW_TOOL = {
    "name": "submit_review",
    "description": "Submit your quality review of the itinerary.",
    "input_schema": {
        "type": "object",
        "properties": {
            "approved": {"type": "boolean"},
            "score": {"type": "integer", "minimum": 1, "maximum": 10},
            "issues": {"type": "array", "items": {"type": "string"},
                       "description": "Concrete problems the designer must fix. Empty if approved."},
            "praise": {"type": "string", "description": "One sentence on what works well."},
        },
        "required": ["approved", "score", "issues", "praise"],
    },
}

EDIT_TOOL = {
    "name": "submit_changes",
    "description": "Submit the updated trip after applying the traveler's change request.",
    "input_schema": {
        "type": "object",
        "properties": {
            "itinerary": {"type": "string", "description": "The FULL updated itinerary markdown, or \"\" if it doesn't change."},
            "packing_list": {"type": "string", "description": "The FULL updated packing list markdown, or \"\" if it doesn't change."},
            "new_preferences": {"type": "array", "items": {"type": "string"},
                                "description": "Any new preference to remember (e.g. 'Vegan'). Empty if none."},
            "change_summary": {"type": "string", "description": "1-2 friendly sentences telling the traveler what changed."},
        },
        "required": ["itinerary", "packing_list", "new_preferences", "change_summary"],
    },
}
