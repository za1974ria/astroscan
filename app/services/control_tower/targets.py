"""AstroScan Control Tower — Targets registry (Phase 3A).

53 lamps grouped into 7 semantic categories:
  edge, core_api, module_page, system, data, freshness, worker

Each target dict supports the following keys (all optional unless noted):
  id              str   required — stable unique id
  label           str   required — display name
  type            str   required — one of:
                          http, json_sanity, dns, tls,
                          system_metric, process,
                          path_readable, sqlite_readable
  category        str   required — semantic category (see above)
  timeout         int|float — probe timeout (seconds)
  critical        bool  — critical=True → measurement failure becomes RED
  optional        bool  — optional=True → 404/403/missing/timeout becomes GREY

HTTP / json_sanity:
  url             str
  json_keys       list[str]  — required JSON keys (json_sanity only)
  min_bytes       int        — minimum response body size

DNS:
  host            str

TLS:
  host            str
  port            int

system_metric:
  metric          str — one of: cpu, ram, disk, inode, load
  path            str — for disk/inode
  warn_pct        int — % threshold for ORANGE
  crit_pct        int — % threshold for RED

process:
  process_name    str — exact /proc/PID/comm value

path_readable:
  path            str
  must_be_dir     bool
  max_age_s       int — ORANGE if mtime older than this

sqlite_readable:
  path            str
"""

TARGETS = [
    # ── EDGE / NETWORK (1–7) ─────────────────────────────────────────
    {"id": "edge_health", "label": "Edge /health", "type": "http",
     "url": "https://astroscan.space/health", "timeout": 5,
     "category": "edge", "critical": True},

    {"id": "edge_portail", "label": "Edge /portail", "type": "http",
     "url": "https://astroscan.space/portail", "timeout": 6,
     "category": "edge", "critical": True, "min_bytes": 2000},

    {"id": "edge_maintenance", "label": "Edge /maintenance", "type": "http",
     "url": "https://astroscan.space/maintenance", "timeout": 6,
     "category": "edge", "critical": False, "min_bytes": 1000},

    {"id": "edge_sentinel", "label": "Edge /sentinel", "type": "http",
     "url": "https://astroscan.space/sentinel", "timeout": 6,
     "category": "edge", "critical": False, "min_bytes": 1000},

    {"id": "edge_dns", "label": "DNS astroscan.space", "type": "dns",
     "host": "astroscan.space", "timeout": 4,
     "category": "edge", "critical": True},

    {"id": "edge_tls", "label": "TLS cert", "type": "tls",
     "host": "astroscan.space", "port": 443, "timeout": 6,
     "category": "edge", "critical": True},

    {"id": "edge_root", "label": "Nginx public root", "type": "http",
     "url": "https://astroscan.space/", "timeout": 5,
     "category": "edge", "critical": True, "min_bytes": 4000},

    # ── CORE API (8–17) ──────────────────────────────────────────────
    {"id": "api_system_status", "label": "/api/system/status", "type": "http",
     "url": "https://astroscan.space/api/system/status", "timeout": 5,
     "category": "core_api", "critical": True},

    {"id": "api_system_diagnostics", "label": "/api/system/diagnostics", "type": "http",
     "url": "https://astroscan.space/api/system/diagnostics", "timeout": 6,
     "category": "core_api", "critical": True},

    {"id": "api_aegis_status", "label": "/api/aegis/status", "type": "http",
     "url": "https://astroscan.space/api/aegis/status", "timeout": 5,
     "category": "core_api", "critical": True},

    {"id": "api_sentinel_health", "label": "/api/sentinel/health", "type": "http",
     "url": "https://astroscan.space/api/sentinel/health", "timeout": 5,
     "category": "core_api", "critical": True},

    {"id": "api_sentinel_metrics", "label": "/api/sentinel/metrics", "type": "http",
     "url": "https://astroscan.space/api/sentinel/metrics", "timeout": 5,
     "category": "core_api", "critical": False},

    {"id": "api_sdr_status", "label": "/api/sdr/status", "type": "http",
     "url": "https://astroscan.space/api/sdr/status", "timeout": 5,
     "category": "core_api", "critical": False},

    {"id": "api_tle_status", "label": "/api/tle/status", "type": "http",
     "url": "https://astroscan.space/api/tle/status", "timeout": 5,
     "category": "core_api", "critical": True},

    {"id": "api_visitors_stats", "label": "/api/visitors/stats", "type": "http",
     "url": "https://astroscan.space/api/visitors/stats", "timeout": 5,
     "category": "core_api", "critical": False},

    {"id": "api_iss", "label": "/api/iss", "type": "http",
     "url": "https://astroscan.space/api/iss", "timeout": 4,
     "category": "core_api", "critical": False},

    {"id": "api_health", "label": "/api/health", "type": "http",
     "url": "https://astroscan.space/api/health", "timeout": 5,
     "category": "core_api", "critical": True},

    # ── MODULE PAGES (18–24) ─────────────────────────────────────────
    {"id": "page_observatoire", "label": "/observatoire", "type": "http",
     "url": "https://astroscan.space/observatoire", "timeout": 7,
     "category": "module_page", "critical": False, "min_bytes": 2000},

    {"id": "page_orbital_map", "label": "/orbital-map", "type": "http",
     "url": "https://astroscan.space/orbital-map", "timeout": 7,
     "category": "module_page", "critical": False, "min_bytes": 2000},

    {"id": "page_flight_radar", "label": "/flight-radar", "type": "http",
     "url": "https://astroscan.space/flight-radar", "timeout": 7,
     "category": "module_page", "critical": False, "optional": True,
     "min_bytes": 1000},

    {"id": "page_ground_assets", "label": "/ground-assets", "type": "http",
     "url": "https://astroscan.space/ground-assets", "timeout": 7,
     "category": "module_page", "critical": False, "min_bytes": 1000},

    {"id": "page_research_center", "label": "/research-center", "type": "http",
     "url": "https://astroscan.space/research-center", "timeout": 7,
     "category": "module_page", "critical": False, "optional": True,
     "min_bytes": 1000},

    {"id": "page_science_archive", "label": "/science-archive", "type": "http",
     "url": "https://astroscan.space/science-archive", "timeout": 7,
     "category": "module_page", "critical": False, "optional": True,
     "min_bytes": 1000},

    {"id": "page_digital_lab", "label": "/digital-lab", "type": "http",
     "url": "https://astroscan.space/digital-lab", "timeout": 7,
     "category": "module_page", "critical": False, "optional": True,
     "min_bytes": 1000},

    # ── SYSTEM READ-ONLY (25–32) ─────────────────────────────────────
    {"id": "sys_cpu", "label": "CPU usage", "type": "system_metric",
     "metric": "cpu", "warn_pct": 75, "crit_pct": 90, "timeout": 2,
     "category": "system", "critical": True},

    {"id": "sys_ram", "label": "RAM usage", "type": "system_metric",
     "metric": "ram", "warn_pct": 80, "crit_pct": 90, "timeout": 2,
     "category": "system", "critical": True},

    {"id": "sys_disk_root", "label": "Disk /", "type": "system_metric",
     "metric": "disk", "path": "/", "warn_pct": 80, "crit_pct": 90,
     "timeout": 2, "category": "system", "critical": True},

    {"id": "sys_disk_opt", "label": "Disk /opt", "type": "system_metric",
     "metric": "disk", "path": "/opt", "warn_pct": 80, "crit_pct": 90,
     "timeout": 2, "category": "system", "critical": True},

    {"id": "sys_loadavg", "label": "Load average", "type": "system_metric",
     "metric": "load", "timeout": 2,
     "category": "system", "critical": False},

    {"id": "sys_inode_root", "label": "Inodes /", "type": "system_metric",
     "metric": "inode", "path": "/", "warn_pct": 75, "crit_pct": 90,
     "timeout": 2, "category": "system", "critical": True},

    {"id": "proc_gunicorn", "label": "Process gunicorn", "type": "process",
     "process_name": "gunicorn", "timeout": 2,
     "category": "system", "critical": True},

    {"id": "proc_nginx", "label": "Process nginx", "type": "process",
     "process_name": "nginx", "timeout": 2,
     "category": "system", "critical": True},

    # ── DATA / STORAGE READ-ONLY (33–38) ─────────────────────────────
    {"id": "data_dir", "label": "Data dir /opt/astroscan/data",
     "type": "path_readable", "path": "/opt/astroscan/data",
     "must_be_dir": True, "timeout": 2,
     "category": "data", "critical": True},

    {"id": "data_archive_db", "label": "archive_stellaire.db",
     "type": "sqlite_readable",
     "path": "/opt/astroscan/data/archive_stellaire.db", "timeout": 3,
     "category": "data", "critical": False, "optional": True},

    {"id": "data_sentinel_store", "label": "Sentinel store module",
     "type": "path_readable",
     "path": "/opt/astroscan/app/blueprints/sentinel/store.py",
     "timeout": 2,
     "category": "data", "critical": False, "optional": True},

    {"id": "data_tle_cache", "label": "TLE cache freshness",
     "type": "path_readable",
     "path": "/opt/astroscan/data/tle_cache.json", "timeout": 2,
     "category": "data", "critical": False, "optional": True,
     "max_age_s": 86400},

    {"id": "data_visitors", "label": "Visitors data",
     "type": "sqlite_readable",
     "path": "/opt/astroscan/data/visitors.db", "timeout": 3,
     "category": "data", "critical": False, "optional": True},

    {"id": "data_logs_dir", "label": "Logs directory",
     "type": "path_readable", "path": "/opt/astroscan/logs",
     "must_be_dir": True, "timeout": 2,
     "category": "data", "critical": False, "optional": True},

    # ── FRESHNESS / DOMAIN SANITY (39–49) ────────────────────────────
    {"id": "fresh_iss", "label": "ISS payload sanity", "type": "json_sanity",
     "url": "https://astroscan.space/api/iss", "timeout": 4,
     "category": "freshness", "critical": False, "optional": True},

    {"id": "fresh_tle", "label": "TLE payload sanity", "type": "json_sanity",
     "url": "https://astroscan.space/api/tle/status", "timeout": 5,
     "category": "freshness", "critical": True},

    {"id": "fresh_sentinel_metrics", "label": "Sentinel metrics payload",
     "type": "json_sanity",
     "url": "https://astroscan.space/api/sentinel/metrics", "timeout": 5,
     "category": "freshness", "critical": False},

    {"id": "fresh_aegis", "label": "AEGIS payload sanity",
     "type": "json_sanity",
     "url": "https://astroscan.space/api/aegis/status", "timeout": 5,
     "category": "freshness", "critical": False},

    {"id": "fresh_sdr", "label": "SDR payload sanity", "type": "json_sanity",
     "url": "https://astroscan.space/api/sdr/status", "timeout": 5,
     "category": "freshness", "critical": False},

    {"id": "fresh_diagnostics", "label": "Diagnostics payload sanity",
     "type": "json_sanity",
     "url": "https://astroscan.space/api/system/diagnostics", "timeout": 6,
     "category": "freshness", "critical": False},

    {"id": "fresh_visitors", "label": "Visitors payload sanity",
     "type": "json_sanity",
     "url": "https://astroscan.space/api/visitors/stats", "timeout": 5,
     "category": "freshness", "critical": False},

    {"id": "fresh_weather", "label": "Weather endpoint", "type": "http",
     "url": "https://astroscan.space/api/weather", "timeout": 5,
     "category": "freshness", "critical": False, "optional": True},

    {"id": "fresh_aurora", "label": "Space weather (aurora)", "type": "http",
     "url": "https://astroscan.space/api/space-weather", "timeout": 5,
     "category": "freshness", "critical": False, "optional": True},

    {"id": "fresh_flight_radar", "label": "Flight radar health", "type": "http",
     "url": "https://astroscan.space/api/flight_radar/health", "timeout": 5,
     "category": "freshness", "critical": False, "optional": True},

    {"id": "fresh_ground_assets", "label": "Ground assets health",
     "type": "http",
     "url": "https://astroscan.space/api/ground_assets/health", "timeout": 5,
     "category": "freshness", "critical": False, "optional": True},

    # ── WORKERS / AGENTS READ-ONLY (50–53) ───────────────────────────
    {"id": "worker_guardian", "label": "Guardian status", "type": "http",
     "url": "https://astroscan.space/api/guardian/status", "timeout": 5,
     "category": "worker", "critical": False, "optional": True},

    {"id": "worker_astrobrain", "label": "AstroBrain status", "type": "http",
     "url": "https://astroscan.space/api/astrobrain/status", "timeout": 5,
     "category": "worker", "critical": False, "optional": True},

    {"id": "worker_scan_signal", "label": "Scan-signal health", "type": "http",
     "url": "https://astroscan.space/api/scan-signal/health", "timeout": 5,
     "category": "worker", "critical": False, "optional": True},

    {"id": "worker_telescope", "label": "Telescope status", "type": "http",
     "url": "https://astroscan.space/api/telescope/status", "timeout": 5,
     "category": "worker", "critical": False, "optional": True},
]

# Hard invariant — fail loud at import time if anyone breaks the count.
assert len(TARGETS) == 53, f"TARGETS must hold 53 lamps, got {len(TARGETS)}"
