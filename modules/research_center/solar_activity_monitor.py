"""
Research Center — Solar activity monitor.
Aggregates solar weather from existing sources (no modification of existing modules).
"""
import os
from pathlib import Path


def get_solar_activity():
    """Return solar activity summary from existing API/module."""
    try:
        from modules.space_alerts import get_solar_weather
    except ImportError:
        return _fetch_solar_v1()
    data = get_solar_weather()
    if not data or data.get('error'):
        return _fetch_solar_v1()
    return {
        'status': data.get('status', 'UNKNOWN'),
        'speed_kms': data.get('speed_kms'),
        'density': data.get('density'),
        'temperature': data.get('temperature'),
        'source': data.get('source', 'NOAA SWPC'),
    }


def _fetch_solar_v1():
    """Fallback: could call /api/v1/solar-weather via curl; return minimal."""
    return {'status': 'UNKNOWN', 'source': 'unavailable'}
