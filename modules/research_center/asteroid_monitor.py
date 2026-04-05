"""
Research Center — Asteroid (NEO) monitor.
Aggregates near-Earth object data from existing sources.
"""
def get_neo_summary():
    """Return NEO summary from existing API/module."""
    try:
        from modules.space_alerts import get_asteroid_alerts
    except ImportError:
        return {'total_today': 0, 'hazardous': [], 'source': 'unavailable'}
    data = get_asteroid_alerts()
    if not data:
        return {'total_today': 0, 'hazardous': [], 'source': 'NASA NeoWs'}
    return {
        'total_today': data.get('total_today', 0),
        'hazardous': data.get('alerts', [])[:20],
        'source': data.get('source', 'NASA NeoWs'),
    }
