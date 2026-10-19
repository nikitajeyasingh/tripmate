"""
TripMate Travel MCP Server
==========================
A Model Context Protocol (MCP) server that exposes real-world travel data as
tools any MCP-compatible agent (Claude Desktop, Claude Code, our orchestrator)
can call.

All upstream APIs are free and need no API key:
  * Open-Meteo        - geocoding + weather forecast + historical climate
  * Frankfurter (ECB) - currency exchange rates
  * REST Countries    - languages, currency, driving side
  * Wikipedia         - notable places near a coordinate (geosearch)

If the network is unavailable (or TRIPMATE_OFFLINE=1) every tool falls back to
bundled sample data and says so in its `source` field, so demos never break.

Run standalone:   python mcp_server/travel_server.py
Inspect it:       npx @modelcontextprotocol/inspector python mcp_server/travel_server.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta

import httpx
from mcp.server.fastmcp import FastMCP

sys.path.insert(0, os.path.dirname(__file__))
import fixtures  # noqa: E402

mcp = FastMCP("tripmate-travel", log_level="WARNING")

OFFLINE = os.getenv("TRIPMATE_OFFLINE") == "1"
HEADERS = {"User-Agent": "TripMate/1.0 (interview demo project)"}
TIMEOUT = 10.0


async def _get(url: str, params: dict) -> dict:
    if OFFLINE:
        raise ConnectionError("offline mode")
    # follow_redirects: APIs move (Frankfurter moved .app -> .dev), and httpx doesn't follow by default
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()


def _out(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)


# REST Countries deprecated its keyless v3.1 API (v5 needs a key). Its underlying open
# dataset has the same fields, so we download it once per server run and cache it.
COUNTRIES_URL = "https://raw.githubusercontent.com/mledoze/countries/master/countries.json"
_countries_cache: list | None = None


async def _countries() -> list:
    global _countries_cache
    if _countries_cache is None:
        _countries_cache = await _get(COUNTRIES_URL, {})
    return _countries_cache


def _fallback(tool: str, err: Exception, data: dict) -> str:
    """Use sample data, but never silently: log the reason to stderr (stdout is the
    MCP channel, so print() there would break the protocol) and tell the agent why."""
    if not OFFLINE:
        print(f"[tripmate-travel] {tool} fell back to sample data: {err!r}", file=sys.stderr)
    return _out({**data, "fallback_reason": "offline mode" if OFFLINE else repr(err)[:200]})


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
@mcp.tool()
async def geocode_city(city: str) -> str:
    """Find a city's coordinates, country and timezone. Call this first; other
    tools need the latitude/longitude it returns."""
    try:
        data = await _get(
            "https://geocoding-api.open-meteo.com/v1/search",
            {"name": city, "count": 1, "language": "en", "format": "json"},
        )
        hit = (data.get("results") or [None])[0]
        if not hit:
            return _out({"error": f"No city found named '{city}'"})
        return _out({
            "city": hit["name"],
            "country": hit.get("country"),
            "country_code": hit.get("country_code"),
            "latitude": hit["latitude"],
            "longitude": hit["longitude"],
            "timezone": hit.get("timezone"),
            "population": hit.get("population"),
            "source": "open-meteo",
        })
    except Exception as e:
        return _fallback("geocode_city", e, fixtures.geocode(city))


@mcp.tool()
async def get_weather(latitude: float, longitude: float, start_date: str, end_date: str) -> str:
    """Daily weather for a date range (YYYY-MM-DD). Uses the live forecast when
    the trip is within 16 days, otherwise last year's actual weather for the
    same dates as a 'typical weather' estimate."""
    try:
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
        daily = "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,weather_code"
        if (start - date.today()).days <= 14:
            data = await _get("https://api.open-meteo.com/v1/forecast", {
                "latitude": latitude, "longitude": longitude, "daily": daily,
                "start_date": start_date, "end_date": end_date,
                "timezone": "auto", "temperature_unit": "fahrenheit",
            })
            kind = "forecast"
        else:
            ly_start, ly_end = start - timedelta(days=365), end - timedelta(days=365)
            data = await _get("https://archive-api.open-meteo.com/v1/archive", {
                "latitude": latitude, "longitude": longitude,
                "daily": daily.replace(",precipitation_probability_max", ""),
                "start_date": ly_start.isoformat(), "end_date": ly_end.isoformat(),
                "timezone": "auto", "temperature_unit": "fahrenheit",
            })
            kind = "typical (same dates last year)"
        d = data["daily"]
        days = []
        for i in range(len(d["time"])):
            days.append({
                "date": (start + timedelta(days=i)).isoformat(),
                "high_f": d["temperature_2m_max"][i],
                "low_f": d["temperature_2m_min"][i],
                "rain_mm": d["precipitation_sum"][i],
                "conditions": fixtures.WMO.get(d["weather_code"][i], "Mixed"),
            })
        return _out({"type": kind, "days": days, "source": "open-meteo"})
    except Exception as e:
        return _fallback("get_weather", e, fixtures.weather(latitude, start_date, end_date))


@mcp.tool()
async def get_country_info(country_code: str) -> str:
    """Practical country facts from a 2-letter ISO code: languages, currency,
    capital, driving side and emergency number."""
    try:
        data = next((c for c in await _countries() if c.get("cca2") == country_code.upper()), None)
        if data is None:
            raise ValueError(f"unknown country code {country_code!r}")
        cur_code, cur = next(iter(data.get("currencies", {}).items()), ("?", {}))
        return _out({
            "country": data["name"]["common"],
            "capital": (data.get("capital") or [None])[0],
            "languages": list(data.get("languages", {}).values()),
            "currency_code": cur_code,
            "currency_name": cur.get("name"),
            "currency_symbol": cur.get("symbol"),
            "drives_on": "left" if country_code.upper() in fixtures.DRIVES_LEFT else "right",
            "emergency_number": fixtures.EMERGENCY.get(country_code.upper(), "112"),
            "source": "mledoze/countries (REST Countries dataset)",
        })
    except Exception as e:
        return _fallback("get_country_info", e, fixtures.country(country_code))


@mcp.tool()
async def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
    """Convert money between currencies using today's European Central Bank rate."""
    if from_currency.upper() == to_currency.upper():
        return _out({"amount": amount, "converted": amount, "rate": 1.0, "source": "identity"})
    try:
        data = await _get("https://api.frankfurter.dev/v1/latest",
                          {"base": from_currency.upper(), "symbols": to_currency.upper()})
        rate = data["rates"][to_currency.upper()]
        return _out({
            "amount": amount, "from": from_currency.upper(), "to": to_currency.upper(),
            "rate": rate, "converted": round(amount * rate, 2), "as_of": data.get("date"),
            "source": "frankfurter/ECB",
        })
    except Exception as e:
        return _fallback("convert_currency", e, fixtures.fx(amount, from_currency, to_currency))


@mcp.tool()
async def find_places_nearby(latitude: float, longitude: float, radius_m: int = 5000, limit: int = 15) -> str:
    """Notable landmarks, museums, parks and neighborhoods near a point, from
    Wikipedia. Use to ground itinerary suggestions in real places."""
    try:
        data = await _get("https://en.wikipedia.org/w/api.php", {
            "action": "query", "list": "geosearch", "format": "json",
            "gscoord": f"{latitude}|{longitude}",
            "gsradius": min(radius_m, 10000), "gslimit": min(limit, 30),
        })
        places = [{"name": p["title"], "distance_m": round(p["dist"])}
                  for p in data["query"]["geosearch"]]
        return _out({"places": places, "source": "wikipedia"})
    except Exception as e:
        return _fallback("find_places_nearby", e, fixtures.places(latitude))


# --------------------------------------------------------------------------- #
# Resource + prompt (shows the other two MCP primitives besides tools)
# --------------------------------------------------------------------------- #
@mcp.resource("tripmate://safety-checklist")
def safety_checklist() -> str:
    """Solo & group travel safety checklist."""
    return fixtures.SAFETY_CHECKLIST


@mcp.prompt()
def plan_trip(destination: str, days: int = 3) -> str:
    """Reusable prompt template for planning a trip with these tools."""
    return (f"Plan a {days}-day trip to {destination}. Geocode it, check the weather, "
            "look up country info and real nearby places, then propose a day-by-day plan.")


if __name__ == "__main__":
    mcp.run()  # stdio transport
