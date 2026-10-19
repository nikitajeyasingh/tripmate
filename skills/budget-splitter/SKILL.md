---
name: budget-splitter
description: Split a group trip budget fairly into lodging, food, activities, transport and a safety buffer, per person and per day. Use whenever money, costs or affordability come up.
tools: [calculate_budget_split]
---
# Budget Splitter

## Rules
1. **Never do budget arithmetic yourself.** Always call `calculate_budget_split`
   (from `split.py` in this skill). Quote its numbers exactly.
2. Budgets from the traveler are in **USD per person** unless they say otherwise.
   If the destination uses another currency, call `convert_currency` once for the
   daily spending cap so travelers know what it looks like in local money.
3. Pick the `style` from the trip vibe:
   - `budget` - "cheap", "broke", "student", hostel
   - `balanced` - default
   - `treat-yourself` - "bachelorette", "birthday", "splurge", "spa", "luxury"
4. If the script returns `warnings`, surface every one of them plainly.

## Output format
- A short table: category | per person | whole group
- The **daily spending cap** per person (USD and local currency)
- 2-3 money tips specific to the destination (e.g. tipping norms, free museum days,
  splitting apps like Splitwise)
