"""Blueprint SEO — sitemap.xml, robots.txt."""
from flask import Blueprint, Response, current_app
from datetime import datetime, timezone

bp = Blueprint("seo", __name__)

SITEMAP_URLS = [
    ("https://astroscan.space/",               "1.0", "daily"),
    ("https://astroscan.space/portail",         "0.9", "daily"),
    ("https://astroscan.space/en/portail",      "0.8", "daily"),
    ("https://astroscan.space/observatoire",    "0.9", "daily"),
    ("https://astroscan.space/ce_soir",         "0.9", "daily"),
    ("https://astroscan.space/meteo-spatiale",  "0.8", "hourly"),
    ("https://astroscan.space/aurores",         "0.8", "daily"),
    ("https://astroscan.space/orbital-map",     "0.8", "always"),
    ("https://astroscan.space/apod",            "0.8", "daily"),
    ("https://astroscan.space/iss-tracker",     "0.7", "always"),
    ("https://astroscan.space/sondes",          "0.7", "daily"),
    ("https://astroscan.space/galerie",         "0.7", "daily"),
    ("https://astroscan.space/data",            "0.8", "daily"),
    ("https://astroscan.space/api/docs",        "0.7", "weekly"),
    ("https://astroscan.space/a-propos",        "0.6", "monthly"),
    ("https://astroscan.space/about",           "0.6", "monthly"),
    ("https://astroscan.space/guide-stellaire", "0.6", "weekly"),
    ("https://astroscan.space/oracle-cosmique", "0.6", "weekly"),
]


@bp.route("/sitemap.xml")
def sitemap_xml():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc, pri, freq in SITEMAP_URLS:
        parts.append(
            f"  <url>\n"
            f"    <loc>{loc}</loc>\n"
            f"    <lastmod>{today}</lastmod>\n"
            f"    <changefreq>{freq}</changefreq>\n"
            f"    <priority>{pri}</priority>\n"
            f"  </url>"
        )
    parts.append("</urlset>")
    return Response("\n".join(parts), mimetype="application/xml")


@bp.route("/robots.txt")
def robots_txt():
    return current_app.send_static_file("robots.txt")
