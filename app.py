"""TripMate web app.   Run:  streamlit run app.py"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import date, timedelta

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from tripmate import TripRequest, make_llm, plan_trip, revise_trip  # noqa: E402
from tripmate.orchestrator import TEAM  # noqa: E402
from tripmate.revision import EDITOR  # noqa: E402
from tripmate.export import plan_to_html  # noqa: E402

st.set_page_config(page_title="TripMate", page_icon="✈️", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600&family=Inter:wght@400;500;600&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.hero h1 { font-family: 'Fraunces', serif; font-size: 3rem; margin-bottom: 0;
           background: linear-gradient(90deg,#e8590c,#d6336c,#7048e8); -webkit-background-clip: text; color: transparent; }
.hero p { font-size: 1.1rem; opacity: .75; margin-top: .25rem; }
.crew { display:flex; flex-wrap:wrap; gap:.5rem; margin:.75rem 0 1.25rem; }
.crew span { border:1px solid rgba(128,128,128,.25); border-radius:999px; padding:.3rem .8rem; font-size:.85rem; }
div[data-testid="stMetricValue"] { font-family: 'Fraunces', serif; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="hero"><h1>TripMate</h1><p>Plan a group trip in one minute with a crew of 8 AI agents.</p></div>',
            unsafe_allow_html=True)
st.markdown('<div class="crew">' + "".join(f"<span>{a.emoji} {a.name}</span>" for a in TEAM + [EDITOR]) + "</div>",
            unsafe_allow_html=True)

def money(text: str) -> str:
    """Streamlit reads text between two $ signs as a LaTeX math formula, so
    "$35 + subway $6" renders as garbled math. Escaping $ keeps it as dollars."""
    return text.replace("\\$", "$").replace("$", "\\$")


PRESETS = {
    "✏️ My own trip": ("", 2, 800, "", ""),   # blank form: plan any trip you like
    "🎂 Birthday in Lisbon": ("Lisbon", 4, 900, "Birthday girls' trip", "We love brunch and pretty photo spots. One of us is vegetarian. No clubbing."),
    "👰 Nashville bachelorette": ("Nashville", 6, 750, "Bachelorette weekend", "Must hear live music on Broadway. One friend is gluten-free. No early mornings."),
    "🌴 Tulum reset": ("Tulum", 3, 1100, "Chill wellness escape", "Want cenotes and a yoga class. Avoid party beach clubs."),
    "💸 Budget Charleston": ("Charleston", 4, 450, "Cheap girls' weekend", "Love the beach and cute streets for photos. No expensive tours."),
}

# ---- inputs --------------------------------------------------------------- #
with st.sidebar:
    st.subheader("Start from an idea")
    preset = st.radio("Sample trips", list(PRESETS), index=1, label_visibility="collapsed")
    d, ppl, bud, vibe, notes = PRESETS[preset]
    st.divider()
    has_key = bool(os.getenv("ANTHROPIC_API_KEY"))
    demo = st.toggle("Demo mode (no API key)", value=not has_key,
                     help="Runs the real agents, MCP server and skills with a scripted offline brain.")
    offline = st.toggle("Offline sample data", value=False, help="Use bundled data instead of live public APIs.")
    st.caption(f"Brain: **{'Demo' if demo else 'Claude'}** · Data: **{'sample' if offline else 'live APIs'}**")

c1, c2, c3 = st.columns([2, 2, 1])
destination = c1.text_input("Where to?", d, placeholder="A city, e.g. Barcelona")
nxt = date.today() + timedelta(days=(4 - date.today().weekday()) % 7 or 7)
dates = c2.date_input("When?", (nxt, nxt + timedelta(days=3)), min_value=date.today())
people = c3.number_input("Travelers", 1, 20, ppl)
c4, c5 = st.columns([1, 2])
budget = c4.number_input("Budget per person (USD, no flights)", 100, 20000, bud, step=50)
vibe = c5.text_input("Vibe", vibe, placeholder="e.g. Chill beach weekend, foodie trip, 30th birthday")
notes = st.text_area("Anything else? (preferences, must-dos, things to avoid)", notes, height=80,
                     placeholder="e.g. We love hiking and street food. One of us is vegan. No early mornings.")

go = st.button("✨ Plan our trip", type="primary", use_container_width=True)

# ---- run ------------------------------------------------------------------ #
if go:
    if not destination.strip():
        st.error("Where are you going? Add a destination first.")
        st.stop()
    vibe = vibe.strip() or "Trip with friends"
    if not isinstance(dates, tuple) or len(dates) != 2:
        st.error("Pick a start and end date.")
        st.stop()
    req = TripRequest(destination, dates[0].isoformat(), dates[1].isoformat(), int(people), float(budget), vibe, notes)
    status = st.status("Your AI crew is on it…", expanded=True)

    def on_event(ev: dict) -> None:
        t = ev["type"]
        if t == "stage":
            status.update(label=ev["label"])
            status.markdown(f"**{ev['label']}**")
        elif t == "tool_call":
            args = json.dumps(ev["input"], ensure_ascii=False)
            status.caption(f"{ev['emoji']} {ev['agent']} → `{ev['tool']}` {args[:80]}")
        elif t == "done":
            o = ev.get("output") or {}
            note = ""
            if "approved" in o:
                note = " · **approved** ✅" if o["approved"] else " · changes requested: " + "; ".join(o["issues"])
            status.write(money(f"{ev['emoji']} **{ev['agent']}** finished in {ev['seconds']:.1f}s{note}"))

    try:
        plan = asyncio.run(plan_trip(req, llm=make_llm(demo=demo), emit=on_event, offline=offline))
    except Exception as e:  # show friendly error, keep the app alive
        status.update(label="Something went wrong", state="error")
        st.exception(e)
        st.stop()
    status.update(label=f"Trip planned in {plan.stats['seconds']}s", state="complete", expanded=False)
    st.session_state["plan"] = plan

# ---- results -------------------------------------------------------------- #
plan = st.session_state.get("plan")
if plan:
    s = plan.stats
    m = st.columns(5)
    m[0].metric("Planning agents", s["agents"])
    m[1].metric("Tool calls", s["tool_calls"])
    m[2].metric("Review score", f"{s['review_score']}/10", f"{s['revisions']} revision(s)", delta_color="off")
    m[3].metric("Time", f"{s['seconds']}s")
    m[4].metric("Tokens", f"{s['tokens_in'] + s['tokens_out']:,}" if s["tokens_in"] else "demo")
    st.caption(f"Model: {s['model']} · Data sources: {', '.join(s['data_sources'])}")

    st.markdown(money(plan.markdown.split("\n---")[0]))
    tabs = st.tabs(["🗓️ Itinerary", "🌤️ Weather", "💸 Budget", "📍 Local intel", "🧳 Packing", "🛟 Safety", "🔍 Agent trace"])
    for tab, key in zip(tabs, ["Itinerary", "Weather", "Budget", "Local intel", "Packing list", "Safety"]):
        tab.markdown(money(plan.sections[key]))
    with tabs[-1]:
        st.caption("Every agent's tool calls, in order. This is what the orchestrator saw.")
        st.json({"brief": plan.brief})
        for name, r in plan.results.items():
            with st.expander(f"{name} · {len(r.tool_log)} tool calls · {r.seconds:.1f}s"):
                for t in r.tool_log:
                    st.markdown(f"**{t['tool']}** `{json.dumps(t['input'], ensure_ascii=False)}`")
                    st.code(t["output"][:1500], language="json")
    d1, d2 = st.columns([3, 1])
    d1.download_button("⬇️ Download trip plan (opens in any browser · print to PDF)",
                       plan_to_html(plan.markdown, f"TripMate · {plan.brief.get('destination', 'Trip')}"),
                       file_name="trip_plan.html", mime="text/html", type="primary", use_container_width=True)
    d2.download_button("Markdown (.md)", plan.markdown, file_name="trip_plan.md", use_container_width=True)

    # ---- conversational revision ------------------------------------------ #
    st.subheader("💬 Want to change something?")
    st.caption("Try: “make Day 2 more relaxed” · “add a beach afternoon” · “one of us is vegan now”")
    for turn in plan.history:
        st.chat_message("user").write(money(turn["request"]))
        st.chat_message("assistant", avatar="✈️").markdown(money(turn["summary"]))
    msg = st.chat_input("Tell TripMate what to change…")
    if msg:
        st.chat_message("user").write(money(msg))
        with st.status("✏️ Editing your plan…", expanded=True) as edit_status:
            def on_edit(ev: dict) -> None:
                if ev["type"] == "done":
                    o = ev.get("output") or {}
                    note = f" · review {o['score']}/10" if "score" in o else ""
                    edit_status.write(money(f"{ev['emoji']} **{ev['agent']}** finished in {ev['seconds']:.1f}s{note}"))
            st.session_state["plan"] = asyncio.run(revise_trip(plan, msg, llm=make_llm(demo=demo), emit=on_edit))
            edit_status.update(label="Plan updated", state="complete")
        st.rerun()
