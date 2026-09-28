#!/usr/bin/env python3
"""Weather for the calendar (off until Settings > Appearance > Weather turns it on).

    weather.py now [--units metric|imperial|auto] [--max-age SECONDS] [--json]
    weather.py geocode TEXT [--lang CODE] [--json]
    weather.py place [--json]

Data from Open-Meteo (https://open-meteo.com): no account or key, free for non-commercial use,
attribution shown with the forecast. Where: the place chosen in Settings
(~/.config/arctic/location.json: {"name", "detail", "lat", "lon"}), else the coordinates tzdata
gives your time zone (zone1970.tab), as arctic-daylight uses. No IP geolocation. Coordinates are
rounded to 2 decimals (about 1 km) before they leave the computer.

`now` answers from ~/.cache/arctic/weather.json while it is younger than --max-age (default one
hour) and for the same place and units; otherwise it asks Open-Meteo (10 s timeout). Offline it
answers {"ok": false, "code": "offline", "cached": <the last reading>}.
Standard library only.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HOME = os.path.expanduser("~")
CONFIG = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config"), "arctic")
CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.join(HOME, ".cache"), "arctic", "weather.json")
PLACE_FILE = os.path.join(CONFIG, "location.json")
ZONEINFO = os.environ.get("ARCTIC_ZONEINFO") or "/usr/share/zoneinfo"
LOCALTIME = os.environ.get("ARCTIC_LOCALTIME") or "/etc/localtime"
# Tests point these at a local server; Arctic itself only ever asks Open-Meteo over https.
FORECAST = os.environ.get("ARCTIC_WEATHER_API") or "https://api.open-meteo.com/v1/forecast"
GEOCODE = os.environ.get("ARCTIC_GEOCODE_API") or "https://geocoding-api.open-meteo.com/v1/search"
USER_AGENT = "Arctic-Linux/0.3 (weather in the calendar)"
ATTRIBUTION = "Open-Meteo.com"
IMPERIAL_LOCALES = ("en_US", "en_LR", "my_MM")


class Failure(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# ---- where ---------------------------------------------------------------------------------------

def parse_coordinates(text):
    """ISO 6709 as in zone1970.tab (+DDMM+DDDMM or +DDMMSS+DDDMMSS) -> (lat, lon)."""
    m = re.fullmatch(r"([+-])(\d{2})(\d{2})(\d{2})?([+-])(\d{3})(\d{2})(\d{2})?", text)
    if not m:
        return None
    lat = int(m.group(2)) + int(m.group(3)) / 60 + int(m.group(4) or 0) / 3600
    lon = int(m.group(6)) + int(m.group(7)) / 60 + int(m.group(8) or 0) / 3600
    return (lat if m.group(1) == "+" else -lat, lon if m.group(5) == "+" else -lon)


def time_zone():
    zone = os.environ.get("ARCTIC_TIMEZONE") or ""
    if not zone:
        target = os.path.realpath(LOCALTIME)
        marker = os.sep + "zoneinfo" + os.sep
        if marker in target:
            zone = target.split(marker, 1)[1]
    return zone


def valid_place(data):
    try:
        lat, lon = float(data["lat"]), float(data["lon"])
    except (KeyError, TypeError, ValueError):
        return False
    name = data.get("name")
    return -90 <= lat <= 90 and -180 <= lon <= 180 and isinstance(name, str) and 0 < len(name) <= 80


def place():
    """{"name", "detail", "lat", "lon", "source": "chosen"|"zone"} or None."""
    try:
        with open(PLACE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and valid_place(data):
            return dict(name=data["name"], detail=str(data.get("detail") or "")[:120],
                        lat=float(data["lat"]), lon=float(data["lon"]), source="chosen")
    except (OSError, ValueError):
        pass
    zone = time_zone()
    if not zone:
        return None
    try:
        with open(os.path.join(ZONEINFO, "zone1970.tab"), encoding="utf-8") as f:
            for line in f:
                cols = line.rstrip("\n").split("\t")
                if len(cols) >= 3 and not line.startswith("#") and cols[2] == zone:
                    coords = parse_coordinates(cols[1])
                    if coords:
                        return dict(name=zone.rsplit("/", 1)[-1].replace("_", " "), detail=zone,
                                    lat=coords[0], lon=coords[1], source="zone")
    except OSError:
        pass
    return None


# ---- asking Open-Meteo ---------------------------------------------------------------------------

def auto_units(env=None):
    env = os.environ if env is None else env
    locale = env.get("LC_ALL") or env.get("LC_MEASUREMENT") or env.get("LANG") or ""
    return "imperial" if locale.split(".")[0] in IMPERIAL_LOCALES else "metric"


def forecast_url(lat, lon, units):
    query = [
        ("latitude", "{:.2f}".format(lat)), ("longitude", "{:.2f}".format(lon)),
        ("current", "temperature_2m,apparent_temperature,weather_code,is_day,wind_speed_10m"),
        ("daily", "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset"),
        ("timezone", "auto"), ("forecast_days", "5"),
        ("temperature_unit", "fahrenheit" if units == "imperial" else "celsius"),
        ("wind_speed_unit", "mph" if units == "imperial" else "kmh"),
    ]
    return FORECAST + "?" + urllib.parse.urlencode(query, safe=",")


def fetch_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read(1_000_000)
    except urllib.error.HTTPError as e:
        raise Failure("service", "Open-Meteo answered {}.".format(e.code)) from None
    except (urllib.error.URLError, OSError, TimeoutError):
        raise Failure("offline", "Can't reach Open-Meteo.") from None
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise Failure("service", "Open-Meteo sent something that isn't a forecast.") from None
    if not isinstance(data, dict) or data.get("error"):
        raise Failure("service", str((data or {}).get("reason") or "Open-Meteo couldn't give a forecast."))
    return data


def _num(value, digits=1):
    return round(float(value), digits) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _hhmm(value):
    m = re.search(r"T(\d{2}:\d{2})", str(value or ""))
    return m.group(1) if m else ""


def reading(data, where, units, now):
    """The forecast JSON in the shape the shell reads."""
    cur = data.get("current") or {}
    daily = data.get("daily") or {}
    days = []
    dates = daily.get("time") or []
    for i, day in enumerate(dates[:5]):
        def col(key, i=i):
            values = daily.get(key) or []
            return values[i] if i < len(values) else None
        days.append(dict(date=str(day), code=int(col("weather_code") or 0), max=_num(col("temperature_2m_max"), 0),
                         min=_num(col("temperature_2m_min"), 0), rain=_num(col("precipitation_probability_max"), 0),
                         sunrise=_hhmm(col("sunrise")), sunset=_hhmm(col("sunset"))))
    if not isinstance(cur.get("weather_code"), int) or _num(cur.get("temperature_2m")) is None:
        raise Failure("service", "Open-Meteo sent a forecast without the current weather.")
    return dict(ok=True, place=where["name"], source=where["source"], units=units, fetched_at=int(now),
                attribution=ATTRIBUTION,
                current=dict(temp=_num(cur.get("temperature_2m")), feels=_num(cur.get("apparent_temperature")),
                             code=int(cur["weather_code"]), is_day=bool(cur.get("is_day", 1)),
                             wind=_num(cur.get("wind_speed_10m"), 0)),
                daily=days)


def read_cache():
    try:
        with open(CACHE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) and isinstance(data.get("reading"), dict) else None
    except (OSError, ValueError):
        return None


def write_cache(key, value):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    tmp = "{}.tmp-{}".format(CACHE, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"key": key, "reading": value}, f)
    os.replace(tmp, CACHE)


def now_cmd(units, max_age, clock=time.time):
    where = place()
    if where is None:
        raise Failure("no_location", "Arctic doesn't know where you are: choose a place in Settings > Appearance.")
    units = auto_units() if units == "auto" else units
    key = "{:.2f},{:.2f},{}".format(where["lat"], where["lon"], units)
    cached = read_cache()
    now = clock()
    if cached and cached.get("key") == key and 0 <= now - cached["reading"].get("fetched_at", 0) < max_age:
        return dict(cached["reading"], cached=True)
    try:
        result = reading(fetch_json(forecast_url(where["lat"], where["lon"], units)), where, units, now)
    except Failure as e:
        out = dict(ok=False, code=e.code, error=str(e))
        if cached and cached.get("key") == key:
            out["cached"] = cached["reading"]
        return out
    write_cache(key, result)
    return result


def geocode_cmd(text, lang):
    text = text.strip()
    if not 2 <= len(text) <= 80:
        raise Failure("usage", "Type at least two letters of a place.")
    lang = lang if re.fullmatch(r"[a-z]{2}", lang or "") else "en"
    url = GEOCODE + "?" + urllib.parse.urlencode(dict(name=text, count=6, language=lang, format="json"))
    places = []
    for r in fetch_json(url).get("results") or []:
        if not isinstance(r, dict) or not valid_place(dict(name=r.get("name"), lat=r.get("latitude"), lon=r.get("longitude"))):
            continue
        detail = ", ".join(str(p) for p in (r.get("admin1"), r.get("country")) if p)
        places.append(dict(name=str(r["name"])[:80], detail=detail[:120],
                           lat=round(float(r["latitude"]), 4), lon=round(float(r["longitude"]), 4)))
    return dict(ok=True, places=places)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="weather.py", description="Weather for the calendar (Open-Meteo).")
    sub = parser.add_subparsers(dest="command")
    n = sub.add_parser("now")
    n.add_argument("--units", choices=("metric", "imperial", "auto"), default="auto")
    n.add_argument("--max-age", type=int, default=3600)
    n.add_argument("--json", action="store_true")
    g = sub.add_parser("geocode")
    g.add_argument("text")
    g.add_argument("--lang", default=(os.environ.get("LANG") or "en")[:2])
    g.add_argument("--json", action="store_true")
    p = sub.add_parser("place")
    p.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "now":
            out = now_cmd(args.units, max(0, args.max_age))
        elif args.command == "geocode":
            out = geocode_cmd(args.text, args.lang)
        elif args.command == "place":
            where = place()
            out = dict(where, ok=True) if where else dict(ok=False, code="no_location", error="No place is known.")
        else:
            parser.print_help()
            return 2
    except Failure as e:
        out = dict(ok=False, code=e.code, error=str(e))
    if getattr(args, "json", False):
        print(json.dumps(out))
    elif out.get("ok") and args.command == "now":
        c = out["current"]
        print("{:.0f}° in {} (code {})".format(c["temp"], out["place"], c["code"]))
    else:
        print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
