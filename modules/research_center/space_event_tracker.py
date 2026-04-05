"""
Research Center — Space event tracker.
Aggregates ISS and satellite activity from existing APIs (read-only).
"""
def get_iss_activity():
    """Return ISS position/summary from existing module."""
    try:
        from modules.orbit_engine import get_iss_precise, get_iss_crew
    except ImportError:
        return {'lat': None, 'lon': None, 'crew_count': 0, 'source': 'unavailable'}
    pos = get_iss_precise()
    if pos.get('error'):
        return {'lat': None, 'lon': None, 'crew_count': 0, 'source': 'error'}
    crew = get_iss_crew() or []
    return {
        'lat': pos.get('lat'),
        'lon': pos.get('lon'),
        'alt_km': pos.get('alt_km'),
        'speed_kms': pos.get('speed_kms'),
        'crew_count': len(crew),
        'source': pos.get('source', 'Skyfield'),
    }


def get_space_weather_summary():
    """Aggregate space weather: solar + ISS. Uses existing modules only."""
    solar = {}
    try:
        from modules.research_center.solar_activity_monitor import get_solar_activity
        solar = get_solar_activity()
    except Exception:
        pass
    iss = get_iss_activity()
    return {
        'solar': solar,
        'iss': iss,
    }
