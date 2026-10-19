"""Offline 'demo brain' - a deterministic stand-in for Claude.

It speaks the exact same protocol (returns text / tool_use blocks), so the real
orchestrator, real agent loop, real MCP server and real skills all run. Only the
language generation is templated. Use it to demo without an API key or Wi-Fi:

    python cli.py --demo
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import uuid
from datetime import date, timedelta

OUTDOOR = re.compile(r"beach|park|garden|miradouro|viewpoint|tower|bridge|street|row|battery|cenote|playa|square|quarter|district|alley|tram|creek|tree|ruins|lagoon|laguna|walk|highway|alto|alfama|real|seine", re.I)
INDOOR = re.compile(r"museum|musée|hall|market|monastery|gallery|auditorium|louvre|orsay|opry|lafayette|azulik|maat|feira|time out", re.I)
WET = re.compile(r"rain|shower|drizzle|thunder|snow", re.I)


def _id() -> str:
    return "toolu_demo_" + uuid.uuid4().hex[:12]


def _call(_tool: str, **inp) -> dict:
    return {"type": "tool_use", "id": _id(), "name": _tool, "input": inp}


def _reply(*blocks) -> dict:
    stop = "tool_use" if any(b["type"] == "tool_use" for b in blocks) else "end_turn"
    return {"content": list(blocks), "stop_reason": stop, "usage": {"input": 0, "output": 0}}


def _text(s: str) -> dict:
    return {"type": "text", "text": s.strip()}


class DemoLLM:
    name = "Demo mode (offline, templated)"

    async def respond(self, *, agent, system, messages, tools, tool_choice=None):
        if os.getenv("TRIPMATE_DEMO_FAST") != "1":
            await asyncio.sleep(random.uniform(0.5, 1.2))  # feel like a real model call
        first = messages[0]["content"]
        m = re.search(r"<context>(.*?)</context>", first, re.S)
        ctx = json.loads(m.group(1)) if m else {}
        done: dict[str, object] = {}
        names = {}
        for msg in messages:
            if msg["role"] == "assistant":
                for b in msg["content"]:
                    if b["type"] == "tool_use":
                        names[b["id"]] = (b["name"], b["input"])
            elif isinstance(msg["content"], list):
                for b in msg["content"]:
                    nm, inp = names.get(b.get("tool_use_id"), (None, None))
                    if nm:
                        try:
                            done[nm] = json.loads(b["content"])
                        except (json.JSONDecodeError, TypeError):
                            done[nm] = b["content"]
        fn = getattr(self, "_" + agent.lower().replace(" ", "_"))
        return fn(ctx, done, first)

    # ------------------------------------------------------------------ #
    def _planner(self, ctx, done, _):
        req = ctx["request"]
        vibe = req.get("vibe", "trip")
        v = vibe.lower()
        style = "treat-yourself" if re.search(r"bachelor|birthday|spa|luxur|splurge|treat", v) else \
                "budget" if re.search(r"cheap|budget|student|broke", v) else "balanced"
        prefs, must, avoid = [], [], []
        for part in re.split(r"[.;\n]|, (?=[a-z])", req.get("notes", "")):
            p = part.strip()
            if not p:
                continue
            if re.search(r"vegetarian|vegan|gluten|allerg|dairy|halal|kosher|accessib|wheelchair|knee", p, re.I):
                prefs.append(p)
            elif re.search(r"\b(no|avoid|hate|not into|skip)\b", p, re.I):
                avoid.append(p)
            else:
                must.append(p)
        return _reply(_call("submit_trip_brief", destination=req["destination"].split(",")[0].strip(),
                            start_date=req["start_date"], end_date=req["end_date"], people=req["people"],
                            budget_per_person_usd=req["budget_per_person"], budget_style=style,
                            vibe=vibe, preferences=prefs, must_do=must, avoid=avoid))

    def _weather_scout(self, ctx, done, _):
        b = ctx["brief"]
        if "geocode_city" not in done:
            return _reply(_text("Let me find the destination first."), _call("geocode_city", city=b["destination"]))
        g = done["geocode_city"]
        if "get_weather" not in done:
            return _reply(_call("get_weather", latitude=g["latitude"], longitude=g["longitude"],
                                start_date=b["start_date"], end_date=b["end_date"]))
        w = done["get_weather"]
        days = w["days"]
        hi = [d["high_f"] for d in days]
        lo = [d["low_f"] for d in days]
        best = max(days, key=lambda d: (not WET.search(d["conditions"]), d["high_f"]))
        wet = [d for d in days if WET.search(d["conditions"])]
        lines = "\n".join(f"- **{_fmt(d['date'])}**: {d['high_f']:.0f}° / {d['low_f']:.0f}°F, {d['conditions'].lower()}" for d in days)
        indoor = f"Keep **{', '.join(_fmt(d['date']) for d in wet)}** for museums, markets and long lunches." if wet else "No washouts expected, so outdoor plans are safe all trip."
        return _reply(_text(f"""
**{g['city']}: highs {min(hi):.0f}–{max(hi):.0f}°F, lows {min(lo):.0f}–{max(lo):.0f}°F.** {"Mostly dry, light-layers weather." if len(wet) <= 1 else "A few wet spells, so bring a rain layer."}

{lines}

- ☀️ **Best outdoor day:** {_fmt(best['date'])} ({best['conditions'].lower()}, {best['high_f']:.0f}°F). Save viewpoints and photo walks for this one.
- ☔ {indoor}

_Data: {w['type']} · source: {w['source']}_"""))

    def _local_expert(self, ctx, done, _):
        b = ctx["brief"]
        if "geocode_city" not in done:
            return _reply(_call("geocode_city", city=b["destination"]))
        g = done["geocode_city"]
        if "get_country_info" not in done:
            return _reply(_text("Fetching country facts and real places in parallel."),
                          _call("get_country_info", country_code=g["country_code"]),
                          _call("find_places_nearby", latitude=g["latitude"], longitude=g["longitude"]))
        c, places = done["get_country_info"], done["find_places_nearby"]["places"][:12]
        plug = "No adapter needed for US travelers." if c.get("country") == "United States" else \
               "Bring a **plug adapter** (US plugs won't fit)."
        top = "\n".join(f"- **{p['name']}**: {_why(p['name'])}" for p in places)
        return _reply(_text(f"""
### Know before you go
- 🗣️ Language: {', '.join(c['languages'])}
- 💱 Currency: {c['currency_name']} ({c['currency_code']} {c.get('currency_symbol') or ''})
- 🚨 Emergency number: **{c['emergency_number']}**. Save it in your phone before you land.
- 🚗 Traffic drives on the {c.get('drives_on', 'right')}. {plug}

### Best real spots for your crew
{top}

_Places from Wikipedia geosearch · source: {done['find_places_nearby']['source']}_"""))

    def _budget_planner(self, ctx, done, _):
        b = ctx["brief"]
        if "calculate_budget_split" not in done:
            return _reply(_text("Loading my budget skill and running the numbers."),
                          _call("load_skill", name="budget-splitter"),
                          _call("geocode_city", city=b["destination"]),
                          _call("calculate_budget_split", budget_per_person=b["budget_per_person_usd"],
                                people=b["people"], nights=b["nights"], style=b["budget_style"]))
        if "get_country_info" not in done:
            return _reply(_call("get_country_info", country_code=done["geocode_city"]["country_code"]))
        s, c = done["calculate_budget_split"], done["get_country_info"]
        cap = s["daily_spending_cap_per_person"]
        if c["currency_code"] != "USD" and "convert_currency" not in done:
            return _reply(_call("convert_currency", amount=cap, from_currency="USD", to_currency=c["currency_code"]))
        local = f" (≈ {c.get('currency_symbol') or ''}{done['convert_currency']['converted']:,.0f} {c['currency_code']})" if "convert_currency" in done else ""
        rows = "\n".join(f"| {k.replace('_', ' ').title()} | ${v:,.0f} | ${s['whole_group'][k]:,.0f} |" for k, v in s["per_person"].items())
        warn = "".join(f"\n> ⚠️ {x}" for x in s["warnings"])
        tip = "Tipping is modest here; rounding up or ~5-10% at sit-down meals is plenty." if c["currency_code"] != "USD" else "Budget 18-20% tips on sit-down meals and drinks."
        return _reply(_text(f"""
**Style: {s['style']}** · group total ${s['group_total']:,.0f} (excluding flights)

| Category | Per person | Whole group |
|---|---|---|
{rows}

💳 **Daily spending cap: ${cap:,.0f} per person{local}** for food, fun and getting around.
🏠 Look for lodging around **${s['lodging_budget_per_night_group']:,.0f}/night** for the whole group.{warn}

**Money tips**
- Make one Splitwise group before the trip and log shared costs as you go.
- {tip}
- Keep the buffer untouched until the last day, then spend it on a farewell dinner."""))

    def _itinerary_designer(self, ctx, done, first):
        if "load_skill" not in done:
            return _reply(_call("load_skill", name="itinerary-builder"))
        b, f = ctx["brief"], ctx["facts"]
        places = [p["name"] for p in f["find_places_nearby"]["places"]]
        out_pl = [p for p in places if OUTDOOR.search(p) and not INDOOR.search(p)]
        in_pl = [p for p in places if INDOOR.search(p)]
        other = [p for p in places if p not in out_pl and p not in in_pl]
        out_pl += other
        days = f["get_weather"]["days"]
        cap = f["calculate_budget_split"]["daily_spending_cap_per_person"]
        must = list(b.get("must_do", []))
        revising = "<reviewer_feedback>" in first
        themes = ["Arrive & golden hour", "Explore & eat", "Culture & sunsets", "Slow day & hidden gems", "Last bites"]
        md = []
        for i, d in enumerate(days):
            wet = bool(WET.search(d["conditions"]))
            pool_a, pool_b = (in_pl, out_pl) if wet else (out_pl, in_pl)
            pick = lambda: (pool_a.pop(0) if pool_a else pool_b.pop(0) if pool_b else "a wander through the nearest neighborhood")  # noqa: E731
            last = i == len(days) - 1
            theme = "Farewell brunch & fly home" if last and i else themes[min(i, len(themes) - 2)]
            head = f"### Day {i + 1} · {_fmt(d['date'], True)} · {theme}  ({d['conditions']}, {d['high_f']:.0f}°F)"
            if i == 0:
                body = [f"- **Afternoon:** Check in, drop bags, then stroll to **{pick()}** (Free)",
                        f"- **Evening:** Welcome dinner at a lively spot nearby ($$)",
                        f"- **Golden hour:** Group photo at **{pick()}** 📸"]
            elif last:
                body = [f"- **Morning:** Slow farewell brunch near your stay ($$)",
                        f"- **Late morning:** One last look at **{pick()}** before heading to the airport (Free)"]
            else:
                a, c2, e = pick(), pick(), pick()
                body = [f"- **Morning:** {'Sleep in, then ' if i == 2 else ''}**{a}** ({_price(a)})",
                        f"- **Afternoon:** **{c2}** ({_price(c2)}), then coffee and people-watching",
                        f"- **Evening:** Dinner and drinks around **{e}** ($$)",
                        f"- **Golden hour:** Catch the sunset from the highest spot near **{e}** 📸"]
                if must:
                    body.insert(1, f"- **Must-do ✔:** {must.pop(0)}")
            md.append(head + "\n" + "\n".join(body))
        extra = "".join(f"\n- **Must-do ✔:** {m} (fit in on any free afternoon)" for m in must)
        why = [f"Outdoor stops sit on the driest, warmest days; indoor spots cover wetter ones.",
               f"Every day stays inside the **${cap:,.0f}/person** daily cap: mostly free sights, one paid activity, one sit-down meal."]
        if b.get("preferences"):
            why.append("Preferences honored: " + "; ".join(b["preferences"]) + ". Dinner areas picked for plenty of options.")
        if b.get("avoid"):
            why.append("Kept off the plan: " + "; ".join(b["avoid"]) + ".")
        safety = ""
        if revising:
            num = f.get("get_country_info", {}).get("emergency_number", "112")
            safety = f"\n\n🚨 **Safety:** local emergency number is **{num}**. Share your live location in the group chat on nights out."
        return _reply(_text("\n\n".join(md) + extra + safety + "\n\n**Why this works**\n" + "\n".join(f"- {w}" for w in why)))

    def _quality_reviewer(self, ctx, done, _):
        it, f = ctx["itinerary"], ctx["facts"]
        places = {p["name"] for p in f["find_places_nearby"]["places"]}
        named = set(re.findall(r"\*\*([^*]+)\*\*", it)) - {"Morning:", "Afternoon:", "Evening:", "Golden hour:", "Late morning:", "Must-do ✔:", "Why this works", "Safety:", "a wander through the nearest neighborhood", "Your request:"}
        unknown = [n for n in named if n not in places and not n.startswith("$") and not re.match(r"[\d$]", n)]
        num = f.get("get_country_info", {}).get("emergency_number", "112")
        issues = []
        if "emergency" not in it.lower():
            issues.append(f"The plan never mentions the local emergency number ({num}). Add a short safety note.")
        if unknown:
            issues.append("These names aren't in the research places list: " + ", ".join(sorted(unknown)[:5]))
        return _reply(_call("submit_review", approved=not issues, score=9 if not issues else 7, issues=issues,
                            praise="Good pacing with light arrival and departure days, and weather-aware ordering."))

    def _packing_assistant(self, ctx, done, _):
        if "load_skill" not in done:
            return _reply(_call("load_skill", name="packing-list"))
        b, w = ctx["brief"], ctx["weather_data"]["days"]
        hi, lo = max(d["high_f"] for d in w), min(d["low_f"] for d in w)
        wet = sum(bool(WET.search(d["conditions"])) for d in w)
        n = len(w)
        beach = bool(re.search(r"beach|playa|cenote|pool", ctx["itinerary"], re.I))
        warm, cold = hi >= 75, lo < 50
        clothes = [f"{n} tops ({'breathable, light' if warm else 'layer-friendly'})", f"{max(2, n - 1)} bottoms (jeans + {'shorts/skirt' if warm else 'trousers'})",
                   "1 going-out outfit for the nice dinner", "1 cozy outfit for travel days",
                   "Light jacket or denim jacket" if not cold else "Warm coat + scarf", f"{n + 1} sets underwear & socks", "Pajamas"]
        if beach:
            clothes += ["Swimsuit + cover-up"]
        if wet:
            clothes += ["Packable rain jacket"]
        shoes = ["Comfy walking sneakers (you'll walk 15k+ steps)", "1 pair cute flats/sandals for evenings"]
        toil = ["Travel-size skincare & makeup", "SPF 30+ sunscreen (face)", "Lip balm with SPF", "Meds + period products", "Hair ties & claw clip"]
        tech = ["Phone + charger", "Power bank", "Earbuds"]
        abroad = (ctx.get("country") or {}).get("country", "United States") != "United States"
        if abroad:
            tech.append("Universal plug adapter")
        docs = ["Passport (check 6+ months validity)" if abroad else "Driver's license / ID", "Credit card with no foreign fees" if abroad else "Credit/debit card", "Small amount of cash", "Insurance card / travel insurance info"]
        shared = ["Hair straightener / curler (one for the group)", "Bluetooth speaker", "Mini first-aid kit", "Big bottle of body sunscreen"]
        if wet:
            shared.append("Compact umbrella or two")
        sec = lambda t, xs: f"**{t}**\n" + "\n".join(f"- [ ] {x}" for x in xs)  # noqa: E731
        return _reply(_text(f"""
_Highs up to {hi:.0f}°F, lows down to {lo:.0f}°F{f', {wet} wet day(s)' if wet else ', dry'}. Carry-on friendly, plan to re-wear bottoms._

{sec('Clothes', clothes)}

{sec('Shoes', shoes)}

{sec('Toiletries & beauty', toil)}

{sec('Tech', tech)}

{sec('Documents & money', docs)}

{sec('Shared items (split these!)', shared)}"""))

    def _trip_editor(self, ctx, done, first):
        """Simple keyword rules that imitate an editor. Claude handles any wording."""
        req = re.search(r"<change_request>\s*(.*?)\s*</change_request>", first, re.S).group(1)
        it, packing = ctx["itinerary"], ctx["packing_list"]
        new_it, new_pack, prefs = "", "", []

        def submit(summary):
            return _reply(_call("submit_changes", itinerary=new_it, packing_list=new_pack,
                                new_preferences=prefs, change_summary=summary))

        if re.search(r"destination|different city|dates?\b|budget|\$\s?\d|\d+\s*(people|friends|of us)", req, re.I):
            return submit("That changes the whole trip and needs fresh research, so please update the form "
                          "and click **Plan our trip** again.")

        n_days = len(re.findall(r"^### Day ", it, re.M))
        m = re.search(r"day\s*(\d+)", req, re.I)
        day = min(int(m.group(1)), n_days) if m else min(2, n_days)
        block_re = re.compile(rf"### Day {day} .*?(?=\n### Day |\n\n🚨|\n\n\*\*Why this works|\Z)", re.S)
        block = block_re.search(it).group(0)
        places = [p["name"] for p in ctx["facts"]["find_places_nearby"]["places"]]

        def set_slot(blk, slot, text):
            line = f"- **{slot}:** {text}"
            pattern = rf"^- \*\*{slot}:\*\*.*$"
            return re.sub(pattern, line, blk, count=1, flags=re.M) if re.search(pattern, blk, re.M) else blk + "\n" + line

        diet = re.search(r"vegan|vegetarian|gluten[- ]free|halal|kosher|dairy[- ]free|nut allerg\w*", req, re.I)
        if diet:
            word = diet.group(0).lower()
            prefs = [word.capitalize()]
            new_it = it.replace("**Why this works**", "**Why this works**\n"
                                f"- Dietary: dinner areas picked for plenty of {word} options. "
                                "Check menus ahead and book where you can.", 1)
            return submit(f"Got it, I noted **{word}** and adjusted the dining notes.")

        if re.search(r"relax|chill|slow|lazy|tired|rest", req, re.I):
            b = set_slot(block, "Morning", "Sleep in, then a slow coffee near your stay (Free)")
            b = set_slot(b, "Afternoon", "Free time: nap, read, or wander with no plan (Free)")
            new_it = it.replace(block, b)
            return submit(f"Day {day} is now a slow day: lie-in and a free afternoon. Evening plans stay the same.")

        if re.search(r"beach|swim|pool|cenote", req, re.I):
            spot = next((p for p in places if re.search(r"beach|playa|cenote|folly|pool", p, re.I)), None)
            text = f"Beach afternoon at **{spot}** (Free)" if spot else "Afternoon at the nearest beach or pool (Free)"
            new_it = it.replace(block, set_slot(block, "Afternoon", text))
            if "Swimsuit" not in packing:
                new_pack = packing.replace("- [ ] Pajamas", "- [ ] Pajamas\n- [ ] Swimsuit + cover-up")
            return submit(f"Added a beach afternoon on Day {day}" + (" and put a swimsuit on the packing list." if new_pack else "."))

        if re.search(r"rain|indoor|museum|art", req, re.I):
            spot = next((p for p in places if INDOOR.search(p) and p not in it), None) or \
                   next((p for p in places if INDOOR.search(p)), None)
            text = f"**{spot}** ($), a cozy indoor pick" if spot else "Indoor afternoon: a café, a market or a museum ($)"
            new_it = it.replace(block, set_slot(block, "Afternoon", text))
            return submit(f"Swapped Day {day}'s afternoon for something indoors.")

        new_it = it.replace(block, block + f"\n- **Your request:** {req}")
        return submit(f"Added your request to Day {day}. (Demo mode uses simple rules; with Claude any wording works.)")


# --------------------------------------------------------------------------- #
def _fmt(iso: str, weekday: bool = False) -> str:
    d = date.fromisoformat(iso)
    return d.strftime("%a %b %-d") if weekday else d.strftime("%a %b %-d")


def _price(p: str) -> str:
    return "$" if INDOOR.search(p) else "Free"


def _why(p: str) -> str:
    if re.search(r"museum|musée|gallery|maat|louvre|orsay|gibbes|frist", p, re.I):
        return "great rainy-day pick with gorgeous interiors."
    if re.search(r"market|food|time out|café|pastéis", p, re.I):
        return "graze, sample and split plates. Perfect for groups."
    if re.search(r"beach|playa|cenote|folly", p, re.I):
        return "swim, sun and the best group photos of the trip."
    if re.search(r"miradouro|view|tower|castle|sacré|bridge|battery", p, re.I):
        return "big views. Go at golden hour."
    if re.search(r"street|quarter|alto|alfama|marais|district|gulch|south|row|real", p, re.I):
        return "wander the shops, cafés and colorful streets."
    return "a local favorite worth a stop."
