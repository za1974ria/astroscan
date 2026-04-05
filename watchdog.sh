#!/bin/bash
# AstroScan-Chohra — watchdog (vérifie et relance si mort)
LOG=/var/log/astroscan-watchdog.log
URL="http://localhost:5003/health"

while true; do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 $URL)
    if [ "$STATUS" != "200" ]; then
        echo "[$(date)] ALERTE: service down (HTTP $STATUS) — relance..." >> $LOG
        systemctl restart astroscan.service
        sleep 10
        STATUS2=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 $URL)
        echo "[$(date)] Apres relance: HTTP $STATUS2" >> $LOG
    else
        echo "[$(date)] OK: HTTP $STATUS" >> $LOG
    fi
    sleep 300
done
