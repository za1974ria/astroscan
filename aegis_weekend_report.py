import os
import subprocess
import json
import urllib.request

def generate_04_05_human_report():
    NODE_IP = "5.78.153.17"
    print("=============================================================")
    print("--- [AEGIS : MATRICE DE VISITES HUMAINES (04 & 05 AVRIL)] ---")
    print(f"Cible : {NODE_IP} (Nœud USA)")
    print("Filtre : Trafic strictement humain (Chrome/Safari/Mozilla)")
    print("=============================================================\n")

    # Commande SSH : Isoler les dates du 04 et 05 Avril, filtrer les navigateurs, extraire Date et IP
    cmd = f"ssh -q root@{NODE_IP} \"awk '(\\$4 ~ /04\\/Apr\\/2026|05\\/Apr\\/2026/) && (\\$0 ~ /Mozilla|Chrome|Safari|Edge/) {{print substr(\\$4, 2, 11), \\$1}}' /var/log/nginx/access.log | sort | uniq -c | sort -nr | head -n 25\""
    
    try:
        print("[*] Synchronisation avec le Gardien Aegis. Analyse temporelle et GeoIP en cours...\n")
        output = subprocess.check_output(cmd, shell=True).decode('utf-8').strip().split('\n')
        
        print(f"{'DATE':<12} | {'REQUÊTES':<10} | {'ADRESSE IP':<16} | {'PAYS':<22} | {'VILLE'}")
        print("-" * 85)

        for line in output:
            if not line: continue
            parts = line.split()
            if len(parts) >= 3:
                count = parts[0]
                date = parts[1]
                ip = parts[2]
                
                # Traduction Géographique
                try:
                    req = urllib.request.Request(f"http://ip-api.com/json/{ip}?lang=fr")
                    req.add_header('User-Agent', 'Aegis-Tracker/2.0')
                    with urllib.request.urlopen(req, timeout=3) as response:
                        data = json.loads(response.read().decode())
                        country = data.get('country', 'Inconnu')
                        city = data.get('city', 'Inconnue')
                        
                        # Identification automatique de l'État-Major (Vos IPs locales)
                        if ip in ["105.235.139.2", "41.101.239.33", "105.235.137.163"]:
                            country = f"ADMIN ({country})"
                            
                        print(f"{date:<12} | {count:<10} | {ip:<16} | {country:<22} | {city}")
                except Exception:
                    print(f"{date:<12} | {count:<10} | {ip:<16} | {'Erreur GeoIP':<22} | -")

        print("-" * 85)
        print("[OK] Rapport généré et certifié par le Gardien Aegis.")

    except subprocess.CalledProcessError as e:
        print(f"\n[ERREUR CRITIQUE] Échec de la liaison SSH : {e}")

if __name__ == "__main__":
    generate_04_05_human_report()