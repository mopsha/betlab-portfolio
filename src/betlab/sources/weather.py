"""Kickoff weather for NFL games: Open-Meteo's free forecast API (no key) and the venue table.

- `venue(stadium_id, stadium)`: the venue from `config/stadiums.yaml` (by name first:
  nflverse sometimes files an international game under the home team's usual id).
- `forecast(lat, lon, kickoff)`: temperature, wind, gusts and chance of rain or snow
  over the three hours from kickoff, up to 16 days ahead. None if the game is further
  out or the API fails; the preview then says the forecast isn't in yet.

Past games' weather comes from nflverse's schedule (`temp`, `wind`, `roof`) and the
play-by-play `weather` text; that's what the effects in `models/game_nfl.py` were fit on.
"""

from __future__ import annotations

from functools import lru_cache

import pandas as pd
import requests
import yaml

from betlab import config

URL = "https://api.open-meteo.com/v1/forecast"
HOURLY = "temperature_2m,precipitation_probability,precipitation,wind_speed_10m,wind_gusts_10m"

# One kept-alive connection for every forecast in a run, a short connect timeout, and a breaker:
# on the Railway worker (Oct 6) each call stalled to its 20 s timeout, and ~75 games (NFL + college)
# ran `betlab preview` into the worker's 25-minute limit. The forecast is a bonus, so after
# MAX_FAILS failures in a row the rest of the run goes without it.
TIMEOUT = (5, 15)       # connect, read (seconds)
MAX_FAILS = 2
_session = requests.Session()
_fails = 0


@lru_cache(maxsize=1)
def venues() -> dict:
    return yaml.safe_load((config.ROOT / "config" / "stadiums.yaml").read_text(encoding="utf-8"))


def venue(stadium_id: str | None, stadium: str | None = None) -> dict | None:
    """The venue for a game: matched by stadium name, else by nflverse's stadium_id."""
    v = venues()
    by_name = {x["name"].lower(): {**x, "id": k} for k, x in v.items()}
    if stadium and stadium.lower() in by_name:
        return by_name[stadium.lower()]
    return {**v[stadium_id], "id": stadium_id} if stadium_id in v else None


def forecast(lat: float, lon: float, kickoff: pd.Timestamp, session=None) -> dict | None:
    """Kickoff-window forecast: temp_f and wind_mph (averages), gust_mph (max), precip_prob
    (max, 0-1) and precip_in (total) over the three hours from kickoff."""
    ko = pd.Timestamp(kickoff).tz_convert("UTC")
    hours_out = (ko - pd.Timestamp.now(tz="UTC")).total_seconds() / 3600
    if hours_out > 15.5 * 24 or hours_out < -4:
        return None
    global _fails
    if _fails >= MAX_FAILS:
        return None
    try:
        r = (session or _session).get(URL, params={
            "latitude": lat, "longitude": lon, "hourly": HOURLY, "wind_speed_unit": "mph",
            "temperature_unit": "fahrenheit", "precipitation_unit": "inch", "timezone": "GMT",
            "forecast_days": 16}, timeout=TIMEOUT)
        r.raise_for_status()
        h = pd.DataFrame(r.json()["hourly"])
    except Exception:
        _fails += 1
        if _fails == MAX_FAILS:
            print(f"weather: Open-Meteo failed {MAX_FAILS} times in a row; no forecasts for the rest of this run")
        return None
    _fails = 0
    h["time"] = pd.to_datetime(h["time"], utc=True)
    w = h[(h["time"] >= ko.floor("h")) & (h["time"] < ko.floor("h") + pd.Timedelta(hours=3))]
    if w.empty:
        return None
    return {"temp_f": round(float(w["temperature_2m"].mean()), 0),
            "wind_mph": round(float(w["wind_speed_10m"].mean()), 0),
            "gust_mph": round(float(w["wind_gusts_10m"].max()), 0),
            "precip_prob": round(float(w["precipitation_probability"].max()) / 100, 2),
            "precip_in": round(float(w["precipitation"].sum()), 2)}
