#!/usr/bin/env python3
import json,datetime,requests,os
OUT="/root/astro_scan/data/shield_status.json"
os.makedirs(os.path.dirname(OUT),exist_ok=True)
try:
    r=requests.get("https://api.open-meteo.com/v1/forecast?latitude=34.87&longitude=1.32&current=uv_index,direct_radiation,cloud_cover,is_day&timezone=Africa%2FAlgiers",timeout=8)
    c=r.json().get("current",{})
    uv=c.get("uv_index",0) or 0; rad=c.get("direct_radiation",0) or 0; is_day=c.get("is_day",0)
    if not is_day: status,risk,reason="inactive","none","Nuit — mode observation"
    elif uv>=7 or rad>=400: status,risk,reason="active","high",f"UV={uv:.1f} — PROTECTION ACTIVEE"
    elif uv>=3: status,risk,reason="caution","medium",f"UV={uv:.1f} — surveillance"
    else: status,risk,reason="inactive","low",f"UV={uv:.1f} — OK"
    json.dump({"status":status,"risk":risk,"reason":reason,"uv_index":round(uv,2),"is_day":bool(is_day),"updated_at":datetime.datetime.now().isoformat(),"source":"OpenMeteo live"},open(OUT,"w"),indent=2)
    print(f"[shield] {status} — {reason}")
except Exception as e: print(f"[shield] Erreur: {e}")
