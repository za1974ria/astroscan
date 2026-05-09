"""AstroScan-Chohra — Background workers (PASS 21+).

Ce package regroupe les threads de fond extraits de station_web.py
(traducteurs, collecteurs TLE/AIS, sync SkyView, etc.) lors du chantier
de modularisation du monolithe (PASS 21.x).

Chaque worker expose typiquement :
- une fonction principale (e.g. ``translate_worker``) qui boucle indéfiniment
- éventuellement un wrapper ``_start_X()`` qui crée le ``Thread`` et le démarre

Les workers sont lancés depuis ``app/bootstrap.py`` au démarrage du process,
soit directement, soit via les shims de rétro-compat dans station_web.py.
"""
