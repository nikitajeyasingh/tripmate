# A Beginner's Step-by-Step Guide to Building a Multi-Agent Trip Planner

This guide walks through how **TripMate** is built, one small step at a time. Every
code snippet comes from the real project, sometimes shortened. You can follow it
to rebuild the project yourself, or use it to explain any part in an interview.

**Time needed:** about 3-5 hours if you build it yourself; 1 hour to read and run it.

---

## Contents
1. What You're Building, in Plain English
2. Where the Data Comes From
3. Core Concepts You'll Learn
4. What You Need Before Starting
5. Project Setup
6. Step 1 – Design the Data Contracts
7. Step 2 – Build the MCP Server (the tools)
8. Step 3 – Build the MCP Client
9. Step 4 – Build Each Agent
10. Step 5 – Wire the Agents Together (the orchestration graph)
11. Step 6 – Add a Skill
12. Step 7 – Build the UI
13. Step 8 – Add Conversational Revision
14. Step 9 – Test the Self-Correction Loop
15. Resource Checklist
16. Common Beginner Mistakes
17. Glossary

---

## 1. What You're Building, in Plain English

Planning a trip with friends usually means a long group chat, many browser tabs,
and one person doing all the work. **TripMate** does that work with a small team
of AI "agents". Each agent is good at one job, like a real travel crew:

| Agent | Its one job |
|---|---|
| 🧭 Planner | Reads your request and turns it into a clear, structured brief |
| 🌤️ Weather Scout | Checks the weather for your exact dates |
| 📍 Local Expert | Finds real places and practical facts (language, currency, emergency number) |
| 💸 Budget Planner | Splits the budget fairly and gives a daily spending limit |
| 🗓️ Itinerary Designer | Writes the day-by-day plan |
| ✅ Quality Reviewer | Checks the plan and sends it back if something is wrong |
| 🧳 Packing Assistant | Makes a packing list based on weather and activities |
| ✏️ Trip Editor | Changes the plan when you chat with it ("make Day 2 more relaxed") |

**You type:**
> Lisbon, Nov 6-9, 4 friends, $900 each, birthday trip. We love brunch and photo spots. One of us is vegetarian. No clubbing.

**You get:** a day-by-day itinerary, a weather summary, a budget table, local tips,
a packing list, a safety checklist, and a chat box to change anything.

---

## 2. Where the Data Comes From

This is an important question in any AI project: **what is real, and what does the
model make up?** Here is the honest answer for every part of TripMate.

| Agent | Data source | Real or mocked? |
|---|---|---|
| 🧭 Planner | What the user types in the form | **User input**, not external data. Claude only puts it into a fixed structure. |
| 🌤️ Weather Scout | [Open-Meteo](https://open-meteo.com) Geocoding API (city → coordinates) and Forecast API. For trips more than ~2 weeks away: Open-Meteo Historical API | **Real.** A live forecast for the actual dates and city if the trip is within ~2 weeks. Further out, it uses the **real weather from the same dates last year** as a "typical weather" estimate (forecasts don't go that far). |
| 📍 Local Expert | [REST Countries](https://restcountries.com) (language, currency, driving side) + [Wikipedia GeoSearch](https://www.mediawiki.org/wiki/Extension:GeoData) (notable places near the city center) | **Real** facts and **real** landmark names with distances. *Not* restaurants, ratings or opening hours. The emergency number comes from a **small built-in list** we wrote (default 112). |
| 💸 Budget Planner | Our own Python logic (`split.py`) + [Frankfurter](https://frankfurter.dev) exchange rates (European Central Bank) | **Real arithmetic** and a **real exchange rate**. The split percentages (e.g. 40% lodging) are **our own estimates**, not real prices. |
| 🗓️ Itinerary Designer | No new API. Combines the weather, places and budget above (it *may* call the places tool again) | **Generated** by Claude from real data. It is told never to invent restaurant names, so meals say "brunch spot in Alfama" instead. |
| ✅ Quality Reviewer | Compares the itinerary with the fetched data | **Generated** judgment, checked against real data |
| 🧳 Packing Assistant | Derived from weather + itinerary + country (for the plug adapter) | **Generated**, not fetched |
| ✏️ Trip Editor | The user's chat message + the current plan | **User input** |
| 🛟 Safety section | An MCP *resource* in our server | **Static text** we wrote |

**Two backup modes** (so a demo never breaks):

| Situation | What happens | Labelled as |
|---|---|---|
| An API is down, or "Offline sample data" is on | The MCP tool returns bundled sample data from `fixtures.py` | `source: offline-sample` (shown in the UI) |
| No Anthropic API key, or "Demo mode" is on | Agents, tools, MCP server and skills all still run; only the **writing** is templated | "Demo mode" in the UI |

> **Why Wikipedia and not OpenTripMap or Geoapify?** They give restaurants and
> categories, but need an API key. Wikipedia needs none, so anyone can run the
> project. Upgrading later is easy: add one new tool to the MCP server (see Step 2).

---

## 3. Core Concepts You'll Learn

**LLM (Large Language Model).** The AI that reads and writes text. Here: Claude.

**Tool use (also called function calling).** The model can't browse the internet
by itself. Instead, you describe some functions ("tools") to it. When it needs
data, it replies: *"please run `get_weather` with these inputs."* **Your code**
runs the function and sends back the result. The model then continues.

**Agent.** An LLM + a job description (system prompt) + some tools, running in a
loop until the job is done.

**Agent loop.** The heart of every agent:
```
ask the model → it asks for tools → run tools → send results back → repeat
                                                 until it gives a final answer
```

**Multi-agent system.** Several focused agents instead of one agent that does
everything. Like a team: each member has a small job, so each does it better.

**Orchestrator.** The "manager" code that decides which agent runs when, what
information each one gets, and what happens next.

**MCP (Model Context Protocol).** An open standard for connecting AI apps to tools.
Think of it as **USB-C for AI**: build the tool server once, and any MCP app
(your app, Claude Desktop, Claude Code) can plug into it.

**Skill.** A folder with instructions (`SKILL.md`) and sometimes code, which an
agent loads **only when it needs it**. This keeps prompts short.

**Structured output.** Making the model answer in a fixed format (JSON with known
fields) so your code can use the answer reliably.

---

## 4. What You Need Before Starting

**Knowledge**
- Basic Python: functions, dictionaries, lists, classes
- How to use a terminal (`cd`, run a command)
- Helpful but not required: `async`/`await` (explained when we use it)

**Software**
- **Python 3.10 or newer** (`python --version`)
- A code editor such as **VS Code**
- *Optional:* **Node.js**, only for the MCP Inspector debugging tool

**Accounts**
- An **Anthropic API key** from [console.anthropic.com](https://console.anthropic.com).
  A full trip plan makes roughly 10-20 API calls, so a few dollars of credit is plenty for building and testing.
- **No other keys needed.** All the travel APIs are free and keyless.

---

## 5. Project Setup

**1. Create the folders**
```
tripmate/
├── mcp_server/          the tools (Step 2)
├── skills/              instructions + scripts (Step 6)
├── tripmate/            agents and orchestration (Steps 1, 3, 4, 5, 8)
├── tests/               (Step 9)
├── app.py               the web UI (Step 7)
└── cli.py               command-line version
```

**2. Create a virtual environment and install libraries**
```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```
`requirements.txt`:
```
anthropic>=0.40       # talk to Claude
mcp>=1.9,<2           # MCP server + client (pin <2, see Mistakes)
httpx>=0.27           # call web APIs
streamlit>=1.38       # web UI
python-dotenv>=1.0    # read the API key from .env
pytest>=8.0           # tests
```

**3. Store your API key safely**

Create a file named `.env` (and add `.env` to `.gitignore` so it's never uploaded):
```
ANTHROPIC_API_KEY=sk-ant-...
```

✅ **Checkpoint:** `python -c "import anthropic, mcp, streamlit; print('ready')"` prints `ready`.

---

## 6. Step 1 – Design the Data Contracts

**File:** `tripmate/contracts.py`

Before writing any agent, decide **what shape the data has** when it moves between
parts of the system. This is the "contract". If everyone agrees on it, you can
build and test each piece on its own.

**What the user sends in:**
```python
@dataclass
class TripRequest:
    destination: str
    start_date: str            # YYYY-MM-DD
    end_date: str
    people: int = 4
    budget_per_person: float = 800
    vibe: str = "Girls' weekend"
    notes: str = ""
```

**What the system returns:**
```python
@dataclass
class TripPlan:
    brief: dict                  # structured version of the request
    sections: dict[str, str]     # "Itinerary", "Weather", "Budget", ...
    markdown: str                # everything joined, ready to download
    results: dict                # each agent's output + tool calls (the trace)
    facts: dict                  # raw API data the agents fetched
    history: list[dict]          # chat revisions
```

**How an agent must answer** (structured output). We describe a pretend tool with
a JSON schema. The agent "calls" it, and **the arguments it passes are the answer**:
```python
REVIEW_TOOL = {
    "name": "submit_review",
    "description": "Submit your quality review of the itinerary.",
    "input_schema": {
        "type": "object",
        "properties": {
            "approved": {"type": "boolean"},
            "score":    {"type": "integer", "minimum": 1, "maximum": 10},
            "issues":   {"type": "array", "items": {"type": "string"}},
            "praise":   {"type": "string"},
        },
        "required": ["approved", "score", "issues", "praise"],
    },
}
```
Now the orchestrator can simply check `review["approved"]`. No guessing from text.

> 💬 **Interview line:** "I designed the data contracts first, so every agent had a clear input and output and I could test each one alone."

---

## 7. Step 2 – Build the MCP Server (the tools)

**File:** `mcp_server/travel_server.py`

The MCP server is a small program that **offers tools**. Our server wraps the free
travel APIs. With the `FastMCP` helper, a normal Python function becomes a tool by
adding one line, `@mcp.tool()`:

```python
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("tripmate-travel")

@mcp.tool()
async def geocode_city(city: str) -> str:
    """Find a city's coordinates, country and timezone. Call this first;
    other tools need the latitude/longitude it returns."""
    try:
        data = await _get("https://geocoding-api.open-meteo.com/v1/search",
                          {"name": city, "count": 1})
        hit = data["results"][0]
        return json.dumps({"city": hit["name"], "country_code": hit["country_code"],
                           "latitude": hit["latitude"], "longitude": hit["longitude"],
                           "source": "open-meteo"})
    except Exception:
        return json.dumps(fixtures.geocode(city))   # offline backup data

if __name__ == "__main__":
    mcp.run()        # talk over stdio (standard input/output)
```

Three things to notice:
1. **The docstring matters.** It becomes the tool description that Claude reads to decide *when* to use the tool. Write it for the model.
2. **Type hints become the input schema.** `city: str` tells Claude what to send.
3. **Every tool has a fallback** and says where its data came from (`source`).

Our server has **5 tools**: `geocode_city`, `get_weather`, `get_country_info`,
`convert_currency`, `find_places_nearby`. It also shows the other two MCP features:
- a **resource** (read-only data): `tripmate://safety-checklist`
- a **prompt** (a reusable prompt template): `plan_trip`

**Adding a new data source later** (e.g. Geoapify restaurants) is just one more
`@mcp.tool()` function. No agent code changes, except giving that tool to an agent.

✅ **Checkpoint:** open the visual tester and call `geocode_city` with "Lisbon":
```bash
npx @modelcontextprotocol/inspector python mcp_server/travel_server.py
```

---

## 8. Step 3 – Build the MCP Client

**File:** `tripmate/mcp_client.py`

The client **starts the server**, asks it "what tools do you have?", and lets our
agents call those tools. It also converts each tool's description into the format
the Claude API expects.

```python
class MCPToolbox:
    async def __aenter__(self):
        params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()                       # handshake
        for t in (await self.session.list_tools()).tools:      # discover tools
            self.schemas[t.name] = {"name": t.name,            # MCP format -> Claude format
                                    "description": t.description,
                                    "input_schema": t.inputSchema}
        return self

    async def call(self, name, args) -> str:
        result = await self.session.call_tool(name, args)
        return result.content[0].text
```

Use it like this:
```python
async with MCPToolbox() as box:
    print(await box.call("geocode_city", {"city": "Lisbon"}))
```

> 💡 **Why `async with`?** It makes sure the server process is always shut down
> cleanly, even if something goes wrong.

✅ **Checkpoint:** the snippet above prints Lisbon's coordinates.

---

## 9. Step 4 – Build Each Agent

**File:** `tripmate/agents.py`

We write **one** `Agent` class and create seven agents from it. Each agent is just
a name, a job description and a list of allowed tools:

```python
WEATHER = Agent(
    "Weather Scout", "🌤️",
    "You are TripMate's Weather Scout. Geocode the destination, then fetch weather "
    "for the exact trip dates. Report a summary, a line per day, and the best day "
    "for outdoor plans...",
    mcp_tools=["geocode_city", "get_weather"],        # only what it needs
)
```

**The agent loop** (shortened from `Agent.run`). This is the most important code
in the project. Make sure you can explain it:

```python
messages = [{"role": "user", "content": task}]
for _ in range(self.max_turns):                      # safety limit, never loop forever
    reply = await llm.respond(system=system, messages=messages, tools=tools)
    messages.append({"role": "assistant", "content": reply["content"]})

    calls = [b for b in reply["content"] if b["type"] == "tool_use"]
    if not calls:                                    # no tool requests = final answer
        return text_of(reply)

    # run ALL requested tools at the same time
    results = await asyncio.gather(*(run_one(c) for c in calls))
    messages.append({"role": "user", "content": results})   # send results back
```

Each tool result goes back with the **same id** as the request:
```python
{"type": "tool_result", "tool_use_id": call["id"], "content": output, "is_error": False}
```
If a tool fails, we send the error back (`is_error: True`) instead of crashing.
The model can then try something else.

**All agents and their tools:**

| Agent | MCP tools | Skill | Answer format |
|---|---|---|---|
| 🧭 Planner | none | none | `submit_trip_brief` (structured) |
| 🌤️ Weather Scout | geocode, weather | none | text |
| 📍 Local Expert | geocode, country info, places | none | text |
| 💸 Budget Planner | geocode, country info, currency | budget-splitter | text |
| 🗓️ Itinerary Designer | places | itinerary-builder | text |
| ✅ Quality Reviewer | none | none | `submit_review` (structured) |
| 🧳 Packing Assistant | none | packing-list | text |
| ✏️ Trip Editor | none | none | `submit_changes` (structured) |

> 💬 **Interview line:** "Each agent only gets the tools it needs, called least privilege. Fewer tools means fewer wrong choices and lower cost."

---

## 10. Step 5 – Wire the Agents Together (the orchestration graph)

**File:** `tripmate/orchestrator.py`

```
            Trip request
                 │
            🧭 Planner
                 │
   ┌─────────────┼─────────────┐     run IN PARALLEL
🌤️ Weather   📍 Local      💸 Budget
   └─────────────┼─────────────┘
                 │  shared "facts" (raw API data)
         🗓️ Itinerary Designer ◄──┐
                 │                │ issues found (max 1 retry)
         ✅ Quality Reviewer ─────┘
                 │ approved
         🧳 Packing Assistant
                 │
            Final trip plan  ──►  ✏️ Trip Editor (chat, Step 8)
```

**Run independent agents at the same time** with `asyncio.gather`. Weather, places
and budget don't depend on each other, so there's no reason to wait:
```python
w, l, b = await asyncio.gather(
    run(WEATHER, context + "Research the weather for this trip."),
    run(LOCAL,   context + "Research the destination for this group."),
    run(BUDGET,  context + "Build the budget for this group."),
)
```

**Share raw facts, not just summaries.** We collect every tool's raw output into a
`facts` dictionary and give it to later agents. Summaries lose details (exact
coordinates, the daily budget number); raw data doesn't.

**The review loop** (this pattern is called *evaluator-optimizer*):
```python
it = await run(ITINERARY, task)
for attempt in range(max_revisions + 1):
    review = (await run(REVIEWER, review_task)).output
    if review["approved"] or attempt == max_revisions:
        break
    it = await run(ITINERARY, task + previous_itinerary + reviewer_feedback)
```

**Guardrails in code.** We don't fully trust the Planner's reading of the form.
Exact values are copied over, and `nights` is calculated in Python:
```python
brief.update(start_date=req.start_date, end_date=req.end_date, people=req.people)
brief["nights"] = (date.fromisoformat(req.end_date) - date.fromisoformat(req.start_date)).days
```

✅ **Checkpoint:** `python cli.py --demo --offline` prints every stage and saves `trip_plan.md`.

---

## 11. Step 6 – Add a Skill

**Folder:** `skills/budget-splitter/`

A skill is a folder an agent can load when needed:
```
skills/budget-splitter/
├── SKILL.md      instructions (what to do, rules, output format)
└── split.py      code the agent can call as a tool
```

**`SKILL.md`** starts with a short header. Only the `name` and `description` are
shown to the agent at first:
```markdown
---
name: budget-splitter
description: Split a group trip budget fairly into lodging, food, activities,
  transport and a safety buffer. Use whenever money comes up.
---
# Budget Splitter
## Rules
1. Never do budget arithmetic yourself. Always call `calculate_budget_split`.
2. Pick the style from the vibe: budget / balanced / treat-yourself.
...
```

**`split.py`** does the math in Python, because **LLMs are not reliable at arithmetic**:
```python
STYLES = {"balanced": (0.40, 0.28, 0.17, 0.07, 0.08), ...}  # lodging, food, fun, transport, buffer

def calculate_budget_split(budget_per_person, people, nights, style="balanced"):
    per_person = {c: budget_per_person * r for c, r in zip(CATEGORIES, STYLES[style])}
    daily_cap = (per_person["food"] + per_person["activities"]
                 + per_person["local_transport"]) / (nights + 1)
    ...
```

**How agents load skills** (`tripmate/skills.py`), called *progressive disclosure*:
1. The agent's prompt lists only skill names + one-line descriptions.
2. The agent calls `load_skill("budget-splitter")` to read the full instructions.
3. Code tools inside the skill (like `calculate_budget_split`) become available.

To add a new skill, **just add a new folder**. No other code changes.

✅ **Checkpoint:** `python skills/budget-splitter/split.py` prints a budget table.

---

## 12. Step 7 – Build the UI

**File:** `app.py` (Streamlit: a web UI written in plain Python)

```python
destination = st.text_input("Where to?", "Lisbon")
dates  = st.date_input("When?", (start, end))
people = st.number_input("Travelers", 1, 20, 4)
...
if st.button("✨ Plan our trip"):
    status = st.status("Your AI crew is on it…", expanded=True)
    plan = asyncio.run(plan_trip(req, emit=on_event))
```

**Live progress.** The orchestrator calls an `emit` function at each event (agent
started, tool called, agent finished). The UI shows these as they happen, so you
can *watch* the agents work. Great for demos:
```python
def on_event(ev):
    if ev["type"] == "tool_call":
        status.caption(f"{ev['emoji']} {ev['agent']} → {ev['tool']}")
```

The results appear in tabs: Itinerary, Weather, Budget, Local intel, Packing,
Safety, and **Agent trace** (every tool call with real inputs and outputs).

✅ **Checkpoint:** `streamlit run app.py`, pick a sample trip, click the button.

---

## 13. Step 8 – Add Conversational Revision

**File:** `tripmate/revision.py`

After the plan appears, the user can chat: *"make Day 2 more relaxed"*, *"add a
beach afternoon"*, *"one of us is vegan now"*.

**Flow (kept small on purpose):**
```
user message ─► ✏️ Trip Editor ─► ✅ Quality Reviewer ─► updated plan
                     ▲                    │
                     └── fix once ────────┘ (if issues found)
```

**Rules for the Trip Editor** (in its system prompt):
- Change **only** what was asked; keep everything else the same.
- Use only real places from the `facts`.
- Update the packing list only if needed (a beach day → add a swimsuit).
- **Big changes** (destination, dates, group size, budget) need new research, so
  it asks the user to re-plan instead of guessing.

It answers with a structured format:
```python
EDIT_TOOL fields: itinerary, packing_list, new_preferences, change_summary
```
An empty string means "this section didn't change", so we only replace what changed:
```python
if edit["itinerary"].strip():
    sections["Itinerary"] = edit["itinerary"]
plan.history.append({"request": message, "summary": edit["change_summary"]})
```

**In the UI** it's a chat box under the plan (`st.chat_input`). In the terminal:
`python cli.py --chat`.

> 💬 **Interview line:** "This adds human-in-the-loop: the user steers, the editor applies small changes, and the reviewer still checks every edit."

---

## 14. Step 9 – Test the Self-Correction Loop

**Goal:** prove the reviewer really catches problems and the designer really fixes them.

**1. Watch it happen.** Run `python cli.py --demo --offline`. You'll see:
```
▶ 4 · Quality check
  ✓ Quality Reviewer → CHANGES REQUESTED (7/10) The plan never mentions the local
    emergency number (112). Add a short safety note.
▶ 3b · Revising itinerary from reviewer feedback
  ✓ Itinerary Designer done
▶ 4 · Quality check (round 2)
  ✓ Quality Reviewer → APPROVED (9/10)
```
The first itinerary forgot the emergency number. The reviewer caught it, and the
revised plan includes it.

**2. Automated tests** (`tests/test_tripmate.py`, no API key or internet needed):
```bash
pytest -q          # 7 passed
```
```python
def test_full_pipeline_in_demo_mode():
    plan = asyncio.run(plan_trip(req, llm=DemoLLM(), offline=True))
    assert plan.stats["revisions"] == 1                        # reviewer asked for a fix
    assert "emergency" in plan.sections["Itinerary"].lower()   # ...and it was fixed
```
Other tests check the budget math adds up, skills are discovered, the MCP server
answers, chat edits change only what was asked, and big changes ask to re-plan.

**3. Break it on purpose (good practice).** Remove rule (6) about the emergency
number from the Reviewer's prompt and run with Claude. The loop should no longer
trigger for that reason. This shows the prompt rule is what drives the check.

**4. With real Claude**, check the **Agent trace** tab: the reviewer's `issues` list
should be specific ("Day 2 has a beach in the rain"), and the revised itinerary should
fix exactly those.

---

## 15. Resource Checklist

**Claude & agents**
- [ ] Claude tool use docs: [docs.claude.com](https://docs.claude.com) → "Tool use"
- [ ] Anthropic: [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) (explains the parallel and evaluator-optimizer patterns used here)
- [ ] Agent Skills: [docs.claude.com](https://docs.claude.com) → "Agent Skills"

**MCP**
- [ ] [modelcontextprotocol.io](https://modelcontextprotocol.io): concepts (tools, resources, prompts)
- [ ] [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) (FastMCP, client)
- [ ] MCP Inspector: `npx @modelcontextprotocol/inspector`

**Data APIs (all free, no key)**
- [ ] [Open-Meteo](https://open-meteo.com/en/docs): geocoding, forecast, historical weather
- [ ] [REST Countries](https://restcountries.com)
- [ ] [Frankfurter](https://frankfurter.dev): exchange rates
- [ ] [Wikipedia GeoSearch](https://www.mediawiki.org/wiki/Extension:GeoData)

**UI & testing**
- [ ] [Streamlit docs](https://docs.streamlit.io): `st.status`, `st.chat_input`
- [ ] [pytest](https://docs.pytest.org)

**Before the interview**
- [ ] `.env` has your API key; one full run with Claude works
- [ ] `pytest -q` passes
- [ ] Demo mode + offline mode tested (Wi-Fi backup)
- [ ] You can explain the agent loop (Step 4) without notes

---

## 16. Common Beginner Mistakes

Several of these happened while building this project.

1. **Letting the LLM do math.** Totals and per-person splits come out slightly wrong. → Put arithmetic in code (`split.py`).
2. **Giving every agent every tool.** The model picks wrong tools more often and costs go up. → Least privilege per agent.
3. **Missing or mismatched tool results.** Every `tool_use` must get a `tool_result` with the **same id** in the very next message, or the API returns an error.
4. **Parsing the model's free text** with string matching ("if 'approved' in reply"). → Use structured output tools.
5. **Passing only summaries between agents.** Details get lost. → Share raw tool data (`facts`).
6. **No loop limit.** An agent can keep calling tools forever. → Always set `max_turns`.
7. **Using `print()` inside a stdio MCP server.** Stdout *is* the communication channel, so stray prints break the connection. → Log to stderr.
8. **Library version surprises.** MCP's Python SDK 2.x renamed `FastMCP`, so most tutorials broke. → Pin versions (`mcp>=1.9,<2`).
9. **Hidden errors in async code.** Here, an error inside an agent was hidden behind an MCP shutdown error. → Make cleanup code re-raise the *original* error, and test each agent alone first.
10. **Asking for a weather forecast months ahead.** Forecasts only go ~16 days out. → Use last year's real weather as an estimate, and say so.
11. **Committing your API key to GitHub.** → Use `.env` and add it to `.gitignore`.
12. **A demo that needs Wi-Fi.** → Offline sample data + demo mode.
13. **Vague tool descriptions.** The model decides *when* to call a tool only from its description. → Write docstrings for the model ("Call this first…").

---

## 17. Glossary

| Term | Simple meaning |
|---|---|
| **Agent** | An LLM with a job, tools, and a loop to finish the job |
| **Agent loop** | Model → tool requests → run tools → results back → repeat until done |
| **Orchestrator** | The "manager" code that runs agents in the right order |
| **Tool use / function calling** | The model asks your code to run a function and send back the result |
| **System prompt** | The agent's job description, sent with every request |
| **Structured output** | Forcing the answer into a fixed JSON shape |
| **MCP** | Model Context Protocol: a standard way to connect AI apps to tools ("USB-C for AI") |
| **MCP server / client** | The server offers tools; the client connects and calls them |
| **Tool / Resource / Prompt** | MCP's three features: actions, read-only data, reusable prompt templates |
| **stdio** | Standard input/output: the client and server talk through the server process's input and output |
| **Skill** | A folder of instructions (+ optional code) an agent loads when needed |
| **Progressive disclosure** | Show short summaries first; load full details only when needed |
| **Parallel / fan-out** | Running independent agents at the same time |
| **Evaluator-optimizer** | One agent creates, another grades, the first improves |
| **Human-in-the-loop** | A person can review or steer the AI's work (our chat revision) |
| **Grounding** | Making the model use real fetched data instead of its memory |
| **Hallucination** | When a model confidently makes something up |
| **Guardrail** | Code that checks or corrects the model's output |
| **Least privilege** | Give each part only the access it needs |
| **Fallback** | A backup used when the main thing fails |
| **Token** | A small piece of text; API cost is counted in tokens |
