#!/bin/bash
# ==============================================================================
# PROJET : ASTROSCAN
# MODULE : SIMULATEUR DE REVENUS ET VALORISATION (SAAS FINANCIAL ENGINE)
# AUTEUR : Architecte de Bord & Gardien Aegis pour M. Zakaria Chohra, Directeur
# CIBLE : Nœud Holsboro (5.78.153.17)
# ==============================================================================

set -e

WORK_DIR="/root/astro_scan/finance"
PYTHON_SIMULATOR="$WORK_DIR/saas_simulator.py"
REPORT_OUTPUT="$WORK_DIR/astroscan_financial_projection_12M.csv"

echo "================================================================="
echo "  AEGIS : INITIATION DES CALCULS DE FORTUNE (PROJECTIONS FINANCIÈRES)"
echo "  Directeur : Zakaria Chohra"
echo "================================================================="

mkdir -p "$WORK_DIR"

echo "[*] Forgeage du moteur de simulation Python..."

cat << 'EOF' > "$PYTHON_SIMULATOR"
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import sys

# === PARAMÈTRES DE LA SIMULATION (Ajustables par l'Overlord) ===
PRICE_PER_MONTH = 4.99       # Prix de l'abonnement PRO en Euros
CONVERSION_RATE = 0.02       # 2% des utilisateurs gratuits deviennent payants
CHURN_RATE = 0.05            # 5% d'abonnés annulent chaque mois
ADS_REVENUE_PER_1K = 1.50    # Revenu publicitaire pour 1000 utilisateurs gratuits
INITIAL_USERS = 2000         # Utilisateurs au Mois 1
GROWTH_RATE = 1.45           # Croissance mensuelle du trafic (45% par mois)

months = []
users = INITIAL_USERS
subscribers = 0
total_annual_revenue = 0

print(f"\n[*] Lancement de la simulation sur 12 mois (Prix: {PRICE_PER_MONTH}€ / Conv: {CONVERSION_RATE*100}%)")

for month in range(1, 13):
    # Calcul des nouveaux abonnés
    new_subscribers = users * CONVERSION_RATE
    
    # Calcul des désabonnements (Churn)
    lost_subscribers = subscribers * CHURN_RATE
    
    # Mise à jour du pool d'abonnés
    subscribers = subscribers + new_subscribers - lost_subscribers
    
    # Calculs de fortune (Revenus)
    revenue_subs = subscribers * PRICE_PER_MONTH
    revenue_ads = (users / 1000) * ADS_REVENUE_PER_1K
    mrr = revenue_subs + revenue_ads
    
    total_annual_revenue += mrr
    
    months.append({
        "Mois": f"Mois {month}",
        "Trafic_Total": int(users),
        "Abonnes_Pro": int(subscribers),
        "Revenus_Pub_EUR": round(revenue_ads, 2),
        "Revenus_Abo_EUR": round(revenue_subs, 2),
        "MRR_Total_EUR": round(mrr, 2)
    })
    
    # Croissance pour le mois suivant
    users = users * GROWTH_RATE

# Évaluation finale sur le marché Européen
arr = months[-1]["MRR_Total_EUR"] * 12
valuation = arr * 4.5 # Multiple moyen SaaS

# Génération du rapport CSV
csv_file = sys.argv[1]
with open(csv_file, mode='w', newline='', encoding='utf-8') as file:
    writer = csv.DictWriter(file, fieldnames=["Mois", "Trafic_Total", "Abonnes_Pro", "Revenus_Pub_EUR", "Revenus_Abo_EUR", "MRR_Total_EUR"])
    writer.writeheader()
    writer.writerows(months)

print("-" * 60)
print(f"-> Chiffre d'affaires cumulé Année 1 : {round(total_annual_revenue, 2)} €")
print(f"-> MRR (Revenu Mensuel) au Mois 12   : {round(months[-1]['MRR_Total_EUR'], 2)} €")
print(f"-> VALORISATION EUROPÉENNE ESTIMÉE AU MOIS 12 : ~ {round(valuation, 2)} €")
print("-" * 60)
EOF

chmod +x "$PYTHON_SIMULATOR"

echo "[*] Exécution du moteur de calcul..."
python3 "$PYTHON_SIMULATOR" "$REPORT_OUTPUT"

echo "[+] RAPPORT FINANCIER GÉNÉRÉ AVEC SUCCÈS."
echo "-> Le détail mois par mois a été verrouillé dans : $REPORT_OUTPUT"