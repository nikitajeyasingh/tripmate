"""Offline sample data so the MCP server still answers without internet.
Every fallback response is tagged source="offline-sample" so agents (and you)
can tell it apart from live data."""
from __future__ import annotations

import hashlib
from datetime import date, timedelta

SRC = "offline-sample"

CITIES = {
    "lisbon": dict(city="Lisbon", country="Portugal", country_code="PT", latitude=38.7167, longitude=-9.1333, timezone="Europe/Lisbon", population=517802,
                   places=["Belém Tower", "Jerónimos Monastery", "LX Factory", "Time Out Market", "Alfama", "São Jorge Castle", "Miradouro da Senhora do Monte",
                           "Bairro Alto", "Praça do Comércio", "MAAT museum", "Pastéis de Belém", "Tram 28", "Príncipe Real", "Feira da Ladra"]),
    "nashville": dict(city="Nashville", country="United States", country_code="US", latitude=36.1659, longitude=-86.7844, timezone="America/Chicago", population=715884,
                      places=["Broadway (Honky Tonk Highway)", "Ryman Auditorium", "Country Music Hall of Fame", "The Gulch", "12 South", "Centennial Park & Parthenon",
                              "Frist Art Museum", "Grand Ole Opry", "East Nashville", "Pedestrian Bridge", "Assembly Food Hall", "Printers Alley"]),
    "charleston": dict(city="Charleston", country="United States", country_code="US", latitude=32.7765, longitude=-79.9311, timezone="America/New_York", population=150227,
                       places=["Rainbow Row", "The Battery", "Charleston City Market", "King Street", "Waterfront Park & Pineapple Fountain", "Magnolia Plantation",
                               "Folly Beach", "Angel Oak Tree", "Gibbes Museum of Art", "Fort Sumter", "Shem Creek"]),
    "new orleans": dict(city="New Orleans", country="United States", country_code="US", latitude=29.9547, longitude=-90.0751, timezone="America/Chicago", population=383997,
                        places=["French Quarter", "Jackson Square", "Café Du Monde", "Frenchmen Street", "Garden District", "Magazine Street", "City Park",
                                "Preservation Hall", "St. Charles Streetcar", "Bywater", "National WWII Museum"]),
    "paris": dict(city="Paris", country="France", country_code="FR", latitude=48.8534, longitude=2.3488, timezone="Europe/Paris", population=2138551,
                  places=["Eiffel Tower", "Louvre", "Le Marais", "Montmartre & Sacré-Cœur", "Musée d'Orsay", "Jardin du Luxembourg", "Canal Saint-Martin",
                          "Shakespeare and Company", "Seine river cruise", "Galeries Lafayette rooftop", "Rue Cler market"]),
    "tulum": dict(city="Tulum", country="Mexico", country_code="MX", latitude=20.2114, longitude=-87.4654, timezone="America/Cancun", population=33374,
                  places=["Tulum Archaeological Site", "Gran Cenote", "Playa Paraíso", "Sian Ka'an Biosphere", "Cenote Calavera", "Tulum Pueblo", "Laguna Kaan Luum",
                          "Azulik art space", "Hotel Zone beach clubs", "Coba ruins"]),
}

COUNTRIES = {
    "PT": dict(country="Portugal", capital="Lisbon", languages=["Portuguese"], currency_code="EUR", currency_name="Euro", currency_symbol="€", drives_on="right"),
    "US": dict(country="United States", capital="Washington, D.C.", languages=["English"], currency_code="USD", currency_name="United States dollar", currency_symbol="$", drives_on="right"),
    "FR": dict(country="France", capital="Paris", languages=["French"], currency_code="EUR", currency_name="Euro", currency_symbol="€", drives_on="right"),
    "MX": dict(country="Mexico", capital="Mexico City", languages=["Spanish"], currency_code="MXN", currency_name="Mexican peso", currency_symbol="$", drives_on="right"),
    "GB": dict(country="United Kingdom", capital="London", languages=["English"], currency_code="GBP", currency_name="British pound", currency_symbol="£", drives_on="left"),
}

EMERGENCY = {"US": "911", "CA": "911", "MX": "911", "GB": "999", "AU": "000", "IN": "112", "JP": "110 (police) / 119 (ambulance)"}

USD_RATES = {"USD": 1.0, "EUR": 0.92, "GBP": 0.79, "MXN": 18.4, "CAD": 1.37, "JPY": 149.0, "INR": 83.5, "AUD": 1.52}

WMO = {0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
       61: "Light rain", 63: "Rain", 65: "Heavy rain", 71: "Light snow", 73: "Snow", 75: "Heavy snow", 80: "Showers", 81: "Showers", 82: "Heavy showers",
       95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm"}

SAFETY_CHECKLIST = """Travel safety checklist
- Share your itinerary and accommodation address with someone at home.
- Save the local emergency number and your embassy contact.
- Keep a photo of your passport/ID in cloud storage.
- Use licensed taxis or rideshare apps; check the plate before getting in.
- Agree on a group meeting point and a 'check-in' text routine at night.
- Keep one card and some cash separate from your main wallet.
"""


def _city(name_or_lat):
    if isinstance(name_or_lat, str):
        return CITIES.get(name_or_lat.strip().lower().split(",")[0])
    return min(CITIES.values(), key=lambda c: abs(c["latitude"] - name_or_lat))


def geocode(city: str) -> dict:
    c = _city(city)
    if c:
        return {k: v for k, v in c.items() if k != "places"} | {"source": SRC}
    return {"city": city.title(), "country": "Unknown", "country_code": "US", "latitude": 40.0, "longitude": -75.0,
            "timezone": "UTC", "source": SRC, "note": "City not in offline sample set; coordinates are placeholders."}


def weather(lat: float, start: str, end: str) -> dict:
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    days, d = [], s
    season = {12: 10, 1: 12, 2: 10, 11: 5, 3: 5}.get(s.month, 0) if lat > 0 else 0
    base = 88 - abs(lat) * 0.5 - season
    conds = ["Clear", "Partly cloudy", "Mostly clear", "Showers", "Overcast"]
    while d <= e:
        h = int(hashlib.md5(f"{lat}{d}".encode()).hexdigest(), 16)
        c = conds[h % len(conds)]
        hi = round(base + (h % 9) - 4, 1)
        days.append({"date": d.isoformat(), "high_f": hi, "low_f": round(hi - 13, 1),
                     "rain_mm": 4.2 if c == "Showers" else 0.0, "conditions": c})
        d += timedelta(days=1)
    return {"type": "sample estimate", "days": days, "source": SRC}


def country(code: str) -> dict:
    c = COUNTRIES.get(code.upper(), COUNTRIES["US"])
    return c | {"emergency_number": EMERGENCY.get(code.upper(), "112"), "source": SRC}


def fx(amount: float, frm: str, to: str) -> dict:
    rate = USD_RATES.get(to.upper(), 1) / USD_RATES.get(frm.upper(), 1)
    return {"amount": amount, "from": frm.upper(), "to": to.upper(), "rate": round(rate, 4),
            "converted": round(amount * rate, 2), "source": SRC}


def places(lat: float) -> dict:
    c = _city(lat)
    return {"places": [{"name": p, "distance_m": 400 + i * 350} for i, p in enumerate(c["places"])], "source": SRC}


# Countries that drive on the left (the open countries dataset doesn't include driving side).
DRIVES_LEFT = {
    "GB", "IE", "IM", "JE", "GG", "MT", "CY", "AU", "NZ", "FJ", "PG", "WS", "TO", "SB",
    "JP", "IN", "PK", "BD", "LK", "NP", "BT", "MV", "TH", "MY", "SG", "ID", "BN", "TL",
    "HK", "MO", "ZA", "NA", "BW", "ZW", "ZM", "MZ", "MW", "TZ", "KE", "UG", "LS", "SZ",
    "MU", "SC", "JM", "BS", "BB", "TT", "AG", "DM", "GD", "KN", "LC", "VC", "GY", "SR",
    "KY", "VG", "VI", "BM", "AI", "MS", "TC", "FK", "SH",
}
