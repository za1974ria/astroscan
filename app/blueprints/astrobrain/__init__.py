"""AstroBrain blueprint package.

Exposes ``bp`` (Flask Blueprint) so app/__init__.py can register it with
url_prefix='/api/astrobrain'. Routes are localhost-only via the @require_localhost
decorator in security.py.

Provider: OpenAI GPT-5 (coexists with the Anthropic/Groq stack in app/blueprints/ai/).
"""
from app.blueprints.astrobrain.routes import bp

__all__ = ["bp"]
