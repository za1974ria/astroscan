"""
AstroScan-Chohra — WSGI Production Entry Point
Standard Gunicorn entry: gunicorn wsgi:app

This file unifies the application entry point.
The actual Flask application is defined in station_web.py.

Production deployment:
    gunicorn wsgi:app --workers 4 --threads 4 --bind 127.0.0.1:5003

Future migration target: app/__init__.py (create_app factory)
Currently: thin alias to station_web:app for production stability.
"""
from station_web import app

if __name__ == "__main__":
    raise SystemExit(
        "Lancer via: gunicorn wsgi:app --workers 4 --threads 4 --bind 0.0.0.0:5003"
    )
