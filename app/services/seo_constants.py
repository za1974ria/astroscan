"""
app.services.seo_constants — Façade unique SEO + i18n.

Extraction Sprint A · Tranche #1 (2026-05-28) depuis station_web.py.
Le monolithe legacy conserve un shim de compatibilité qui re-importe ces
symboles depuis ce module — toute modification doit se faire ici.

Symboles exposés :
    SEO_HOME_TITLE          (str)     — re-export depuis app.config
    SEO_HOME_DESCRIPTION    (str)     — re-export depuis app.config
    SUPPORTED_LANGS         (set)     — re-export depuis app.config (frozenset)
    PAGE_PATHS              (set)     — pages HTML comptabilisées comme visite
    _SESSION_TIME_SNIPPET   (str)     — script HTML injecté par hooks.after_request
    get_user_lang           (callable) — résolution langue cookie > header > 'fr'
"""
from __future__ import annotations

from flask import request

from app.config import (
    SEO_HOME_TITLE,
    SEO_HOME_DESCRIPTION,
    SUPPORTED_LANGS,
)

# Pages HTML soumises au compteur de visites (anti-spam API/static).
PAGE_PATHS = {
    '/', '/landing', '/portail', '/dashboard', '/overlord_live', '/galerie', '/observatoire',
    '/vision', '/ce_soir', '/telescopes', '/mission-control', '/globe',
    '/telemetrie-sondes', '/sky-camera', '/orbital-radio', '/iss-tracker',
    '/visiteurs-live', '/guide-stellaire', '/oracle-cosmique', '/meteo-spatiale',
    '/aurores', '/orbital-map',
}

# Script injecté en after_request HTML : mesure le temps passé par page
# et l'envoie via sendBeacon('/track-time') au unload.
_SESSION_TIME_SNIPPET = (
    '<!-- astroscan-session-time --><script>'
    '(function(){var t0=Date.now(),sent=!1;'
    "function getSid(){var c=document.cookie.split(';');for(var i=0;i<c.length;i++){"
    "var p=c[i].trim();if(p.indexOf('astroscan_sid=')===0)return decodeURIComponent(p.slice(14));}"
    "return '';}function send(){if(sent)return;sent=!0;var d=Math.max(0,Math.round((Date.now()-t0)/1000)),"
    "body=JSON.stringify({session_id:getSid(),path:window.location.pathname||'/',duration:d});"
    "try{if(navigator.sendBeacon){var b=new Blob([body],{type:'application/json'});"
    "if(navigator.sendBeacon('/track-time',b))return;}}catch(e){}"
    "try{fetch('/track-time',{method:'POST',headers:{'Content-Type':'application/json'},body:body,keepalive:!0});}catch(e){}}"
    "window.addEventListener('pagehide',send);window.addEventListener('beforeunload',send);})();"
    "</script>"
)


def get_user_lang() -> str:
    """Priorité : cookie > Accept-Language header > défaut 'fr'."""
    lang = request.cookies.get("lang", "")
    if lang in SUPPORTED_LANGS:
        return lang
    accept = request.headers.get("Accept-Language", "")
    return "en" if accept.lower().startswith("en") else "fr"


__all__ = [
    "SEO_HOME_TITLE",
    "SEO_HOME_DESCRIPTION",
    "SUPPORTED_LANGS",
    "PAGE_PATHS",
    "_SESSION_TIME_SNIPPET",
    "get_user_lang",
]
