"""Service station_state — chemin racine du déploiement AstroScan.

Extrait depuis station_web.py L179 lors de PASS 23.

PASS 2D fix (2026-05-07) — Phase 2D Architecture Purification :
La valeur '/root/astro_scan' était hardcodée pour préserver le comportement
historique. Cela cassait :
- La CI GitHub Actions (PermissionError sur /root/astro_scan/.env)
- Tout déploiement sur un chemin différent (Docker, autre serveur, dev local)

La résolution est maintenant DYNAMIQUE :
1. Si la variable d'environnement ASTROSCAN_HOME est définie, elle gagne.
2. Sinon, le chemin est calculé depuis __file__ (ce fichier est à
   <PROJECT_ROOT>/app/services/station_state.py).

Comportement en production (Hetzner /root/astro_scan) : INCHANGÉ.
Comportement en CI / dev / Docker : FONCTIONNEL.
"""

import os
from pathlib import Path

# Le fichier est à : <PROJECT_ROOT>/app/services/station_state.py
# Donc PROJECT_ROOT = parent.parent.parent
_DEFAULT_STATION: str = str(Path(__file__).resolve().parent.parent.parent)

# Override possible via variable d'environnement (Docker, CI, déploiements alternatifs)
STATION: str = os.environ.get('ASTROSCAN_HOME', _DEFAULT_STATION)
