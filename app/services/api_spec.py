"""
app.services.api_spec — OpenAPI spec legacy (extraite de station_web.py).

Sprint A · Tranche #2 (2026-05-28) — Extraction pure depuis le monolithe.

NOTE : cette spec (~16 endpoints) est issue de station_web.py. Le blueprint
app/blueprints/api/__init__.py possède sa propre version locale plus récente
(~11 endpoints) qui sert /api/spec.json en production. Aucune consolidation
n'est faite à ce stade — cf. Sprint A bis pour réconciliation.

Le shim de compatibilité dans station_web.py re-importe API_SPEC depuis ce
module pour préserver les éventuels lazy-imports legacy.
"""
from __future__ import annotations

API_SPEC = {
    "openapi": "3.0.0",
    "info": {
        "title": "AstroScan-Chohra API",
        "version": "2.0.0",
        "description": (
            "API publique de la station d'observation spatiale AstroScan-Chohra. "
            "Données en temps réel : ISS, météo spatiale, éphémérides Tlemcen, APOD NASA. "
            "Usage scientifique et éducatif libre."
        ),
        "contact": {
            "name": "Zakaria Chohra",
            "email": "zakaria.chohra@gmail.com",
            "url": "https://astroscan.space/a-propos"
        },
        "license": {
            "name": "Open Data — Usage scientifique et éducatif",
            "url": "https://astroscan.space/a-propos"
        }
    },
    "servers": [{"url": "https://astroscan.space", "description": "Production"}],
    "paths": {
        "/api/ephemerides/tlemcen": {
            "get": {
                "summary": "Éphémérides Tlemcen",
                "description": "Données astronomiques en temps réel depuis Tlemcen (34.88°N, 1.32°E, 800m). Soleil (lever/coucher), Lune (phase, illumination), planètes visibles, début/fin nuit astronomique. Cache 5 min.",
                "tags": ["Astronomie"],
                "responses": {"200": {"description": "JSON éphémérides complètes"}}
            }
        },
        "/api/iss": {
            "get": {
                "summary": "Position ISS en temps réel",
                "description": "Coordonnées GPS de la Station Spatiale Internationale, altitude, vitesse, pays survolé.",
                "tags": ["ISS"],
                "responses": {"200": {"description": "JSON position ISS"}}
            }
        },
        "/api/passages-iss": {
            "get": {
                "summary": "Passages ISS sur Tlemcen",
                "description": "Prochains passages visibles de l'ISS au-dessus de Tlemcen avec azimut, élévation max et durée.",
                "tags": ["ISS"],
                "parameters": [
                    {"name": "lat", "in": "query", "schema": {"type": "number"}, "example": 34.88},
                    {"name": "lon", "in": "query", "schema": {"type": "number"}, "example": 1.32}
                ],
                "responses": {"200": {"description": "JSON passages ISS"}}
            }
        },
        "/api/apod": {
            "get": {
                "summary": "APOD NASA du jour",
                "description": "Image astronomique du jour NASA avec titre, explication et traduction française automatique.",
                "tags": ["NASA"],
                "responses": {"200": {"description": "JSON APOD"}}
            }
        },
        "/api/meteo-spatiale": {
            "get": {
                "summary": "Météo spatiale NOAA",
                "description": "Indice Kp, alertes géomagnétiques, vent solaire, probabilité aurores boréales.",
                "tags": ["Météo Spatiale"],
                "responses": {"200": {"description": "JSON météo spatiale"}}
            }
        },
        "/api/aurore": {
            "get": {
                "summary": "Données aurores boréales",
                "description": "Niveau d'activité aurorale, prévisions Kp 24h, visibilité par latitude.",
                "tags": ["Météo Spatiale"],
                "responses": {"200": {"description": "JSON aurores"}}
            }
        },
        "/api/tonight": {
            "get": {
                "summary": "Objets observables ce soir",
                "description": "Objets du ciel profond visibles depuis Tlemcen cette nuit — calculés avec astropy. Inclut phase lunaire.",
                "tags": ["Astronomie"],
                "responses": {"200": {"description": "JSON objets de la nuit"}}
            }
        },
        "/api/moon": {
            "get": {
                "summary": "Phase lunaire actuelle",
                "description": "Phase, illumination (%), jour du cycle lunaire.",
                "tags": ["Astronomie"],
                "responses": {"200": {"description": "JSON phase lune"}}
            }
        },
        "/api/visitors/snapshot": {
            "get": {
                "summary": "Statistiques visiteurs",
                "description": "Nombre total de visiteurs, visiteurs actifs, pays distincts, top pays, humains vs robots.",
                "tags": ["Analytics"],
                "parameters": [
                    {"name": "exclude_my_ip", "in": "query", "schema": {"type": "string", "default": "1"}, "description": "Exclure l'IP du serveur"}
                ],
                "responses": {"200": {"description": "JSON stats visiteurs"}}
            }
        },
        "/api/health": {
            "get": {
                "summary": "Santé de l'API",
                "description": "Statut de tous les modules : TLE, APOD, ISS, SDR, base de données.",
                "tags": ["Système"],
                "responses": {"200": {"description": "JSON health check"}}
            }
        },
        "/api/export/visitors.csv": {
            "get": {
                "summary": "Export visiteurs CSV",
                "description": "Statistiques visiteurs par pays au format CSV. Données anonymisées — aucune donnée personnelle.",
                "tags": ["Export"],
                "responses": {"200": {"description": "CSV file — country, country_code, visits, first_visit, last_visit"}}
            }
        },
        "/api/export/visitors.json": {
            "get": {
                "summary": "Export visiteurs JSON",
                "description": "Statistiques visiteurs par pays avec métadonnées de citation scientifique (CC BY 4.0).",
                "tags": ["Export"],
                "responses": {"200": {"description": "JSON avec metadata de citation"}}
            }
        },
        "/api/export/ephemerides.json": {
            "get": {
                "summary": "Export éphémérides JSON",
                "description": "Éphémérides Tlemcen complètes avec métadonnées scientifiques (coordonnées, licence, computation).",
                "tags": ["Export"],
                "responses": {"200": {"description": "JSON scientifique avec metadata"}}
            }
        },
        "/api/export/observations.json": {
            "get": {
                "summary": "Export observations stellaires",
                "description": "Archive 1500+ observations avec analyse IA (objets détectés, anomalies, score confiance).",
                "tags": ["Export"],
                "responses": {"200": {"description": "JSON observations archive"}}
            }
        },
        "/api/export/apod-history.json": {
            "get": {
                "summary": "Export APOD + traductions FR",
                "description": "Historique NASA APOD avec traductions françaises (CC BY 4.0).",
                "tags": ["Export"],
                "responses": {"200": {"description": "JSON APOD archive"}}
            }
        },
        "/sitemap.xml": {
            "get": {
                "summary": "Sitemap SEO dynamique",
                "description": "Sitemap XML avec toutes les pages indexables, lastmod = date du jour.",
                "tags": ["SEO"],
                "responses": {"200": {"description": "XML sitemap"}}
            }
        }
    },
    "tags": [
        {"name": "ISS", "description": "Station Spatiale Internationale"},
        {"name": "Astronomie", "description": "Éphémérides et données astronomiques"},
        {"name": "NASA", "description": "Données officielles NASA"},
        {"name": "Météo Spatiale", "description": "NOAA, Kp-index, aurores boréales"},
        {"name": "Analytics", "description": "Statistiques plateforme"},
        {"name": "Export", "description": "Téléchargement données CSV/JSON — CC BY 4.0"},
        {"name": "Système", "description": "Health checks et statut"},
        {"name": "SEO", "description": "Référencement"}
    ]
}

__all__ = ["API_SPEC"]
