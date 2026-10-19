# TripMate: interview guide

Your cheat sheet for presenting this project. Read it twice, run the demo three
times before the interview, and you'll be comfortable.

---

## 1. The 30-second pitch

> "Planning a group trip with friends usually means a messy group chat, ten browser
> tabs and one person doing all the work. I built **TripMate**, a team of eight AI
> agents that plans the trip for you. You enter the destination, dates, group size,
> budget and the vibe, and the agents check the real weather, find real places,
> split the budget fairly, write a day-by-day itinerary, review their own work,
> and make a shared packing list. Then you can
> chat with it to change anything.
>
> Under the hood it uses Claude with tool use, a custom MCP server that wraps four
> live public APIs, Agent Skills with progressive disclosure, and an orchestrator
> that runs agents in parallel with a self-review loop."

## 2. Why this use case (if asked)

- **Everyone gets it instantly.** No domain explanation needed, so the conversation goes straight to the engineering.
- **It needs real orchestration.** Weather, places and budget are independent (parallel), the itinerary depends on all three (sequential), and quality needs checking (loop). It's a natural fit for multiple agents, not a forced one.
- **It needs real data.** An itinerary is only useful if the weather and places are real, which is exactly where LLMs hallucinate without tools.

---

## 3. Demo script (about 6 minutes)

**Before the call:** run `streamlit run app.py`, set your API key in `.env`, do one warm-up run. Have VS Code open on `orchestrator.py`.

1. **Show the app (30s).** Point at the 8 agent chips. Pick "🎂 Birthday in Lisbon". Read the notes aloud: *"brunch, photo spots, one vegetarian, no clubbing."*
2. **Click "Plan our trip" and narrate the live trace (60s).**
   - "The **Planner** turns my messy notes into a structured brief: it extracted *vegetarian* as a preference and *no clubbing* as something to avoid."
   - "Now **three agents run in parallel**, each with only the tools it needs. You can see them calling the MCP server: geocode, weather, country info, real places from Wikipedia."
   - "The **Budget Planner** loads its skill first, then calls a Python function for the math, because LLMs shouldn't do arithmetic."
   - "The **Reviewer** checks the itinerary. If it finds a problem, it sends specific feedback and the designer revises."
3. **Show the result (60s).** Itinerary tab (outdoor plans on sunny days), Budget tab (table + daily cap in euros), Packing tab (shared items). Point at the metrics row.
4. **Chat to change it (45s).** Type *"make Day 2 more relaxed"* in the chat box. "The Trip Editor changes only that day, and the Reviewer checks the edit again. That's human-in-the-loop." Then try *"change the budget to $500"*: "Big changes need fresh research, so it asks me to re-plan instead of guessing."
5. **Open the Agent trace tab (30s).** "Every tool call with its real input and output, so it's debuggable."
6. **Show code (90s).** Open in this order:
   - `orchestrator.py`: the diagram at the top, then `asyncio.gather` and the review loop.
   - `agents.py`: the loop. "No framework. About 100 lines, so I understand every step."
   - `travel_server.py`: "`@mcp.tool()` and the docstring becomes the tool description Claude reads."
   - `skills/budget-splitter/`: SKILL.md + split.py.
7. **Close (15s).** "The same MCP server also plugs straight into Claude Desktop, so the tools are reusable beyond this app."

**If Wi-Fi or the API fails:** toggle *Demo mode* and *Offline sample data* in the sidebar. Say: "I built a fallback so the system degrades gracefully. The agents, MCP server and skills are all still real; only the text generation is templated."

---

## 4. Explaining each rubric item in plain words

**Multi-agent orchestration.** Seven agents, each with a narrow job and its own system prompt. Patterns used:
- *Fan-out / fan-in*: three research agents in parallel with `asyncio.gather`.
- *Pipeline*: research → itinerary → packing.
- *Evaluator-optimizer*: the reviewer grades the itinerary with a JSON schema (`approved`, `score`, `issues`); if not approved, the designer revises once.
- *Shared blackboard*: raw tool outputs are passed forward, so later agents work from facts, not from each other's summaries.

**MCP server.** MCP is an open standard for connecting AI apps to tools and data, like USB-C for AI. My server exposes all three MCP primitives:
- **Tools** (5): actions the model can call.
- **Resource** (1): read-only data the app can fetch (safety checklist).
- **Prompt** (1): a reusable prompt template.
It runs over **stdio**: the client starts it as a subprocess and they talk JSON-RPC.

**MCP client.** `mcp_client.py` starts the server, does the handshake (`initialize`), discovers tools with `list_tools`, and converts each MCP schema into Claude's tool format. Agents never hard-code tools; they're discovered at runtime.

**APIs.** Open-Meteo (geocoding, 16-day forecast, and last year's weather for trips further out), REST Countries, Frankfurter (European Central Bank exchange rates), Wikipedia geosearch. All free with no keys, so anyone can run it.

**Skills.** Following Anthropic's Agent Skills idea: a skill is a folder with a `SKILL.md` (instructions) and optionally code. Agents only see the skill's name and one-line description at first; they call `load_skill` to read the full instructions when needed. That's **progressive disclosure**: it keeps prompts small, and you add capabilities by adding a folder.

---

## 5. Likely questions and good answers

**"Why multiple agents instead of one big prompt?"**
Focus and reliability. Each agent has a short prompt and 2-3 tools, so it picks the right tool more often. Independent work runs in parallel, so it's faster. And the reviewer gives a second opinion, which a single prompt can't do for itself. The trade-off is more API calls and cost, so I'd only split where the work is genuinely separate.

**"How do you stop hallucinations?"**
Three layers: (1) itinerary places must come from the Wikipedia tool results, enforced in the skill instructions; (2) the reviewer checks every place name against that real list; (3) numbers come from code, not the model.

**"Where does the data come from? What's real?"**
Weather, country facts, exchange rates and place names are real, from free public APIs. Budget numbers are real arithmetic on my own estimated percentages, not real prices. The itinerary and packing list are generated by Claude from that real data. Show the table in the README ("Where the data comes from"). If an API fails, tools fall back to sample data and label it.

**"Why Wikipedia for places, not Google Places or Geoapify?"**
No API key needed, so anyone can run it. The trade-off is no restaurants or ratings, so I told the agents never to invent restaurant names. Adding Geoapify would be one new MCP tool.

**"Why not LangChain / CrewAI?"**
I wanted to show I understand the underlying loop: send messages, get `tool_use` blocks, run tools, send `tool_result`s back. It's about 100 lines. In a team I'd happily use the Claude Agent SDK or a framework, but I'd know what it does underneath.

**"How do you get structured output?"**
I give the agent a tool like `submit_review` with a JSON schema and, when it has no other tools, force it with `tool_choice`. The orchestrator then branches on `approved: false` instead of parsing text.

**"What happens if a tool or API fails?"**
Tool errors are returned to the model as `is_error` tool results, so it can retry or work around them. Each MCP tool also falls back to sample data and marks `source: offline-sample`, so the UI shows the data wasn't live.

**"How would you evaluate it?"**
Build a set of ~30 varied trip requests. Score automatically: Are all places in the tool results? Does the plan fit the daily cap? Is every must-do and avoid honored? Plus an LLM-as-judge for tone. Run it on every prompt change.

**"How would you make it production-ready?"**
Prompt caching for cost, streaming for UX, evals in CI, tracing per agent, rate-limit retries, a remote MCP server over HTTP with auth, and real booking APIs for flights and hotels.

**"What was hardest?"**
Honest answer you can give: getting agents to hand off information cleanly. Passing only prose between agents lost details (like exact coordinates or the daily cap), so I added the shared "facts" blackboard with raw tool outputs.

**"What's the cost per trip?"**
Shown in the metrics row (tokens in/out). Roughly 9-10 agent runs and ~20 API calls. Prompt caching and using a smaller model (Haiku) for the simple agents (packing, weather) would cut it a lot.

---

## 6. Words to know

| Term | Simple meaning |
|---|---|
| Tool use / function calling | Model asks to run a function; your code runs it and sends back the result |
| Agent loop | Repeat: model → tool calls → results → model, until it gives a final answer |
| MCP | Open standard so any AI app can use any tool server |
| stdio transport | Client and server talk through the server process's input/output |
| Progressive disclosure | Show summaries first, load details only when needed |
| Evaluator-optimizer | One agent creates, another grades, the first improves |
| Grounding | Making the model use real data instead of memory |
| Human-in-the-loop | A person can steer or check the AI's work (our chat revision) |

For the full glossary and a step-by-step explanation of every part, see **BUILD_GUIDE.md**.

Good luck! 🍀
