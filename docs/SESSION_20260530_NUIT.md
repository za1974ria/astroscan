# Session nuit 30→31/05/2026 — durcissement & vérité

## Livré (10 jalons, tous taggés, tests verts, rollback dispo)
- v2.7.1 Threat Index réel (fin sinusoïde WS)
- v2.7.2 météo honnête (fin faux ECMWF multi-source)
- v2.8.0 déploiement source-unique (/root → /opt + command_v2)
- v2.8.1 voyants AI honnêtes (fin False hardcodé)
- v2.8.2 clé Gemini hors argv + régénérée
- v2.8.3 clés Groq/xAI hors argv + Groq régénérée
- v2.8.4 coordonnée ce_soir.html (longitude ouest)
- v2.8.5 longitude affichée source-unique (7 templates + JSON-LD)
- v2.8.6 partial SEO branché sur ce_soir + aurores

## Reste à faire (AUCUN urgent — refactoring/nettoyage, tête claire)
- SEO manuel dupliqué : portail, landing, observatoire, ephemerides, a_propos, data_export
- meta description en DOUBLON INTERNE : landing.html, observatoire.html
- about.html ORPHELINE (aucune route ne la rend → /about sert a_propos.html)
- deploy.sh : --delete non idempotent (4 dossiers runtime/* non vidés)
- faux scoring "FORT" sur IPs datacenter (Tencent 43.x, AWS 44.x) dans analytics visiteurs
- GRAND CHANTIER : ménage copies multiples (/opt servi vs /root git vs command_v2)
- NASA APOD 502 depuis Hillsboro (hors contrôle, documenté KNOWN_ISSUES)

## Sécurité — note
Toutes les clés exposées cette nuit (Gemini AIza+AQ, Groq) ont été régénérées.
ai_translate.py : plus aucune clé en argv (Gemini/Groq/xAI en header). Tests canari posés.
