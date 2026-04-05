# -*- coding: utf-8 -*-
"""
Module Mission Control — statut global du système AstroScan.
Aucune dépendance externe.
"""


def get_global_mission_status():
    """Retourne un dictionnaire JSON avec le statut système."""
    return {
        'ok': True,
        'status': 'operational',
        'iss': {'status': 'tracking', 'source': 'open-notify'},
        'mars': {'status': 'standby', 'source': 'nasa'},
        'neo': {'status': 'standby', 'source': 'nasa'},
        'voyager': {'status': 'standby', 'source': 'jpl'},
    }
