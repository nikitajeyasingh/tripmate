"""Deterministic budget math for the budget-splitter skill.

Exposed to agents as the `calculate_budget_split` tool. Keeping arithmetic in
code (not in the LLM) makes the numbers exact and testable.
"""
from __future__ import annotations

STYLES = {
    #               lodging, food, activities, transport, buffer
    "budget":         (0.35, 0.30, 0.15, 0.10, 0.10),
    "balanced":       (0.40, 0.28, 0.17, 0.07, 0.08),
    "treat-yourself": (0.45, 0.25, 0.20, 0.05, 0.05),
}
CATEGORIES = ("lodging", "food", "activities", "local_transport", "buffer")

TOOL_SCHEMA = {
    "name": "calculate_budget_split",
    "description": "Split a per-person trip budget into categories, per person and for the whole group, plus a daily spending cap. Use instead of doing math yourself.",
    "input_schema": {
        "type": "object",
        "properties": {
            "budget_per_person": {"type": "number", "description": "Total trip budget per person in USD (excluding flights)."},
            "people": {"type": "integer", "minimum": 1},
            "nights": {"type": "integer", "minimum": 1},
            "style": {"type": "string", "enum": list(STYLES)},
            "lodging_per_night_total": {"type": "number", "description": "Optional known price for the whole group's lodging per night, USD."},
        },
        "required": ["budget_per_person", "people", "nights"],
    },
}


def calculate_budget_split(budget_per_person: float, people: int, nights: int,
                           style: str = "balanced", lodging_per_night_total: float | None = None) -> dict:
    ratios = dict(zip(CATEGORIES, STYLES.get(style, STYLES["balanced"])))
    warnings: list[str] = []

    per_person = {c: budget_per_person * r for c, r in ratios.items()}
    if lodging_per_night_total:
        lodging_pp = lodging_per_night_total * nights / people
        rest = budget_per_person - lodging_pp
        if rest <= 0:
            warnings.append("Lodging alone exceeds the budget. Look for a cheaper stay or add travelers.")
            rest = 0
        others = {c: r for c, r in ratios.items() if c != "lodging"}
        total_r = sum(others.values())
        per_person = {"lodging": lodging_pp} | {c: rest * r / total_r for c, r in others.items()}
        if lodging_pp > 0.55 * budget_per_person:
            warnings.append(f"Lodging is {lodging_pp / budget_per_person:.0%} of each person's budget (above the 55% comfort line).")

    days = nights + 1
    daily_cap = (per_person["food"] + per_person["activities"] + per_person["local_transport"]) / days
    if daily_cap < 45:
        warnings.append(f"Daily spending cap is only ${daily_cap:.0f}. Plan free activities and grocery breakfasts.")

    r2 = lambda x: round(x, 2)  # noqa: E731
    return {
        "style": style,
        "people": people,
        "nights": nights,
        "per_person": {c: r2(v) for c, v in per_person.items()},
        "whole_group": {c: r2(v * people) for c, v in per_person.items()},
        "group_total": r2(budget_per_person * people),
        "daily_spending_cap_per_person": r2(daily_cap),
        "lodging_budget_per_night_group": r2(per_person["lodging"] * people / nights),
        "warnings": warnings,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(calculate_budget_split(800, 4, 3, "treat-yourself"), indent=2))
