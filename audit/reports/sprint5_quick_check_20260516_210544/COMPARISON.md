# Sprint 5 — Quick check Lighthouse BP

⚠️ ROUTES PYTHON EN ATTENTE DE RESTART : /api/solar/image, /api/apod/proxy-image
   Le service astroscan tourne en root et zakaria n'a pas sudo NOPASSWD.
   Exécuter manuellement : sudo systemctl restart astroscan.service

| Module | URL | AVANT | APRÈS | Δ BP | 100% ? |
|--------|-----|-------|-------|------|--------|
| a_propos | `/a-propos` | 100/95/77/100 | 100/95/100/100 | 23 | - |
| europe_live | `/europe-live` | 97/93/96/100 | 97/93/96/100 | 0 | - |
| meteo_spatiale | `/meteo-spatiale` | 100/100/96/100 | 100/100/96/100 | 0 | - |
| methodology | `/methodology` | 100/93/96/100 | 100/93/100/100 | 4 | - |
| sky_camera | `/sky-camera` | 100/100/96/100 | 100/100/96/100 | 0 | - |
| lab | `/lab` | 98/82/96/100 | 98/82/96/100 | 0 | - |
| mission_control | `/mission-control` | 81/92/96/100 | 81/92/96/100 | 0 | - |
