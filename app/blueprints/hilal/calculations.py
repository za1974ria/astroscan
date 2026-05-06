"""Hilal Observatory — pure scientific calculations.

Crescent visibility (Yallop 1997 + Odeh 2006), Hijri calendar conversion,
Islamic prayer times (5 methods in parallel), Ramadan status, city search.

Empreinte: rigueur scientifique. On calcule, on ne tranche pas.

Dependencies: skyfield (NASA JPL DE421), hijridate, adhan, timezonefinder, pytz.
"""

import logging
import math
import time as _t
from datetime import date, datetime, timedelta, timezone as _tz

log = logging.getLogger(__name__)

EPHEMERIS_PATH = "/root/astro_scan/de421.bsp"

_TS = None
_EPH = None
_TF = None


def _ts():
    global _TS
    if _TS is None:
        from skyfield.api import load
        _TS = load.timescale()
    return _TS


def _eph():
    global _EPH
    if _EPH is None:
        from skyfield.api import load_file
        _EPH = load_file(EPHEMERIS_PATH)
    return _EPH


def _tf():
    global _TF
    if _TF is None:
        from timezonefinder import TimezoneFinder
        _TF = TimezoneFinder()
    return _TF


PHASE_FR = [
    "Nouvelle Lune", "Premier Croissant", "Premier Quartier", "Gibbeuse Croissante",
    "Pleine Lune", "Gibbeuse Décroissante", "Dernier Quartier", "Dernier Croissant",
]
PHASE_AR = [
    "محاق", "هلال متزايد", "تربيع أول", "أحدب متزايد",
    "بدر", "أحدب متناقص", "تربيع آخر", "هلال متناقص",
]
PHASE_ICON = ["🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘"]

HIJRI_FR = [
    "", "Mouharram", "Safar", "Rabi' al-Awwal", "Rabi' al-Thani",
    "Joumada al-Awwal", "Joumada al-Thani", "Rajab", "Cha'bane",
    "Ramadan", "Chawwal", "Dhou al-Qi'da", "Dhou al-Hijja",
]
HIJRI_AR = [
    "", "محرم", "صفر", "ربيع الأول", "ربيع الثاني",
    "جمادى الأولى", "جمادى الثانية", "رجب", "شعبان",
    "رمضان", "شوال", "ذو القعدة", "ذو الحجة",
]


def get_moon_today():
    """Geocentric moon parameters: phase, illumination, age, distance, magnitude."""
    ts = _ts()
    eph = _eph()
    earth, sun, moon = eph["earth"], eph["sun"], eph["moon"]
    now = datetime.now(_tz.utc)
    t = ts.from_datetime(now)

    e = earth.at(t)
    sun_app = e.observe(sun).apparent()
    moon_app = e.observe(moon).apparent()
    sun_lat, sun_lon, _ = sun_app.frame_latlon(_ecliptic_frame())
    moon_lat, moon_lon, _ = moon_app.frame_latlon(_ecliptic_frame())
    phase_angle = (moon_lon.degrees - sun_lon.degrees) % 360.0
    illumination = (1.0 - math.cos(math.radians(phase_angle))) / 2.0 * 100.0

    distance_km = moon_app.distance().km
    idx = int((phase_angle + 22.5) / 45.0) % 8

    nm_prev = find_previous_newmoon(now)
    age_days = (now - nm_prev).total_seconds() / 86400.0 if nm_prev else None

    p = phase_angle if phase_angle <= 180 else 360 - phase_angle
    mag = -12.7 + 0.026 * abs(p) + 4e-9 * (abs(p) ** 4)

    return {
        "phase_name_fr": PHASE_FR[idx],
        "phase_name_ar": PHASE_AR[idx],
        "phase_icon": PHASE_ICON[idx],
        "phase_angle_deg": round(phase_angle, 2),
        "illumination_percent": round(illumination, 1),
        "age_days": round(age_days, 1) if age_days is not None else None,
        "distance_km": int(distance_km),
        "magnitude": round(mag, 1),
    }


def _ecliptic_frame():
    from skyfield.framelib import ecliptic_frame
    return ecliptic_frame


def _find_phase(now_dt, target_y, lookback_days=0, lookahead_days=35):
    """Return UTC datetime of next/previous moon phase y in [0..3]."""
    from skyfield import almanac
    ts = _ts()
    eph = _eph()
    t0 = ts.from_datetime(now_dt - timedelta(days=lookback_days))
    t1 = ts.from_datetime(now_dt + timedelta(days=lookahead_days))
    try:
        t, y = almanac.find_discrete(t0, t1, almanac.moon_phases(eph))
    except Exception as e:
        log.warning("find_discrete: %s", e)
        return None
    matches = [ti.utc_datetime() for ti, yi in zip(t, y) if int(yi) == target_y]
    if not matches:
        return None
    if lookback_days > 0:
        return matches[-1]
    return matches[0]


def find_previous_newmoon(now_dt):
    return _find_phase(now_dt, 0, lookback_days=35, lookahead_days=0)


def find_next_newmoon(now_dt):
    return _find_phase(now_dt, 0, lookback_days=0, lookahead_days=45)


def crescent_visibility(newmoon_dt, lat=34.87, lng=-1.32):
    """Yallop 1997 & Odeh 2006 criteria, evaluated at sunset best-time
    on each day D=0..4 after the conjunction. Returns first visible date
    per criterion plus a consensus estimate.

    Yallop categories (q'):
      A: q > 0.216    — visible naked-eye
      B: q > -0.014   — binoculars
      C: q > -0.160   — telescope
      D:              — invisible

    Odeh categories (V):
      I:   V >= 5.65  — naked-eye
      II:  V >= 2.0   — binoculars
      III: V >= -0.96 — telescope
      IV:             — invisible
    """
    from skyfield.api import wgs84
    from skyfield import almanac
    ts = _ts()
    eph = _eph()
    earth, sun, moon = eph["earth"], eph["sun"], eph["moon"]
    obs_loc = wgs84.latlon(lat, lng)
    observer = earth + obs_loc

    yallop_first = None
    odeh_first = None

    for d in range(0, 5):
        target = newmoon_dt + timedelta(days=d)
        t0 = ts.utc(target.year, target.month, target.day, 0, 0, 0)
        t1 = ts.utc(target.year, target.month, target.day, 23, 59, 59) + 1.0  # +1 day

        # find sunset on target_date
        try:
            f_sun = almanac.sunrise_sunset(eph, obs_loc)
            t_sun, y_sun = almanac.find_discrete(t0, t1, f_sun)
        except Exception as e:
            log.warning("sunrise_sunset d=%d: %s", d, e)
            continue

        sunset_t = None
        for ti, yi in zip(t_sun, y_sun):
            if int(yi) == 0:  # sunset
                sunset_t = ti
                break
        if sunset_t is None:
            continue

        # find moonset within ~16h after sunset
        try:
            f_moon = almanac.risings_and_settings(eph, moon, obs_loc)
            t_end = ts.from_datetime(sunset_t.utc_datetime() + timedelta(hours=16))
            t_m, y_m = almanac.find_discrete(sunset_t, t_end, f_moon)
        except Exception as e:
            log.warning("risings_and_settings d=%d: %s", d, e)
            continue

        moonset_t = None
        for ti, yi in zip(t_m, y_m):
            if int(yi) == 0:
                moonset_t = ti
                break

        # Best time = sunset + 4/9 * (moonset - sunset)  [Yallop]
        if moonset_t is None:
            best_dt = sunset_t.utc_datetime() + timedelta(minutes=15)
        else:
            lag = (moonset_t.utc_datetime() - sunset_t.utc_datetime()).total_seconds()
            if lag <= 0:
                continue
            best_dt = sunset_t.utc_datetime() + timedelta(seconds=4 * lag / 9)

        best_t = ts.from_datetime(best_dt)

        obs_at = observer.at(best_t)
        moon_app = obs_at.observe(moon).apparent()
        sun_app = obs_at.observe(sun).apparent()

        moon_alt, _, moon_dist = moon_app.altaz()
        sun_alt, _, _ = sun_app.altaz()

        ARCV = moon_alt.degrees - sun_alt.degrees
        ARCL = moon_app.separation_from(sun_app).degrees

        # Topocentric semi-diameter of Moon (arcmin), from radius 1737.4 km
        sd_arcmin = math.degrees(math.atan(1737.4 / moon_dist.km)) * 60.0
        W = sd_arcmin * (1.0 - math.cos(math.radians(ARCL)))  # arcminutes

        q_yallop = (ARCV - (11.8371 - 6.3226 * W + 0.7319 * W ** 2 - 0.1018 * W ** 3)) / 10.0
        q_odeh = ARCV - (7.1651 - 6.3226 * W + 0.7319 * W ** 2 - 0.1018 * W ** 3)

        if q_yallop > 0.216:
            y_cat, y_lbl = "A", "Visible à l'œil nu"
        elif q_yallop > -0.014:
            y_cat, y_lbl = "B", "Visible aux jumelles"
        elif q_yallop > -0.160:
            y_cat, y_lbl = "C", "Télescope nécessaire"
        else:
            y_cat, y_lbl = "D", "Invisible"

        if q_odeh >= 5.65:
            o_cat, o_lbl = "I", "Visible à l'œil nu"
        elif q_odeh >= 2.0:
            o_cat, o_lbl = "II", "Visible aux jumelles"
        elif q_odeh >= -0.96:
            o_cat, o_lbl = "III", "Télescope nécessaire"
        else:
            o_cat, o_lbl = "IV", "Invisible"

        date_str = best_dt.date().isoformat()

        if yallop_first is None and y_cat in ("A", "B"):
            yallop_first = {
                "date": date_str,
                "category": y_cat,
                "category_label": y_lbl,
                "q_value": round(q_yallop, 4),
                "ARCV": round(ARCV, 2),
                "ARCL": round(ARCL, 2),
                "W_arcmin": round(W, 3),
                "moon_age_hours": round((best_dt - newmoon_dt).total_seconds() / 3600.0, 1),
            }
        if odeh_first is None and o_cat in ("I", "II"):
            odeh_first = {
                "date": date_str,
                "category": o_cat,
                "category_label": o_lbl,
                "q_value": round(q_odeh, 4),
                "ARCV": round(ARCV, 2),
                "ARCL": round(ARCL, 2),
                "W_arcmin": round(W, 3),
                "moon_age_hours": round((best_dt - newmoon_dt).total_seconds() / 3600.0, 1),
            }

        if yallop_first and odeh_first:
            break

    consensus = None
    confidence = "low"
    if yallop_first and odeh_first:
        if yallop_first["date"] == odeh_first["date"]:
            consensus = yallop_first["date"]
            confidence = "high"
        else:
            # consensus = later date (more conservative)
            consensus = max(yallop_first["date"], odeh_first["date"])
            confidence = "medium"
    elif yallop_first:
        consensus = yallop_first["date"]
        confidence = "medium"
    elif odeh_first:
        consensus = odeh_first["date"]
        confidence = "medium"

    return {
        "yallop_1997": yallop_first or {
            "date": None, "category": "D", "category_label": "Invisible (5j)",
        },
        "odeh_2006": odeh_first or {
            "date": None, "category": "IV", "category_label": "Invisible (5j)",
        },
        "consensus_date": consensus,
        "confidence": confidence,
        "observer": {"lat": lat, "lng": lng},
    }


def hijri_today():
    from hijridate import Gregorian
    today = date.today()
    h = Gregorian(today.year, today.month, today.day).to_hijri()
    return {
        "day": h.day,
        "month": h.month,
        "month_name_fr": HIJRI_FR[h.month],
        "month_name_ar": HIJRI_AR[h.month],
        "month_name_en": h.month_name(),
        "year": h.year,
    }


def islamic_calendar(years=3):
    """Return ~10 events per Hijri year for the next `years` years."""
    from hijridate import Hijri, Gregorian
    today = date.today()
    cur_h = Gregorian(today.year, today.month, today.day).to_hijri()

    events_template = [
        ("🌟", "Nouvel An hégirien",       "New Year (Muharram)", "رأس السنة الهجرية", 1, 1),
        ("🕊️", "Achoura",                  "Ashura",              "عاشوراء",          1, 10),
        ("💫", "Mawlid an-Nabi",           "Mawlid",              "المولد النبوي",     3, 12),
        ("🌌", "Isra wal Mi'raj",          "Isra wal Mi'raj",     "الإسراء والمعراج",  7, 27),
        ("🌃", "Laylat al-Bara'a",         "Laylat al-Bara'a",    "ليلة البراءة",      8, 15),
        ("⭐", "Début Ramadan",            "Ramadan begins",      "بداية رمضان",       9, 1),
        ("💎", "Laylat al-Qadr (estimation)", "Laylat al-Qadr",   "ليلة القدر",        9, 27),
        ("🌙", "Aïd al-Fitr",              "Eid al-Fitr",         "عيد الفطر",         10, 1),
        ("🕋", "Jour d'Arafat",            "Day of Arafah",       "يوم عرفة",          12, 9),
        ("🐏", "Aïd al-Adha",              "Eid al-Adha",         "عيد الأضحى",        12, 10),
    ]

    events = []
    for y in range(cur_h.year, cur_h.year + max(1, int(years))):
        for icon, name_fr, name_en, name_ar, mon, day in events_template:
            try:
                g = Hijri(y, mon, day).to_gregorian()
                events.append({
                    "icon": icon,
                    "name_fr": name_fr,
                    "name_en": name_en,
                    "name_ar": name_ar,
                    "hijri": f"{day} {HIJRI_FR[mon]} {y}",
                    "hijri_short": f"{day:02d}/{mon:02d}/{y}",
                    "gregorian_date": f"{g.year:04d}-{g.month:02d}-{g.day:02d}",
                    "method": "astronomical_pure",
                })
            except Exception as e:
                log.warning("calendar %d-%d-%d: %s", y, mon, day, e)
    events.sort(key=lambda x: x["gregorian_date"])
    return events


def prayer_times_5_methods(lat, lng, date_local=None, tz_name=None):
    from adhan.adhan import adhan as _adhan
    from adhan.methods import (
        MUSLIM_WORLD_LEAGUE, ISNA, KARACHI, EGYPT, MAKKAH, ASR_STANDARD,
    )
    import pytz

    if date_local is None:
        date_local = date.today()

    if tz_name is None:
        try:
            tz_name = _tf().timezone_at(lat=lat, lng=lng) or "UTC"
        except Exception:
            tz_name = "UTC"

    try:
        tz = pytz.timezone(tz_name)
        sample = datetime.combine(date_local, datetime.min.time())
        tz_offset = tz.utcoffset(sample).total_seconds() / 3600.0
    except Exception:
        tz_offset = 0.0
        tz_name = "UTC"

    methods = {
        "MWL":       ("Muslim World League",            MUSLIM_WORLD_LEAGUE),
        "ISNA":      ("Islamic Society of N. America",  ISNA),
        "Karachi":   ("Univ. Sciences Karachi",         KARACHI),
        "Egypt":     ("Egyptian General Authority",     EGYPT),
        "UmmAlQura": ("Umm Al-Qura, Makkah",            MAKKAH),
    }

    out = {}
    fasting_minutes = None
    for key, (label, params_dict) in methods.items():
        params = {**params_dict, **ASR_STANDARD}
        try:
            t = _adhan(date_local, (lat, lng), params, timezone_offset=tz_offset)
            fajr = t["fajr"]
            out[key] = {
                "label":       label,
                "imsak_10min": (fajr - timedelta(minutes=10)).strftime("%H:%M"),
                "imsak_15min": (fajr - timedelta(minutes=15)).strftime("%H:%M"),
                "imsak_20min": (fajr - timedelta(minutes=20)).strftime("%H:%M"),
                "fajr":        fajr.strftime("%H:%M"),
                "sunrise":     t["shuruq"].strftime("%H:%M"),
                "dhuhr":       t["zuhr"].strftime("%H:%M"),
                "asr":         t["asr"].strftime("%H:%M"),
                "maghrib":     t["maghrib"].strftime("%H:%M"),
                "isha":        t["isha"].strftime("%H:%M"),
            }
            if key == "MWL":
                fasting_minutes = int((t["maghrib"] - fajr).total_seconds() / 60)
        except Exception as e:
            log.warning("prayer %s: %s", key, e)
            out[key] = {"label": label, "error": str(e)[:200]}

    return {
        "methods": out,
        "fasting_duration_minutes": fasting_minutes,
        "timezone": tz_name,
        "tz_offset_hours": tz_offset,
    }


def ramadan_status():
    from hijridate import Gregorian, Hijri
    today = date.today()
    h = Gregorian(today.year, today.month, today.day).to_hijri()

    if h.month == 9:
        return {
            "in_ramadan": True,
            "day": h.day,
            "total": 30,
            "hijri_year": h.year,
        }

    target_year = h.year if h.month < 9 else h.year + 1
    nr = Hijri(target_year, 9, 1).to_gregorian()
    nr_g = date(nr.year, nr.month, nr.day)
    days_until = (nr_g - today).days
    return {
        "in_ramadan": False,
        "next_ramadan_gregorian": nr_g.isoformat(),
        "next_ramadan_hijri_year": target_year,
        "days_until": days_until,
    }


_CITY_CACHE = {}
_CITY_CACHE_TTL = 86400.0


def cities_search(q, limit=10):
    """Free-form city search via OpenStreetMap Nominatim. Cached 24h."""
    import json
    import urllib.parse
    import urllib.request

    q = (q or "").strip()
    if len(q) < 2:
        return []

    cache_key = f"{q.lower()}:{limit}"
    now_ts = _t.time()
    cached = _CITY_CACHE.get(cache_key)
    if cached and (now_ts - cached[0]) < _CITY_CACHE_TTL:
        return cached[1]

    params = urllib.parse.urlencode({
        "format": "json",
        "q": q,
        "limit": limit,
        "addressdetails": 1,
        "accept-language": "fr",
        "featuretype": "city",
    })
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    req = urllib.request.Request(
        url, headers={"User-Agent": "ASTRO-SCAN-CHOHRA/1.0 (zakaria.chohra@gmail.com)"}
    )

    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log.warning("Nominatim search failed: %s", e)
        return []

    results = []
    seen = set()
    for item in data:
        cls = item.get("class", "")
        typ = item.get("type", "")
        # accept place / city / town / village / boundary administrative
        if cls not in ("place", "boundary") and typ not in (
            "city", "town", "village", "administrative", "municipality",
        ):
            continue
        addr = item.get("address") or {}
        name = (
            addr.get("city") or addr.get("town") or addr.get("village")
            or addr.get("municipality") or addr.get("hamlet")
            or item.get("display_name", "").split(",")[0].strip()
        )
        country = addr.get("country") or ""
        cc = (addr.get("country_code") or "").upper()
        try:
            lat = float(item["lat"])
            lng = float(item["lon"])
        except Exception:
            continue
        key = (name, country)
        if key in seen:
            continue
        seen.add(key)
        flag = (
            "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in cc)
            if len(cc) == 2 and cc.isalpha() else "🏳️"
        )
        results.append({
            "name": name,
            "country": country,
            "country_code": cc,
            "lat": round(lat, 4),
            "lng": round(lng, 4),
            "flag": flag,
        })
        if len(results) >= limit:
            break

    _CITY_CACHE[cache_key] = (now_ts, results)
    return results
