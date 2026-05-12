"""
AstroScan-Chohra — Application Factory
Nouvelle architecture modulaire (migration progressive depuis station_web.py)
"""
import os
import logging
from flask import Flask

from app.services.env_guard import MIN_SECRET_KEY_LEN_PRODUCTION, validate_production_env

log = logging.getLogger(__name__)


def _resolve_secret_key(config_name: str) -> bytes:
    """Return SECRET_KEY: enforce env presence in production,
    fall back to ephemeral random in dev/test."""
    key = os.environ.get("SECRET_KEY", "")
    if config_name == "production":
        if not key or len(key) < MIN_SECRET_KEY_LEN_PRODUCTION:
            raise RuntimeError("SECRET_KEY")
        log.info("[CONFIG] SECRET_KEY loaded from env (len=%d)", len(key))
        return key.encode() if isinstance(key, str) else key
    if not key:
        log.warning("[CONFIG] SECRET_KEY missing in %s, using ephemeral os.urandom(32)", config_name)
        return os.urandom(32)
    return key.encode() if isinstance(key, str) else key


def create_app(config_name: str = "production") -> Flask:
    # Après chargement .env via import station_web (wsgi) — avant routes / Sentry.
    if config_name == "production":
        try:
            env_report = validate_production_env()
            log.info(
                "[ENV_GUARD] production OK; optional_missing=%s",
                env_report.get("optional_missing") or [],
            )
        except RuntimeError as exc:
            var = str(exc)
            log.error(
                "[ENV_GUARD] required variable missing or invalid: %s "
                "(see .env.example — value never logged)",
                var,
            )
            raise

    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), '..', 'templates'),
        static_folder=os.path.join(os.path.dirname(__file__), '..', 'static'),
    )

    app.config.update(
        SECRET_KEY=_resolve_secret_key(config_name),
        TESTING=os.environ.get("TESTING", "0") == "1",
        STATION=os.environ.get("STATION", "/root/astro_scan"),
        DB_PATH=os.environ.get("DB_PATH",
            "/root/astro_scan/data/archive_stellaire.db"),
        SUPPORTED_LANGS={"fr", "en"},
        DEFAULT_LANG="fr",
        TEMPLATES_AUTO_RELOAD=True,
        SEND_FILE_MAX_AGE_DEFAULT=0,
    )
    # Force Jinja to re-check template mtime on every render across workers.
    app.jinja_env.auto_reload = True

    _init_sentry(app)
    _init_sqlite_wal(app.config["DB_PATH"])
    _register_blueprints(app)
    _register_hooks(app)
    _register_i18n(app)
    _register_bootstrap(app)

    log.info("[AstroScan] Application factory initialisée — %s", config_name)
    return app


def _register_hooks(app: Flask) -> None:
    """Attache les 8 hooks app-level (PASS 24)."""
    from app.hooks import register_hooks
    register_hooks(app)


def _register_i18n(app: Flask) -> None:
    """PASS 30 — i18n app-level hooks (cookie renewal + template context)."""
    from app.blueprints.i18n import register_i18n_hooks
    register_i18n_hooks(app)


def _register_bootstrap(app: Flask) -> None:
    """Lance les threads de fond app-level (PASS 25.1)."""
    from app.bootstrap import start_background_threads
    start_background_threads()


def _init_sentry(app: Flask) -> None:
    dsn = os.environ.get("SENTRY_DSN", "")
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        sentry_sdk.init(
            dsn=dsn,
            integrations=[FlaskIntegration()],
            traces_sample_rate=0.1,
            environment=os.environ.get("FLASK_ENV", "production"),
            release="astroscan@2.0.0",
        )
        log.info("[SENTRY] Monitoring actif")
    except ImportError:
        log.warning("[SENTRY] sentry-sdk non installé")


def _init_sqlite_wal(db_path: str) -> None:
    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-20000")
        conn.execute("PRAGMA mmap_size=268435456")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.commit()
        conn.close()
        log.info("[SQLite] WAL mode activé sur %s", db_path)
    except Exception as e:
        log.warning("[SQLite] WAL échec: %s", e)


def _register_blueprints(app: Flask) -> None:
    """Enregistre les 21 blueprints actifs en prod (sync avec station_web.py L501+).

    Mise à jour PASS 16 (2026-05-03) : étendu de 6 → 21 BPs pour préparer
    la bascule create_app (PASS 17). Ordre = ordre de station_web.py.
    """
    # Import IDENTIQUE à station_web.py L468-L506 (sync ordre + chemin)
    from app.blueprints.seo.routes import seo_bp
    from app.blueprints.apod.routes import apod_bp
    from app.blueprints.sdr.routes import sdr_bp
    from app.blueprints.iss.routes import iss_bp
    from app.blueprints.i18n import bp as i18n_bp
    from app.blueprints.api import bp as api_bp
    from app.blueprints.pages import bp as pages_bp
    from app.blueprints.main import bp as main_bp
    from app.blueprints.system import bp as system_bp
    from app.blueprints.health import bp as health_bp
    from app.blueprints.analytics import bp as analytics_bp
    from app.blueprints.export import bp as export_bp, bp_global as export_global_bp
    from app.blueprints.cameras import bp as cameras_bp
    from app.blueprints.archive import bp as archive_bp
    from app.blueprints.weather import bp as weather_bp
    from app.blueprints.astro import bp as astro_bp
    from app.blueprints.feeds import bp as feeds_bp
    from app.blueprints.telescope import bp as telescope_bp
    from app.blueprints.ai import bp as ai_bp
    from app.blueprints.lab import bp as lab_bp
    from app.blueprints.research import bp as research_bp
    from app.blueprints.satellites import bp as satellites_bp
    from app.blueprints.nasa_proxy import bp as nasa_proxy_bp
    from app.blueprints.version import bp as version_bp
    from app.blueprints.ground_assets import ground_assets_bp
    from app.blueprints.scan_signal import scan_signal_bp
    from app.blueprints.flight_radar import flight_radar_bp
    from app.blueprints.hilal import bp as hilal_bp
    from app.blueprints.maintenance import bp as maintenance_bp

    app.register_blueprint(seo_bp)
    app.register_blueprint(apod_bp)
    app.register_blueprint(sdr_bp)
    app.register_blueprint(iss_bp)
    app.register_blueprint(i18n_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(system_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(export_bp)
    app.register_blueprint(export_global_bp)
    app.register_blueprint(cameras_bp)
    app.register_blueprint(archive_bp)
    app.register_blueprint(weather_bp)
    app.register_blueprint(astro_bp)
    app.register_blueprint(feeds_bp)
    app.register_blueprint(telescope_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(lab_bp)
    app.register_blueprint(research_bp)
    app.register_blueprint(satellites_bp)
    app.register_blueprint(nasa_proxy_bp)
    app.register_blueprint(version_bp)
    app.register_blueprint(ground_assets_bp)
    app.register_blueprint(scan_signal_bp)
    app.register_blueprint(flight_radar_bp)
    app.register_blueprint(hilal_bp)
    app.register_blueprint(maintenance_bp)
    log.info("[Blueprints] 30 blueprints + 8 hooks enregistrés (sync station_web.py + hilal + maintenance)")


def register_all_for_fallback(app: Flask) -> None:
    """Enregistre TOUS les blueprints + hooks sur une instance Flask externe.

    Conçu pour le mode FALLBACK de wsgi.py (ASTROSCAN_FORCE_MONOLITH=1
    ou create_app() failure). Permet à station_web.app de servir le site
    si la factory create_app() devient inutilisable (régression silencieuse,
    config manquante, etc.).

    Réutilise les fonctions internes _register_blueprints + _register_hooks
    pour garantir la SYNCHRONISATION avec le mode normal (single source
    of truth). Toute évolution future des BPs sera automatiquement propagée
    au mode fallback.

    Voir wsgi.py pour le mécanisme complet du strangler fig pattern.
    Voir PASS 25.5 (2026-05-08) pour la justification de cette restauration.

    Args:
        app: Instance Flask externe (typiquement station_web.app)
    """
    _register_blueprints(app)
    _register_hooks(app)
    log.info(
        "[fallback-safety] %d routes registered on external Flask app",
        len(list(app.url_map.iter_rules())),
    )
