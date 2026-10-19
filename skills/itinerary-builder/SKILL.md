---
name: itinerary-builder
description: Turn research (weather, real places, budget) into a realistic day-by-day itinerary. Use when writing or revising the trip plan.
---
# Itinerary Builder

## Rules
1. **Only use real places** that appear in the `find_places_nearby` results or the
   research notes you were given. Never invent restaurant or venue names. For meals,
   describe the type of place and the neighborhood instead ("brunch spot in Alfama").
2. **Respect the weather.** Put outdoor plans (beaches, viewpoints, walking tours)
   on the driest, warmest days; move museums and markets to rainy days.
3. **Pace it like a real trip with friends:** max 3 anchor activities per day,
   a slow morning on at least one day, and one "golden hour" photo moment per day.
4. **Arrival and departure days are light.** Assume arrival mid-afternoon and
   departure around noon.
5. **Stay inside the daily spending cap** from the budget. Mark each activity
   `Free`, `$`, `$$` or `$$$`.
6. **Honor preferences** from the brief (dietary needs, accessibility, "no clubs",
   "must do brunch", etc.) and say where you did.
7. Group nearby places on the same day to cut transit time.
8. **Safety line.** Start the plan with one line giving the local emergency number
   from the country info (e.g. "Emergency number in Portugal: 112").

## Output format
For each day, use exactly this shape. Number the anchors; the numbers ARE the limit.
```
### Day N - <Weekday, Mon DD> - <theme>  (<weather one-liner>)
1. <time> - <anchor activity> (<Free/$/$$/$$$>)
2. <time> - <anchor activity> (...)
3. <time> - <anchor activity> (...)
Golden hour: <one photo moment that is part of an anchor above, not a new stop>
Est. per person: <item €X> + <item €Y> + <transport €Z> = **€total** (cap €<daily cap>)
```
- At most **3** numbered anchors per day; at most **2** on arrival and departure days.
- Meals count as anchors. A short walk between anchors is not an anchor.
- No "optional extras", "if you have time" or bonus lists. If it doesn't fit, leave it out.
- List anchors in chronological order.
- The per-day total must be at or under the daily cap. Include transport.

End with **"Why this works"**: 2-3 bullets tying choices to weather, budget and preferences.
Do not include a packing list; another agent writes it.
