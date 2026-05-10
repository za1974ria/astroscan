"""
Source unique de vérité pour l'équipage ISS actuel (fallback statique).

Cette constante sert de fallback fiable quand les API externes
(open-notify, thespacedevs) renvoient des données obsolètes ou échouent.

ATTENTION : open-notify.org/astros.json N'EST PLUS MAINTENU depuis 2023+.
Il retourne en permanence l'équipage Crew-8 / Soyouz MS-25 (2024) :
  Kononenko, Chub, Caldwell Dyson, Dominick, Barratt, Epps, Grebenkin,
  Wilmore, Williams (9 noms).
On utilise donc cette signature comme heuristique de détection "stale"
dans services/iss_live.py.

À METTRE À JOUR manuellement après chaque rotation d'équipage
(typiquement tous les 6 mois). Source officielle :
  https://www.nasa.gov/international-space-station/space-station-crews/
  https://en.wikipedia.org/wiki/Expedition_74

Dernière vérification : 2026-05-10 (Zakaria + Claude Opus 4.7).
Aucune source web fiable n'a pu confirmer les noms à cette date,
donc liste laissée VIDE intentionnellement (mieux que des noms inventés).
"""
from datetime import date

# Équipage ISS actuel (mai 2026). À actualiser manuellement.
# Liste laissée vide tant qu'aucune source officielle n'a été confirmée.
# Le frontend doit afficher uniquement le compteur live (7) sans liste de noms.
ISS_CREW_CURRENT: list[str] = []

# Date de la dernière mise à jour manuelle (pour TTL frontend)
ISS_CREW_LAST_UPDATE = date(2026, 5, 10)

# Nombre actuel par défaut (cohérent avec /api/iss qui retourne 7 live).
# Ce nombre est utilisé UNIQUEMENT comme fallback ultime ; en pratique
# l'endpoint /api/iss/crew renverra le nombre live de _get_iss_crew().
ISS_CREW_COUNT_FALLBACK = 7

# TTL : si la liste a plus de N jours, frontend doit considérer
# uniquement le compteur live, pas la liste de noms.
ISS_CREW_NAMES_TTL_DAYS = 30

# Heuristique de détection "stale" : si une source externe contient
# au moins 2 de ces noms, c'est l'équipage 2024 obsolète d'open-notify.
# On retourne alors une liste vide + flag stale plutôt que les vieux noms.
ISS_CREW_STALE_SIGNATURES = (
    "Kononenko",
    "Caldwell Dyson",
    "Dominick",
    "Grebenkin",
)
