"""TripMate: a multi-agent group-trip planner built on Claude + MCP + Skills."""
from .contracts import TripPlan, TripRequest
from .llm import make_llm
from .orchestrator import plan_trip
from .revision import revise_trip

__all__ = ["TripRequest", "TripPlan", "plan_trip", "revise_trip", "make_llm"]
