"""Blueprint API — documentation Swagger + spec OpenAPI."""
from flask import Blueprint, render_template, jsonify

bp = Blueprint("api_docs", __name__)

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
            "url": "https://astroscan.space/a-propos",
        },
        "license": {
            "name": "Open Data — CC BY 4.0",
            "url": "https://astroscan.space/data",
        },
    },
    "servers": [{"url": "https://astroscan.space", "description": "Production"}],
    "tags": [
        {"name": "ISS", "description": "Station Spatiale Internationale"},
        {"name": "Astronomie", "description": "Éphémérides et données astronomiques"},
        {"name": "NASA", "description": "Données officielles NASA"},
        {"name": "Météo Spatiale", "description": "NOAA, Kp-index, aurores"},
        {"name": "Export", "description": "Téléchargement CSV/JSON — CC BY 4.0"},
        {"name": "Analytics", "description": "Statistiques plateforme"},
        {"name": "Système", "description": "Health checks"},
    ],
    "paths": {
        "/api/ephemerides/tlemcen": {"get": {
            "summary": "Éphémérides Tlemcen",
            "tags": ["Astronomie"],
            "responses": {"200": {"description": "JSON éphémérides complètes"}},
        }},
        "/api/iss": {"get": {
            "summary": "Position ISS temps réel",
            "tags": ["ISS"],
            "responses": {"200": {"description": "JSON position ISS"}},
        }},
        "/api/apod": {"get": {
            "summary": "APOD NASA du jour",
            "tags": ["NASA"],
            "responses": {"200": {"description": "JSON APOD + traduction FR"}},
        }},
        "/api/meteo-spatiale": {"get": {
            "summary": "Météo spatiale NOAA",
            "tags": ["Météo Spatiale"],
            "responses": {"200": {"description": "JSON Kp, alertes, vent solaire"}},
        }},
        "/api/visitors/snapshot": {"get": {
            "summary": "Statistiques visiteurs",
            "tags": ["Analytics"],
            "responses": {"200": {"description": "JSON stats visiteurs"}},
        }},
        "/api/export/visitors.csv": {"get": {
            "summary": "Export visiteurs CSV",
            "tags": ["Export"],
            "responses": {"200": {"description": "CSV anonymisé"}},
        }},
        "/api/export/visitors.json": {"get": {
            "summary": "Export visiteurs JSON",
            "tags": ["Export"],
            "responses": {"200": {"description": "JSON avec metadata CC BY 4.0"}},
        }},
        "/api/export/observations.json": {"get": {
            "summary": "Export observations stellaires",
            "tags": ["Export"],
            "responses": {"200": {"description": "500 observations avec analyse IA"}},
        }},
        "/api/export/ephemerides.json": {"get": {
            "summary": "Export éphémérides JSON",
            "tags": ["Export"],
            "responses": {"200": {"description": "JSON scientifique avec metadata"}},
        }},
        "/api/health": {"get": {
            "summary": "Santé de l'API",
            "tags": ["Système"],
            "responses": {"200": {"description": "JSON health check"}},
        }},
    },
}


@bp.route("/api/docs")
def api_docs():
    return render_template("api_docs.html")


@bp.route("/api/spec.json")
def api_spec_json():
    return jsonify(API_SPEC)
