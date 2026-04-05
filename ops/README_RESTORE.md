# Restauration d’une sauvegarde `astroscan_safe_*.tar.gz`

1. Arrêter le service (fenêtre de maintenance) :
   ```bash
   sudo systemctl stop astroscan
   ```
2. Sauvegarder le répertoire actuel (copie de secours) :
   ```bash
   sudo cp -a /root/astro_scan /root/astro_scan.before_restore.$(date +%Y%m%d)
   ```
3. Extraire l’archive :
   ```bash
   sudo tar -xzf /root/astro_scan/backups/astroscan_safe_YYYYMMDDTHHMMSSZ.tar.gz -C /root
   ```
4. Vérifier permissions (propriétaire attendu : root pour cet environnement).
5. Redémarrer :
   ```bash
   sudo systemctl start astroscan
   sudo systemctl is-active astroscan
   curl -sS -I http://127.0.0.1:5003/health | head -3
   ```

**Note** : ne pas restaurer par-dessus un déploiement sans validation des migrations / données externes (TLE, bases SQLite hors archive).
