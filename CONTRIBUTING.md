# Contributing to AstroScan

Thanks for your interest in contributing. AstroScan is a small,
focused project; the guidelines below keep the codebase coherent
across passes.

## Development Setup

1. **Python 3.12** is the supported runtime.
2. Create a virtual environment and install dependencies:

   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Copy the environment template and fill in real values:

   ```bash
   cp .env.example .env
   chmod 600 .env
   # Edit .env — at minimum set SECRET_KEY (see .env.example for the
   # one-liner that generates a strong random key).
   ```

4. Boot the application factory locally:

   ```bash
   export FLASK_ENV=development
   export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
   python3 -m flask --app app:create_app run --port 5003
   ```

   In production the entry point is `station_web.py` driven by Gunicorn
   under the `astroscan` systemd unit on the Hetzner host.

## Pull Request Guidelines

- **One feature per PR.** Bug fixes, refactors and new features should
  not be bundled. Each PR should be reviewable in one sitting.
- **Run `python3 -m py_compile` on every touched `.py` file before
  committing.** CI will reject syntax errors but local compilation
  catches them faster.
- **Avoid editing `station_web.py` directly.** New routes, hooks and
  services should land in `app/blueprints/`, `app/hooks.py`,
  `app/bootstrap.py` or `app/services/`. The monolith is a thin shim
  whose only role is to keep legacy imports alive during the migration.
- **Backward compatibility:** never break an existing public API contract.
  When a contract needs to change, add a new endpoint and deprecate the
  old one over a release cycle.
- **Backups before risky edits.** When modifying long files (templates,
  `app/blueprints/health/__init__.py`, etc.) create a sibling
  `.bak_pre_pass<N>` first. These are covered by `.gitignore *.bak_*`
  and never committed.
- **Atomic commits, descriptive messages.** Pass-style messages
  (`PASS NN — <subject>`) are encouraged. Reference any audit, ticket
  or finding that motivated the change.

## Code Style

- **Python**: PEP 8, 4-space indent, lines ≤ 100 cols where reasonable.
  Imports grouped stdlib / third-party / local. No bare `except:` —
  catch the narrowest exception type that makes sense.
- **Flask blueprints**: keep one blueprint per concern; expose `bp` as
  the module-level name; `url_prefix` belongs on the `Blueprint(...)`
  call, not on each route.
- **Jinja2 templates**: autoescape is **on**. Never bypass it without
  reading the surrounding context (and never for user-controlled strings).
  When a template needs raw HTML, use `|safe` deliberately and
  document why.
- **SQL**: prefer parameterised queries. When duplicate-merging values
  (e.g. country names), normalize at SELECT time via `CASE WHEN`
  rather than mutating the table.
- **Logging**: `log = logging.getLogger(__name__)` at module scope.
  Use `log.info("[Component] message %s", value)` — string formatting
  goes through the logger.

## What NOT to Commit

- `.env` and any `*.env.*` variants other than `.env.example`.
- Any `*.bak_*` backups (covered by `.gitignore`).
- Database files (`*.db`, `*.db-wal`, `*.db-shm`).
- Logs, screenshots, generated reports unless they are an intentional
  artefact of a PASS (e.g. `SECURITY_AUDIT_2026-05-04.md`).

## Useful Commands

```bash
# Compile every touched .py file before commit
python3 -m py_compile $(git diff --cached --name-only --diff-filter=AM | grep '\.py$')

# Build the factory and count routes/blueprints
python3 -c "
import os; os.environ['SECRET_KEY']='dev-min-16-chars-test'
from app import create_app
a = create_app('production')
print('routes=', len(list(a.url_map.iter_rules())), 'bps=', len(a.blueprints))
"
```

## Questions

For non-security questions, open a GitHub issue. For security findings,
follow [`SECURITY.md`](SECURITY.md).
