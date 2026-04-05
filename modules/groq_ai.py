# -*- coding: utf-8 -*-
"""
Groq AI integration for AstroScan.
Loads GROQ_API_KEY from environment (via python-dotenv/.env) and exposes a safe client helper.
"""
import os

_groq_client = None


def get_groq_client():
  """
  Return a singleton Groq client, or None if GROQ_API_KEY is missing.
  Callers should handle the None case gracefully.
  """
  global _groq_client
  if _groq_client is not None:
      return _groq_client
  api_key = os.getenv("GROQ_API_KEY") or os.getenv("GROK_API_KEY")
  if not api_key:
      return None
  try:
      from groq import Groq
  except Exception:
      return None
  try:
      _groq_client = Groq(api_key=api_key)
  except Exception:
      _groq_client = None
  return _groq_client


def run_text_analysis(prompt, model="llama-3.1-70b-versatile"):
  """
  Simple helper to run a text completion on Groq.
  Returns a dict with either {'ok': True, 'text': ...} or {'ok': False, 'error': ...}.
  """
  client = get_groq_client()
  if client is None:
      return {"ok": False, "error": "GROQ_API_KEY not configured or client unavailable."}
  try:
      resp = client.chat.completions.create(
          model=model,
          messages=[{"role": "user", "content": prompt}],
          temperature=0.3,
      )
      text = ""
      if resp and resp.choices:
          text = resp.choices[0].message.content or ""
      return {"ok": True, "text": text}
  except Exception as e:
      return {"ok": False, "error": str(e)}

