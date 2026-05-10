"""Hilal compute helpers — Croissant Islamique, calculs astropy + ephem.

Extrait de station_web.py (PASS 15) pour permettre l'utilisation
par astro_bp sans dépendance circulaire.

Fonctions exposées :
    hilal_compute(for_date=None) -> dict       # 1 mois courant
    hilal_compute_calendar() -> dict           # 24 prochains mois

Critères supportés : ODEH 2006, UIOF/France, Oum Al Qura, Istanbul 1978.
Coordonnées par défaut : Tlemcen 34.87°N 1.32°W 816m.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.constants.observatory import OBSERVER_LAT, OBSERVER_LON, OBSERVER_ALT_M

_HIJRI_MONTHS = [
    'Mouharram','Safar','Rabi al-Awwal','Rabi al-Thani',
    'Joumada al-Oula','Joumada al-Thania','Rajab','Chaabane',
    'Ramadan','Chawwal','Dhou al-Qi\'da','Dhou al-Hijja'
]

def hilal_compute(for_date=None):
    """
    Calcule la visibilité du croissant islamique pour Tlemcen.
    Retourne un dict complet avec critères ODEH, UIOF et Oum Al Qura.
    """
    import math
    import ephem
    from datetime import timedelta
    from astropy.coordinates import (EarthLocation, AltAz, get_body, get_sun,
                                     solar_system_ephemeris)
    from astropy.time import Time
    import astropy.units as u

    LAT, LON, ALT = OBSERVER_LAT, OBSERVER_LON, OBSERVER_ALT_M
    location = EarthLocation(lat=LAT * u.deg, lon=LON * u.deg, height=ALT * u.m)

    # Date de référence
    if for_date is None:
        for_date = datetime.now(timezone.utc).date()

    # ── 1. Trouver la prochaine nouvelle lune ──
    obs = ephem.Observer()
    obs.lat = str(LAT)
    obs.lon = str(LON)
    obs.elevation = ALT
    obs.pressure = 0
    obs.horizon = '-0:34'

    ref_dt = datetime(for_date.year, for_date.month, for_date.day, 12, 0, 0)
    obs.date = ref_dt.strftime('%Y/%m/%d %H:%M:%S')

    next_new = ephem.next_new_moon(obs.date)
    next_new_dt = next_new.datetime().replace(tzinfo=timezone.utc)

    # ── 2. Coucher du soleil le jour J et J+1 après la nouvelle lune ──
    def find_sunset(day):
        """Retourne l'heure du coucher soleil (UTC) pour un jour donné."""
        obs2 = ephem.Observer()
        obs2.lat = str(LAT)
        obs2.lon = str(LON)
        obs2.elevation = ALT
        obs2.pressure = 1013
        obs2.horizon = '-0:50'  # réfraction
        obs2.date = f"{day.year}/{day.month:02d}/{day.day:02d} 12:00:00"
        try:
            sunset_ephem = obs2.next_setting(ephem.Sun())
            return sunset_ephem.datetime().replace(tzinfo=timezone.utc)
        except Exception:
            return datetime(day.year, day.month, day.day, 18, 30, tzinfo=timezone.utc)

    # Jour de la nouvelle lune et lendemain
    nm_day = next_new_dt.date()
    days_to_check = [nm_day, nm_day + timedelta(days=1)]

    results_by_day = []
    for check_day in days_to_check:
        sunset_dt = find_sunset(check_day)
        t_sunset = Time(sunset_dt)

        frame = AltAz(obstime=t_sunset, location=location)
        moon_coord = get_body('moon', t_sunset).transform_to(frame)
        sun_coord = get_sun(t_sunset).transform_to(frame)

        moon_alt = float(moon_coord.alt.deg)
        moon_az = float(moon_coord.az.deg)
        sun_alt = float(sun_coord.alt.deg)

        # Elongation géocentrique (ARCL)
        with solar_system_ephemeris.set('builtin'):
            moon_gcrs = get_body('moon', t_sunset)
            sun_gcrs = get_sun(t_sunset)
        arcl_deg = float(moon_gcrs.separation(sun_gcrs).deg)

        # ARCV = altitude de la lune au coucher du soleil
        arcv_deg = moon_alt

        # Largeur du croissant (W) en minutes d'arc — formule Odeh
        # W = 0.27245 * SD * (1 - cos(ARCL))  où SD = demi-diamètre moyen ≈ 0.2725°
        crescent_w_deg = 0.27245 * (1.0 - math.cos(math.radians(arcl_deg)))
        crescent_w_arcmin = crescent_w_deg * 60.0

        # Âge lunaire depuis la nouvelle lune (heures)
        moon_age_h = (sunset_dt - next_new_dt).total_seconds() / 3600.0

        # ── Critère ODEH (2006) ──
        # Visible si ARCL ≥ 6.4° ET W ≥ 0.216°
        # Incertain si ARCL ≥ 6.4° ET W ≥ 0.1°
        if arcl_deg >= 6.4 and crescent_w_deg >= 0.216:
            odeh = 'VISIBLE'
        elif arcl_deg >= 6.4 and crescent_w_deg >= 0.1:
            odeh = 'INCERTAIN'
        elif moon_alt > 0 and moon_age_h >= 15:
            odeh = 'POSSIBLE'
        else:
            odeh = 'NON VISIBLE'

        # ── Critère UIOF / France ──
        # Lune visible si altitude > 3° au coucher du soleil ET Âge > 15h
        if arcv_deg >= 5.0 and moon_age_h >= 15:
            uiof = 'VISIBLE'
        elif arcv_deg >= 3.0 and moon_age_h >= 12:
            uiof = 'INCERTAIN'
        else:
            uiof = 'NON VISIBLE'

        # ── Critère Oum Al Qura (Arabie Saoudite) ──
        # Lune visible si elle se couche APRÈS le soleil ET lune couchée ≥ 5 min après soleil
        obs3 = ephem.Observer()
        obs3.lat = str(LAT); obs3.lon = str(LON); obs3.elevation = ALT
        obs3.pressure = 1013; obs3.horizon = '-0:50'
        obs3.date = f"{check_day.year}/{check_day.month:02d}/{check_day.day:02d} 12:00:00"
        try:
            moonset_ephem = obs3.next_setting(ephem.Moon())
            moonset_dt = moonset_ephem.datetime().replace(tzinfo=timezone.utc)
            lag_min = (moonset_dt - sunset_dt).total_seconds() / 60.0
            oumqura = 'VISIBLE' if lag_min >= 5 and moon_alt > 0 else 'NON VISIBLE'
        except Exception:
            oumqura = 'INCERTAIN'
            lag_min = 0.0

        # Coucher de la lune
        try:
            moonset_str = moonset_dt.strftime('%H:%M UTC') if 'moonset_dt' in dir() else '—'
        except Exception:
            moonset_str = '—'

        results_by_day.append({
            'date': check_day.isoformat(),
            'sunset_utc': sunset_dt.strftime('%H:%M UTC'),
            'moonset_utc': moonset_str,
            'moon_alt_deg': round(arcv_deg, 2),
            'moon_az_deg': round(moon_az, 2),
            'arcl_deg': round(arcl_deg, 2),
            'arcv_deg': round(arcv_deg, 2),
            'crescent_width_arcmin': round(crescent_w_arcmin, 3),
            'crescent_width_deg': round(crescent_w_deg, 4),
            'moon_age_hours': round(max(0, moon_age_h), 1),
            'criteria': {
                'odeh': odeh,
                'uiof': uiof,
                'oum_al_qura': oumqura,
            },
            'moonset_lag_min': round(lag_min, 1) if 'lag_min' in dir() else None,
        })

    # ── 3. Mois hégirien approximatif ──
    # Comptage depuis 1 Mouharram 1 AH = 16 juillet 622 CE
    J0 = 1948439.5  # JD du 1 Mouharram 1 AH (approx)
    jd_now = Time(datetime.now(timezone.utc)).jd
    hijri_days = jd_now - J0
    hijri_months_total = hijri_days / 29.53058867
    hijri_year = int(hijri_months_total / 12) + 1
    hijri_month_idx = int(hijri_months_total % 12)
    hijri_month_name = _HIJRI_MONTHS[hijri_month_idx % 12]
    hijri_day = int((hijri_months_total % 1) * 29.53) + 1

    # ── 4. Compte à rebours jusqu'au premier jour possible ──
    best_day = None
    best_criteria = 'NON VISIBLE'
    for r in results_by_day:
        if r['criteria']['odeh'] in ('VISIBLE', 'INCERTAIN') or \
           r['criteria']['uiof'] in ('VISIBLE', 'INCERTAIN'):
            best_day = r['date']
            best_criteria = r['criteria']
            break
    if best_day is None:
        best_day = results_by_day[-1]['date'] if results_by_day else (nm_day + timedelta(days=1)).isoformat()

    delta_days = (datetime.fromisoformat(best_day).date() - for_date).days

    return {
        'ok': True,
        'computed_at': datetime.now(timezone.utc).isoformat(),
        'location': {'city': 'Tlemcen', 'lat': LAT, 'lon': LON, 'alt_m': ALT},
        'hijri_current': {
            'year': hijri_year,
            'month_num': hijri_month_idx + 1,
            'month_name': hijri_month_name,
            'day': hijri_day,
        },
        'new_moon': {
            'datetime_utc': next_new_dt.isoformat(),
            'date': nm_day.isoformat(),
        },
        'sighting_days': results_by_day,
        'predicted_first_day': best_day,
        'countdown_days': delta_days,
        'next_month_name': _HIJRI_MONTHS[(hijri_month_idx + 1) % 12],
        'next_hijri_year': hijri_year + (1 if hijri_month_idx == 11 else 0),
    }


def hilal_compute_calendar():
    """
    Génère le calendrier hégire pour les 24 prochains mois.
    Critères : ODEH 2006 (principal) + Istanbul 1978 / IRCICA (secondaire).
    Cache 24h recommandé (données stables).
    """
    import math
    import ephem
    from datetime import timedelta

    LAT, LON, ALT = OBSERVER_LAT, OBSERVER_LON, OBSERVER_ALT_M   # Tlemcen précis

    now   = datetime.now(timezone.utc)
    today = now.date()

    # ── Mois hégire courant (même formule que _hilal_compute) ──
    J0 = 1948439.5
    from astropy.time import Time as _ATime
    jd_now              = _ATime(now).jd
    total_months        = int((jd_now - J0) / 29.53058867)
    h_year_base         = total_months // 12 + 1
    h_month_idx_base    = total_months % 12          # 0-indexed, mois courant

    # ── Helpers ephem ──
    def _obs(day, pressure=1013, horizon='-0:50'):
        o = ephem.Observer()
        o.lat = str(LAT); o.lon = str(LON)
        o.elevation = ALT; o.pressure = pressure; o.horizon = horizon
        o.date = f'{day.year}/{day.month:02d}/{day.day:02d} 12:00:00'
        return o

    def _sunset(day):
        try:
            return _obs(day).next_setting(ephem.Sun()).datetime().replace(tzinfo=timezone.utc)
        except Exception:
            return datetime(day.year, day.month, day.day, 18, 30, tzinfo=timezone.utc)

    def _sighting(check_day, nm_dt):
        sunset_dt = _sunset(check_day)

        # Position lune + soleil au moment du coucher du soleil
        o2 = ephem.Observer()
        o2.lat = str(LAT); o2.lon = str(LON)
        o2.elevation = ALT; o2.pressure = 1013; o2.horizon = '-0:34'
        o2.date = ephem.Date(sunset_dt.strftime('%Y/%m/%d %H:%M:%S'))

        moon = ephem.Moon(); sun_obj = ephem.Sun()
        moon.compute(o2); sun_obj.compute(o2)

        moon_alt = math.degrees(moon.alt)
        arcl_deg = math.degrees(ephem.separation(moon, sun_obj))

        crescent_w_deg    = 0.27245 * (1.0 - math.cos(math.radians(arcl_deg)))
        crescent_w_arcmin = crescent_w_deg * 60.0
        moon_age_h        = max(0.0, (sunset_dt - nm_dt).total_seconds() / 3600.0)

        # Coucher lune + lag
        o3 = _obs(check_day, pressure=1013, horizon='-0:34')
        try:
            moonset_dt  = o3.next_setting(ephem.Moon()).datetime().replace(tzinfo=timezone.utc)
            lag_min     = (moonset_dt - sunset_dt).total_seconds() / 60.0
            moonset_str = moonset_dt.strftime('%H:%M UTC')
        except Exception:
            lag_min = 0.0; moonset_str = '—'

        # ODEH 2006 — critère international de référence
        if arcl_deg >= 6.4 and crescent_w_deg >= 0.216:
            odeh = 'VISIBLE'
        elif arcl_deg >= 6.4 and crescent_w_deg >= 0.1:
            odeh = 'INCERTAIN'
        elif moon_alt > 0 and moon_age_h >= 15:
            odeh = 'POSSIBLE'
        else:
            odeh = 'NON VISIBLE'

        # Istanbul 1978 — IRCICA : alt ≥ 5° + arcl ≥ 8° + âge ≥ 15h
        if moon_alt >= 5.0 and arcl_deg >= 8.0 and moon_age_h >= 15:
            istanbul = 'VISIBLE'
        elif moon_alt >= 3.0 and arcl_deg >= 6.0 and moon_age_h >= 12:
            istanbul = 'INCERTAIN'
        else:
            istanbul = 'NON VISIBLE'

        # Oum Al Qura — moonset lag ≥ 5 min
        oumqura = 'VISIBLE' if lag_min >= 5 and moon_alt > 0 else 'NON VISIBLE'

        return {
            'date':                 check_day.isoformat(),
            'sunset_utc':           sunset_dt.strftime('%H:%M UTC'),
            'moonset_utc':          moonset_str,
            'arcl_deg':             round(arcl_deg, 2),
            'arcv_deg':             round(moon_alt, 2),
            'crescent_width_arcmin': round(crescent_w_arcmin, 3),
            'moon_age_hours':       round(moon_age_h, 1),
            'moonset_lag_min':      round(lag_min, 1),
            'criteria': {'odeh': odeh, 'istanbul': istanbul, 'oum_al_qura': oumqura},
        }

    def _pick_first(days):
        # Priorité ODEH VISIBLE → Istanbul VISIBLE → INCERTAIN → J+1 par défaut
        for d in days:
            if d['criteria']['odeh'] == 'VISIBLE':
                return d['date'], d['criteria'], 'ODEH'
        for d in days:
            if d['criteria']['istanbul'] == 'VISIBLE':
                return d['date'], d['criteria'], 'Istanbul'
        for d in days:
            if d['criteria']['odeh'] in ('INCERTAIN', 'POSSIBLE') or \
               d['criteria']['istanbul'] == 'INCERTAIN':
                return d['date'], d['criteria'], 'calcul'
        return days[-1]['date'], days[-1]['criteria'], 'astronomique'

    def _badge(crit):
        o = crit.get('odeh', ''); i = crit.get('istanbul', '')
        if o == 'VISIBLE' and i == 'VISIBLE':   return 'CONFIRMÉ',  95
        if o == 'VISIBLE':                        return 'PROBABLE',  85
        if i == 'VISIBLE':                        return 'PROBABLE',  78
        if o in ('INCERTAIN', 'POSSIBLE') or i == 'INCERTAIN':
                                                  return 'INCERTAIN', 60
        return 'CALCUL', 30

    # ── Boucle 24 nouvelles lunes ──
    search_dt   = now
    h_year      = h_year_base
    h_month_idx = h_month_idx_base
    calendar    = []

    for _ in range(24):
        o_nm = ephem.Observer()
        o_nm.lat = str(LAT); o_nm.lon = str(LON)
        o_nm.elevation = ALT; o_nm.pressure = 0
        o_nm.date = search_dt.strftime('%Y/%m/%d %H:%M:%S')

        nm_ephem = ephem.next_new_moon(o_nm.date)
        nm_dt    = nm_ephem.datetime().replace(tzinfo=timezone.utc)
        nm_day   = nm_dt.date()

        sighting = [_sighting(nm_day + timedelta(days=off), nm_dt) for off in range(2)]
        first_day_str, first_crit, method = _pick_first(sighting)
        badge, pct = _badge(first_crit)

        # Avancer le compteur hégire
        h_month_idx = (h_month_idx + 1) % 12
        if h_month_idx == 0:
            h_year += 1

        month_name = _HIJRI_MONTHS[h_month_idx]
        calendar.append({
            'hijri_month_num':    h_month_idx + 1,
            'hijri_month_name':   month_name,
            'hijri_year':         h_year,
            'date_1er_gregorien': first_day_str,
            'new_moon_utc':       nm_dt.isoformat(),
            'badge':              badge,
            'certitude_pct':      pct,
            'method':             method,
            'criteria':           first_crit,
            'sighting_days':      sighting,
            'is_ramadan':         h_month_idx == 8,
            'is_aid_fitr':        h_month_idx == 9,
            'is_aid_adha':        h_month_idx == 11,
        })

        search_dt = nm_dt + timedelta(days=29)

    # Prochain Ramadan + compte à rebours
    next_ramadan = next((m for m in calendar if m['is_ramadan']), None)
    countdown_ramadan = None
    if next_ramadan:
        rd = datetime.fromisoformat(next_ramadan['date_1er_gregorien']).date()
        countdown_ramadan = (rd - today).days

    return {
        'ok':           True,
        'computed_at':  now.isoformat(),
        'location':     {'city': 'Tlemcen', 'lat': LAT, 'lon': LON, 'alt_m': ALT},
        'ephemeris':    'VSOP87 / Méeus (ephem) + DE430 (astropy)',
        'criteria_info': {
            'primary':   'ODEH 2006 — International Astronomical Center',
            'secondary': 'Istanbul 1978 — IRCICA (alt ≥ 5° + arcl ≥ 8° + âge ≥ 15h)',
            'note':      'Précision ±1 jour · Tlemcen 34.87°N 1.32°W 816m · Cache 24h',
        },
        'calendar':               calendar,
        'next_ramadan':           next_ramadan,
        'countdown_ramadan_days': countdown_ramadan,
    }

# Aliases compat
_hilal_compute = hilal_compute
_hilal_compute_calendar = hilal_compute_calendar
