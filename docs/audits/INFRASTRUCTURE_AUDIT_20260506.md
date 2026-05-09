# AUDIT INFRASTRUCTURE — 6 mai 2026, 01h11 UTC

## État actuel
- Service astroscan: actif, uptime 23min (post-restart adsb.lol)
- Disque: 45% utilisé (64/150 GB)
- Flight Radar: 1767+ avions live (adsb.lol Tier 3)
- Vessel Tracker: 600+ navires (AISStream singleton)

## Anomalies non-critiques détectées (à traiter à froid)

### 1. Backup quotidien cassé depuis 3 mai
- Script `/root/astro_scan/backup_daily.sh` ABSENT
- Cron `claude_user` fait toujours référence à ce script
- Dernière erreur: 2026-05-03 04:05:07
- Impact: pas de backup auto depuis 3 jours
- Mitigation: backups manuels timestampés sur tous fichiers critiques

### 2. Compte claude_user legacy
- UID 1003, dans le groupe sudo
- Date de création: ancienne migration AutoScan
- Status: à évaluer (garder vs supprimer)

### 3. Script monitor.sh absent
- Référencé probablement dans un cron mais script disparu
- À investiguer: `crontab -l` de tous les users

## Plan demain (à froid)
1. Décider: recréer backup_daily.sh OU migrer vers solution moderne
2. Audit complet crontabs (tous les users)
3. Décision claude_user (cleanup vs garder)
4. Vérifier cohérence /etc/cron.d/

## Pas urgent
Aucun risque immédiat. Système stable, sauvegardes manuelles en place.
