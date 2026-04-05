import os, subprocess, json, urllib.request

print("--- [RADAR AEGIS : RECHERCHE DE CIBLES IRLANDAISES (IE)] ---")
cmd = "ssh -q root@5.78.153.17 \"awk '{print \\$1}' /var/log/nginx/access.log | sort | uniq -c | sort -nr\""

try:
    output = subprocess.check_output(cmd, shell=True).decode('utf-8').strip().split('\n')
    found = False
    print(f"{'REQUÊTES':<10} | {'ADRESSE IP':<16} | {'VILLE'}")
    print("-" * 50)
    for line in output:
        if not line: continue
        parts = line.split()
        if len(parts) >= 2:
            count, ip = parts[0], parts[1]
            try:
                req = urllib.request.Request(f"http://ip-api.com/json/{ip}?lang=fr")
                req.add_header('User-Agent', 'Aegis-Tracker/1.0')
                with urllib.request.urlopen(req, timeout=1) as response:
                    data = json.loads(response.read().decode())
                    if data.get('countryCode') == 'IE':
                        found = True
                        print(f"{count:<10} | {ip:<16} | {data.get('city', 'Inconnue')}")
            except: continue
    if not found: print("[RAPPORT] Aucune cible irlandaise (IE) détectée.")
except Exception as e: print(f"[ERREUR] Liaison échouée : {e}")
