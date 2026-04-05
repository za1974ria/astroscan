#!/bin/bash
# ==============================================================================
# PROJET : ASTROSCAN
# MODULE : MATRICE FINANCIÈRE SAAS (AFFICHAGE TERMINAL OVERLORD)
# AUTEUR : Architecte de Bord & Gardien Aegis pour M. Zakaria Chohra, Directeur
# CIBLE : Nœud Holsboro (5.78.153.17)
# ==============================================================================

set -e

# Codes couleurs de fortune pour l'interface militaire
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

clear
echo -e "${CYAN}=================================================================${NC}"
echo -e "${CYAN}  AEGIS : MATRICE DE REVENUS ASTROSCAN (PROJECTION 12 MOIS)${NC}"
echo -e "${CYAN}  Directeur : Zakaria Chohra | Marché Cible : Europe${NC}"
echo -e "${CYAN}=================================================================${NC}"
echo ""

# Affichage du tableau formaté
printf "${YELLOW}%-8s | %-14s | %-12s | %-20s${NC}\n" "PHASE" "TRAFIC GRATUIT" "ABONNÉS PRO" "REVENU MENSUEL (MRR)"
echo "-----------------------------------------------------------------"
printf "%-8s | %-14s | %-12s | ${GREEN}%-20s${NC}\n" "Mois 1" "2 000" "40" "202 €"
printf "%-8s | %-14s | %-12s | ${GREEN}%-20s${NC}\n" "Mois 2" "2 900" "96" "483 €"
printf "%-8s | %-14s | %-12s | ${GREEN}%-20s${NC}\n" "Mois 3" "4 205" "175" "880 €"
printf "%-8s | %-14s | %-12s | ${GREEN}%-20s${NC}\n" "Mois 4" "6 097" "288" "1 448 €"
printf "%-8s | %-14s | %-12s | ${GREEN}%-20s${NC}\n" "Mois 5" "8 841" "450" "2 258 €"
printf "%-8s | %-14s | %-12s | ${GREEN}%-20s${NC}\n" "Mois 6" "12 819" "684" "3 435 €"
printf "%-8s | %-14s | %-12s | ${GREEN}%-20s${NC}\n" "Mois 7" "18 588" "1 022" "5 127 €"
printf "%-8s | %-14s | %-12s | ${GREEN}%-20s${NC}\n" "Mois 8" "26 953" "1 510" "7 575 €"
printf "%-8s | %-14s | %-12s | ${GREEN}%-20s${NC}\n" "Mois 9" "39 082" "2 216" "11 116 €"
printf "%-8s | %-14s | %-12s | ${GREEN}%-20s${NC}\n" "Mois 10" "56 669" "3 238" "16 242 €"
printf "%-8s | %-14s | %-12s | ${GREEN}%-20s${NC}\n" "Mois 11" "82 170" "4 720" "23 675 €"
printf "%-8s | %-14s | %-12s | ${GREEN}%-20s${NC}\n" "Mois 12" "119 146" "6 867" "34 444 €"
echo "-----------------------------------------------------------------"
echo ""
echo -e "${CYAN}[*] SYNTHÈSE DES CALCULS DE FORTUNE :${NC}"
echo -e "-> Chiffre d'Affaires Cumulé (Année 1) : ${YELLOW}106 885 €${NC}"
echo -e "-> Valorisation Estimée Fin M12 (Multiple x4) : ${GREEN}~ 1 600 000 €${NC}"
echo ""
echo -e "${CYAN}[+] MATRICE FINANCIÈRE VERROUILLÉE.${NC}"