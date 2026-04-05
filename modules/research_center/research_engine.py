"""
Research Center — Research engine.
Produces structured research summaries by aggregating existing AstroScan data.
Does not modify any existing module; only reads from them.
"""
from datetime import datetime, timezone

from .solar_activity_monitor import get_solar_activity
from .asteroid_monitor import get_neo_summary
from .space_event_tracker import get_iss_activity, get_space_weather_summary
from .research_logger import write_log, list_logs


def get_research_summary():
    """
    Aggregate scientific information from existing modules and produce a structured summary.
    """
    solar = get_solar_activity()
    neo = get_neo_summary()
    iss = get_iss_activity()
    # Optional: discoveries from space_analysis_engine (read-only)
    discoveries = []
    try:
        from modules.space_analysis_engine.data_logger import load_discoveries
        discoveries = load_discoveries()[-10:]
    except Exception:
        pass
    summary = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'solar_activity': solar,
        'near_earth_objects': {
            'total_today': neo.get('total_today', 0),
            'hazardous_count': len(neo.get('hazardous', [])),
            'source': neo.get('source'),
        },
        'iss_activity': iss,
        'recent_discoveries_count': len(discoveries),
    }
    return summary


def get_research_events(limit=30):
    """Return recent research events (space weather, NEO, etc.) from logs and live data."""
    events = []
    solar = get_solar_activity()
    if solar.get('status'):
        events.append({
            'type': 'solar',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'title': 'Solar activity',
            'detail': solar.get('status') + (' — ' + str(solar.get('speed_kms', '')) + ' km/s' if solar.get('speed_kms') else ''),
        })
    neo = get_neo_summary()
    if neo.get('total_today', 0) > 0:
        events.append({
            'type': 'neo',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'title': 'NEO update',
            'detail': f"{neo['total_today']} NEO today, {len(neo.get('hazardous', []))} potentially hazardous",
        })
    iss = get_iss_activity()
    if iss.get('lat') is not None:
        events.append({
            'type': 'iss',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'title': 'ISS position',
            'detail': f"Lat {iss.get('lat')}, Lon {iss.get('lon')}, Crew {iss.get('crew_count', 0)}",
        })
    logged = list_logs(limit=limit)
    for e in logged:
        events.append({
            'type': e.get('kind', 'log'),
            'timestamp': e.get('timestamp', ''),
            'title': e.get('title', e.get('kind', 'event')),
            'detail': e.get('detail', e.get('summary', '')),
        })
    events.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    return events[:limit]
