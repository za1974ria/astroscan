#!/usr/bin/env python3
"""Pre-traduction des rapports EN→FR en batch. Une fois. Lance: python3 pretranslate.py"""
import sqlite3
import requests
import os
import time
import re

try:
    from dotenv import load_dotenv
    load_dotenv("/root/astro_scan/.env")
except Exception:
    pass

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY_BACKUP") or ""
DB = "/root/astro_scan/data/archive_stellaire.db"

conn = sqlite3.connect(DB)
cur = conn.cursor()
try:
    cur.execute("SELECT id, analyse_gemini FROM observations WHERE (rapport_fr IS NULL OR rapport_fr='') AND analyse_gemini IS NOT NULL AND LENGTH(analyse_gemini)>30 ORDER BY id DESC LIMIT 500")
    rows = cur.fetchall()
except Exception:
    rows = []

print(len(rows), "rapports à traduire...")
n = 0
for obs_id, text in rows:
    if not text or not re.search(r"\\b(the|and|with|this|from|pictured|viewed)\\b", text, re.I):
        cur.execute("UPDATE observations SET rapport_fr=? WHERE id=?", (text or "", obs_id))
        n += 1
        continue
    try:
        r = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=" + API_KEY,
            json={"contents": [{"parts": [{"text": "Traduis en français naturel. UNIQUEMENT la traduction.\\n\\n" + (text[:1200] or "")}]}]},
            timeout=15,
        )
        if r.status_code != 200:
            time.sleep(2)
            continue
        j = r.json()
        tr = (j.get("candidates") or [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
        cur.execute("UPDATE observations SET rapport_fr=? WHERE id=?", (tr or text, obs_id))
        n += 1
        if n % 10 == 0:
            conn.commit()
            print(" ", n, "/", len(rows))
        time.sleep(0.5)
    except Exception as e:
        print(" Erreur #%s: %s" % (obs_id, e))
        time.sleep(2)
conn.commit()
conn.close()
print("\\n✅ %s rapports traduits et mis en cache." % n)
