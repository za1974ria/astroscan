"""Service station_state — chemin racine du déploiement AstroScan.

Extrait depuis station_web.py L179 lors de PASS 23.

Note : la valeur reste hard-codée (verbatim copie) pour préserver le
comportement historique. `app.config.STATION` expose la même variable
mais avec lecture os.environ — les deux sources convergeront lors d'un
PASS ultérieur d'unification de la configuration.
"""

STATION: str = '/root/astro_scan'
