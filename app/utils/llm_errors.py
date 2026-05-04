"""Centralized LLM API error handling — PASS 31.5.

Wraps external LLM calls (Anthropic, Groq, Gemini, OpenAI) with proper error
handling that logs full details server-side but returns clean, bilingual,
user-friendly messages to the frontend.

The bug this module fixes: when an LLM provider returns an error such as
"Your credit balance is too low to access the Anthropic API. ...request_id:
req_xxx", route handlers were forwarding that string verbatim to visitors,
exposing billing status, internal request IDs, and the provider identity.

Public API:
    friendly_message(err, lang=None)       -> str
    classify_error(err)                    -> str (one of the kinds below)
    llm_error_response(err, provider=..., http_status=503) -> (Flask response, status)
"""
from __future__ import annotations

import logging
from typing import Tuple, Union

from flask import jsonify, request, has_request_context

log = logging.getLogger(__name__)


def _get_lang() -> str:
    """Resolve current language from request context — fallback 'fr'."""
    if not has_request_context():
        return 'fr'
    try:
        lang = (request.args.get('lang') or
                request.cookies.get('lang') or
                'fr')
        return lang if lang in ('fr', 'en') else 'fr'
    except Exception:
        return 'fr'


# User-facing messages keyed by (kind, lang). 5 categories cover all observed
# upstream failures from Anthropic / Groq / Gemini / OpenAI.
FRIENDLY_MESSAGES = {
    'fr': {
        'unavailable': "Le service IA est temporairement indisponible. Merci de réessayer dans quelques instants.",
        'rate_limit': "Le service IA est très sollicité actuellement. Merci de réessayer dans une minute.",
        'invalid_input': "La requête n'a pas pu être traitée. Vérifiez votre saisie et réessayez.",
        'timeout': "Le service IA met trop de temps à répondre. Merci de réessayer.",
        'generic': "Une erreur inattendue est survenue. Notre équipe a été notifiée.",
    },
    'en': {
        'unavailable': "The AI service is temporarily unavailable. Please try again shortly.",
        'rate_limit': "The AI service is currently busy. Please try again in a minute.",
        'invalid_input': "The request could not be processed. Please check your input and try again.",
        'timeout': "The AI service is taking too long to respond. Please try again.",
        'generic': "An unexpected error occurred. Our team has been notified.",
    },
}


def classify_error(err: Union[Exception, str, None]) -> str:
    """Map an exception or raw error string to a friendly-message key.

    Returns one of: 'unavailable', 'rate_limit', 'invalid_input', 'timeout', 'generic'.
    Heuristic-based — checks exception class name and string content.
    """
    if err is None:
        return 'generic'
    if isinstance(err, Exception):
        cls = type(err).__name__.lower()
        msg = str(err).lower()
    else:
        cls = ''
        msg = str(err).lower()

    # Quota / billing / credit (the original observed bug)
    if any(k in msg for k in ('credit balance', 'quota', 'billing', 'insufficient_quota', 'payment')):
        return 'unavailable'
    # Rate limit / 429
    if any(k in msg for k in ('rate limit', 'too many requests', '429')) or 'ratelimit' in cls:
        return 'rate_limit'
    # Timeout
    if 'timeout' in msg or 'timeout' in cls or 'timedout' in cls:
        return 'timeout'
    # Bad input / 400 (excluding billing — already caught above)
    if '400' in msg or 'invalid_request' in msg or 'bad request' in msg:
        return 'invalid_input'
    # 401 / 403 / auth
    if any(k in msg for k in ('401', '403', 'unauthorized', 'forbidden', 'invalid api key', 'authentication')):
        return 'unavailable'
    # 5xx upstream
    if any(k in msg for k in ('500', '502', '503', '504', 'internal server error', 'service unavailable')):
        return 'unavailable'
    return 'generic'


def friendly_message(err: Union[Exception, str, None], lang: str = None) -> str:
    """Return the bilingual user-facing message for an error. Never raises."""
    kind = classify_error(err)
    if lang not in ('fr', 'en'):
        lang = _get_lang()
    return FRIENDLY_MESSAGES.get(lang, FRIENDLY_MESSAGES['fr']).get(
        kind, FRIENDLY_MESSAGES['fr']['generic']
    )


def llm_error_response(
    err: Union[Exception, str],
    *,
    provider: str = 'AI',
    http_status: int = 503,
) -> Tuple:
    """Return a Flask jsonify response for an LLM call failure.

    Logs the full error (with provider context) at ERROR level for debugging.
    Returns a clean bilingual message to the caller. Never exposes raw details.

    Usage in a route handler:
        try:
            result = call_anthropic(...)
        except Exception as e:
            return llm_error_response(e, provider='Anthropic')
    """
    kind = classify_error(err)
    msg = friendly_message(err)
    raw = str(err)[:500] if err is not None else ''
    log.error(
        '[llm_error] provider=%s kind=%s exc_type=%s raw=%s',
        provider, kind, type(err).__name__ if isinstance(err, Exception) else 'str', raw,
        exc_info=isinstance(err, Exception),
    )
    return jsonify({
        'ok': False,
        'error': msg,
        'service_status': 'unavailable' if kind in ('unavailable', 'timeout', 'rate_limit') else 'error',
    }), http_status
