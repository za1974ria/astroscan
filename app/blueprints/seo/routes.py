"""Blueprint SEO — robots.txt, sitemap.xml, google verify.

Extrait de station_web.py. Aucune dépendance sur les globals du monolithe.
"""
from datetime import datetime, timezone
from flask import Blueprint, Response

seo_bp = Blueprint('seo', __name__)


@seo_bp.route('/robots.txt')
def robots_txt():
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        "Disallow: /api/\n"
        "Disallow: /admin\n"
        "Disallow: /static/\n"
        "Disallow: /analytics\n"
        "Disallow: /overlord_live\n"
        "Disallow: /visiteurs-live\n"
        "Disallow: /dashboard\n"
        "Disallow: /observatory/status\n"
        "Disallow: /lab/\n"
        "Disallow: /demo\n"
        "Disallow: /health\n"
        "Disallow: /ready\n"
        "Disallow: /selftest\n"
        "Disallow: /status\n"
        "Disallow: /static/img/raw/\n"
        "\n"
        "Sitemap: https://astroscan.space/sitemap.xml\n"
    )
    return Response(content, mimetype='text/plain')


def _alt_url(loc: str, lang: str) -> str:
    """Return URL for the requested language. EN reached via ?lang=en
    (cookie-persisted thereafter by the i18n blueprint)."""
    if lang == "fr":
        return loc
    sep = "&" if "?" in loc else "?"
    return f"{loc}{sep}lang={lang}"


@seo_bp.route('/sitemap.xml')
def sitemap_xml():
    """Sitemap SEO dynamique — lastmod = date du jour.

    PASS 30 — multilingual: each URL declares xhtml:link rel=alternate
    hreflang fr/en + x-default for international SEO."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    URLS = [
        ("https://astroscan.space/",               "1.0", "daily"),
        ("https://astroscan.space/portail",         "1.0", "daily"),
        ("https://astroscan.space/observatoire",    "0.9", "weekly"),
        ("https://astroscan.space/ephemerides",     "0.9", "hourly"),
        ("https://astroscan.space/ce_soir",         "0.9", "hourly"),
        ("https://astroscan.space/space-weather",   "0.8", "hourly"),
        ("https://astroscan.space/orbital-map",     "0.8", "always"),
        ("https://astroscan.space/mission-control", "0.8", "always"),
        ("https://astroscan.space/apod",            "0.8", "daily"),
        ("https://astroscan.space/nasa-apod",       "0.9", "daily"),
        ("https://astroscan.space/data",            "0.8", "daily"),
        ("https://astroscan.space/telescope",       "0.7", "daily"),
        ("https://astroscan.space/sondes",          "0.7", "daily"),
        ("https://astroscan.space/iss-tracker",     "0.7", "always"),
        ("https://astroscan.space/aladin",          "0.7", "daily"),
        ("https://astroscan.space/meteo-spatiale",  "0.7", "hourly"),
        ("https://astroscan.space/aurores",         "0.7", "daily"),
        ("https://astroscan.space/galerie",         "0.6", "weekly"),
        ("https://astroscan.space/vision",          "0.6", "monthly"),
        ("https://astroscan.space/guide-stellaire", "0.6", "weekly"),
        ("https://astroscan.space/oracle-cosmique", "0.6", "weekly"),
        ("https://astroscan.space/telescopes",      "0.6", "weekly"),
        ("https://astroscan.space/scientific",      "0.5", "weekly"),
        ("https://astroscan.space/lab",             "0.5", "weekly"),
        ("https://astroscan.space/research-center", "0.5", "weekly"),
        ("https://astroscan.space/a-propos",        "0.5", "monthly"),
        ("https://astroscan.space/about",           "0.5", "monthly"),
        ("https://astroscan.space/research",        "0.4", "monthly"),
    ]
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
        ' xmlns:xhtml="http://www.w3.org/1999/xhtml">',
    ]
    for loc, pri, freq in URLS:
        fr_url = _alt_url(loc, 'fr')
        en_url = _alt_url(loc, 'en')
        parts.append(
            f'  <url>\n    <loc>{fr_url}</loc>\n    <lastmod>{today}</lastmod>'
            f'\n    <changefreq>{freq}</changefreq>\n    <priority>{pri}</priority>'
            f'\n    <xhtml:link rel="alternate" hreflang="fr" href="{fr_url}"/>'
            f'\n    <xhtml:link rel="alternate" hreflang="en" href="{en_url}"/>'
            f'\n    <xhtml:link rel="alternate" hreflang="x-default" href="{fr_url}"/>'
            f'\n  </url>'
        )
    parts.append('</urlset>')
    return Response('\n'.join(parts), mimetype='application/xml')


@seo_bp.route('/google<token>.html')
def google_verify(token):
    """Route de vérification Google Search Console."""
    return f'google-site-verification: google{token}.html', 200
