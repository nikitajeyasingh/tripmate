# ✈️ TripMate: a multi-agent group-trip planner

**Tell it where, when, how many friends and your budget. A crew of AI agents plans the
trip, checks its own work, and lets you chat to change it:** a weather-aware day-by-day
itinerary using real places, a fair budget split per person, local tips and a shared
packing list.

Built with **Claude** (tool use), a custom **MCP server + client**, four live
**public APIs** (no keys needed), and **Agent Skills** with progressive disclosure.

```
"Birthday trip to Lisbon, 4 of us, $900 each.
 We love brunch and photo spots. One of us is vegetarian. No clubbing."
```
→ 8 agents · ~15–20 live tool calls · a self-review loop · about 2 minutes.
Then chat to change it: *"make Day 2 more relaxed"*, *"one of us is vegan now"*.

📘 **New to the code? Read [BUILD_GUIDE.md](BUILD_GUIDE.md)**: a step-by-step guide to how it's built.

---

## Architecture

```mermaid
flowchart TD
    U[Trip request<br/>web form or CLI] --> P[🧭 Planner<br/>structured TripBrief]
    P --> W[🌤️ Weather Scout]
    P --> L[📍 Local Expert]
    P --> B[💸 Budget Planner]
    subgraph parallel [Research: run in parallel]
      W
      L
      B
    end
    W & L & B --> BB[(Shared facts<br/>raw tool outputs)]
    BB --> I[🗓️ Itinerary Designer]
    I --> R{✅ Quality Reviewer}
    R -- issues found --> I
    R -- approved --> K[🧳 Packing Assistant]
    K --> OUT[Final trip plan + agent trace]
    OUT <-- chat --> E[✏️ Trip Editor<br/>+ reviewer re-check]

    subgraph MCP [MCP server: tripmate-travel, stdio]
      T1[geocode_city] --- A1[(Open-Meteo)]
      T2[get_weather] --- A1
      T3[get_country_info] --- A2[(Open countries dataset)]
      T4[convert_currency] --- A3[(Frankfurter / ECB)]
      T5[find_places_nearby] --- A4[(Wikipedia)]
      RS[resource: safety-checklist]
    end
    W -. MCP client .-> T1 & T2
    L -. MCP client .-> T1 & T3 & T5
    B -. MCP client .-> T1 & T3 & T4

    subgraph Skills [skills/]
      S1[budget-splitter<br/>SKILL.md + split.py]
      S2[itinerary-builder]
      S3[packing-list]
    end
    B -. load_skill .-> S1
    I -. load_skill .-> S2
    K -. load_skill .-> S3
```

## Where the data comes from

| Agent | Data source | Real or generated? |
|---|---|---|
| 🧭 Planner | The form the user fills in | User input, put into a fixed structure |
| 🌤️ Weather Scout | [Open-Meteo](https://open-meteo.com) geocoding + forecast; historical API for trips more than ~2 weeks out | **Real**: live forecast for the actual dates and city; further out, the real weather from the same dates last year as a "typical weather" estimate |
| 📍 Local Expert | [mledoze/countries](https://github.com/mledoze/countries) (the open dataset behind REST Countries) + [Wikipedia GeoSearch](https://www.mediawiki.org/wiki/Extension:GeoData) | **Real** country facts and landmark names. Not restaurants, ratings or opening hours. Emergency numbers and driving side come from small built-in lists |
| 💸 Budget Planner | Own logic (`split.py`) + [Frankfurter](https://frankfurter.dev) (European Central Bank rates) | **Real arithmetic and a real FX rate**; the split percentages are our estimates, not real prices |
| 🗓️ Itinerary Designer | The research above (may search for more places) | **Generated** from real data; meals are described by type and neighborhood, never invented venue names |
| ✅ Quality Reviewer | Compares the plan with the fetched data | Generated judgment, checked against real data |
| 🧳 Packing Assistant | Weather + itinerary + country | **Generated** |
| ✏️ Trip Editor | The user's chat message + the current plan | User input |
| 🛟 Safety section | MCP resource | Static text we wrote |

**Fallbacks are never silent.** If an API fails, the tool returns bundled sample data marked
`source: offline-sample` with a `fallback_reason`, logs the error to stderr, and the UI lists
which sources were live. Without an API key, demo mode templates the writing while every
agent, tool and skill still runs.

### What each piece demonstrates

| Capability | Where | What to look at |
|---|---|---|
| **Multi-agent orchestration** | `tripmate/orchestrator.py` | 7 planning agents; 3 run in parallel (`asyncio.gather`); evaluator-optimizer loop (reviewer → designer revises); structured hand-offs |
| **MCP server** | `mcp_server/travel_server.py` | 5 tools + 1 resource + 1 prompt (all three MCP primitives), stdio transport, also works in Claude Desktop |
| **MCP client** | `tripmate/mcp_client.py` | Launches the server, discovers tools at runtime, converts MCP schemas to Claude tool schemas |
| **Live data via APIs** | MCP server | Open-Meteo, Frankfurter (ECB), Wikipedia GeoSearch, open countries dataset; no keys needed |
| **Skills** | `skills/*/SKILL.md` | Progressive disclosure: agents see one-line summaries and call `load_skill` on demand. `budget-splitter` ships code (`split.py`) that becomes a tool |
| **Human-in-the-loop** | `tripmate/revision.py` | Chat edits: the Trip Editor changes only what was asked, the Reviewer re-checks, and big changes ask to re-plan |
| **Agent loop** | `tripmate/agents.py` | ~100-line framework-free tool-use loop: parallel tool calls, tool errors returned to the model, structured output via an answer tool |

### Design decisions

- **Least privilege per agent.** The Weather Scout can't call the currency tool. Smaller toolsets mean fewer wrong calls and lower cost.
- **Structured output through tools.** The Planner and Reviewer answer by calling `submit_trip_brief` / `submit_review` with a JSON schema, so the orchestrator branches on real fields (`approved: false`), not on parsing prose. If a model rejects a forced `tool_choice`, the agent is told in its prompt to call the tool and gets one retry nudge.
- **Deterministic guardrails over LLM output.** Dates, head-count and budget from the form overwrite whatever the Planner inferred; `nights` is computed in code.
- **Math in code, not in the model.** Budget arithmetic runs in `split.py`; the skill tells the agent never to calculate itself.
- **Grounding through shared facts.** Raw tool outputs (merged across every search, not just the last one) go to later agents, and the reviewer checks each named place against that list.
- **Matching rules across agents.** The designer's skill and the reviewer's checklist are written to agree, so the designer is never graded on a rule it wasn't given.

## Lessons from testing on live data

| What broke | Cause | Fix |
|---|---|---|
| Reviewer rejected real places like Alfama | The shared facts store kept only the *last* place search | Merge places from every search, including the designer's own |
| Itinerary cut off mid-line | 4,000-token response limit | Raised to 8,000 |
| Designer kept failing review | Its rules contradicted the reviewer's (named restaurants, anchors per day) | Aligned the skill and the reviewer prompt |
| Country and currency data silently fake | REST Countries deprecated its keyless API; Frankfurter moved domains; errors were swallowed | Switched to the open dataset, followed redirects, made fallbacks log and label themselves |
| Wikipedia returned 403 | Robot policy requires contact info in the User-Agent | Added the project URL to the User-Agent |
| `$35 + $6` rendered as math in the UI | Streamlit reads text between `$` signs as LaTeX | Escape `$` outside code spans |

---

## Run it

Requires Python 3.10+.

```bash
cd tripmate
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # then paste your Anthropic key into .env
```

**Web app (best for the demo)**
```bash
streamlit run app.py
```
Pick a sample trip or **✏️ My own trip**, click **Plan our trip**, then chat below the plan to change it.
**⬇️ Download trip plan** saves a standalone HTML page that opens in any browser (Print → Save as PDF for a PDF).

**Command line**
```bash
python cli.py                       # sample Lisbon birthday trip with Claude + live APIs
python cli.py --demo --offline      # no API key, no internet: still runs every agent, MCP and skill
python cli.py --chat                # plan, then chat to change it
python cli.py -d Chicago -s 2026-11-06 -e 2026-11-09 -p 2 -b 600 \
   -v "Foodie weekend" -n "We love deep dish pizza and architecture. No museums."
```
Each run writes `trip_plan.md` and `trip_plan.html`.

**Tests** (no key or internet needed): `pytest -q`

**Inspect the MCP server on its own**
```bash
npx @modelcontextprotocol/inspector python mcp_server/travel_server.py
```

**Use the same MCP server inside Claude Desktop:** add `claude_desktop_config.example.json`
to your Claude Desktop config (fix the path), restart, and ask *"What's the weather in Lisbon next weekend?"*.

### Configuration
| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | (none) | If missing, the app automatically uses demo mode |
| `TRIPMATE_MODEL` | `claude-sonnet-5-5` | Any Claude model ID |
| `TRIPMATE_OFFLINE` | `0` | `1` = MCP server uses bundled sample data |

---

## Project layout
```
tripmate/
├── app.py                     Streamlit UI with live agent trace and chat edits
├── cli.py                     Command-line runner
├── mcp_server/
│   ├── travel_server.py       MCP server: 5 tools, 1 resource, 1 prompt
│   └── fixtures.py            Offline fallback data + small lookup tables
├── skills/
│   ├── budget-splitter/       SKILL.md + split.py (code tool)
│   ├── itinerary-builder/     SKILL.md
│   └── packing-list/          SKILL.md
├── tripmate/
│   ├── contracts.py           Data shapes + structured-output schemas
│   ├── orchestrator.py        The agent team + pipeline
│   ├── revision.py            Chat edits (Trip Editor + re-review)
│   ├── agents.py              Agent tool-use loop
│   ├── mcp_client.py          MCP client → Claude tool schemas
│   ├── skills.py              Skill registry (progressive disclosure)
│   ├── llm.py                 Claude wrapper + model selection
│   ├── demo_llm.py            Offline scripted brain (same protocol)
│   └── export.py              Printable HTML export of the plan
└── tests/test_tripmate.py
```

## What I'd do next
- **Evals:** ~30 varied trip requests, several runs each, scored on grounding (are all places real?), budget fit and preference coverage; tracked on every prompt change. One Chicago trip scored 6/10 on one run and 8/10 on the next, which is why single runs aren't enough.
- **LangGraph for orchestration** once the flow needs pause-and-resume (e.g. friends voting on a draft), persistent trip threads and checkpointing. The MCP server and skills wouldn't change.
- **Prompt caching** on system prompts and skills to cut cost and latency; a smaller model for simple agents.
- **Streaming** the itinerary into the UI.
- **More MCP tools:** restaurants (e.g. Geoapify), flights and hotels, walking times.
- **Currency picker** for travelers who don't budget in USD.
- **Observability:** OpenTelemetry spans per agent and tool call; per-trip cost reporting.
- **Remote MCP** over Streamable HTTP with auth, so the travel tools serve many apps.
