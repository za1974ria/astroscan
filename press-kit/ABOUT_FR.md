# À propos d'ASTRO-SCAN (Français)

## Résumé en une ligne

**ASTRO-SCAN est un observatoire spatial gratuit, en données ouvertes et en temps réel, conçu en solo par un scientifique indépendant à Tlemcen, Algérie — qui rend accessibles les flux NASA, NOAA, ESA et JPL à tout navigateur web.**

## Description courte (50 mots)

ASTRO-SCAN est un observatoire astronomique en temps réel qui agrège les données NASA, NOAA, ESA, JPL, CelesTrak et Harvard MicroObservatory dans un tableau de bord bilingue (FR/EN), sans publicité. Conçu en solo par Zakaria Chohra à Tlemcen, Algérie, il sert la communauté scientifique et éducative mondiale, sans paywall ni traceurs.

## Description moyenne (150 mots)

ASTRO-SCAN est un observatoire web indépendant qui rend l'intelligence orbitale en temps réel et la science spatiale accessibles à tout internaute. La plateforme agrège les flux de la NASA (APOD, NEO, DONKI, SkyView, rovers martiens), du NOAA Space Weather Prediction Center, de l'ESA, du JPL Horizons (Voyager, Parker Solar Probe, BepiColombo), de CelesTrak, du Harvard MicroObservatory et de N2YO dans une interface unifiée bilingue (français/anglais).

Conçu en solo par **Zakaria Chohra** à Tlemcen, Algérie, ASTRO-SCAN repose sur une infrastructure Flask 3.1 durcie (25 blueprints, 266 routes, 13 services) avec Gunicorn, Nginx et SSL Let's Encrypt. La plateforme n'expose aucune clé d'API tierce côté navigateur, intègre un chatbot IA AEGIS pour les questions astronomiques (Claude, Gemini, Groq, Grok), et fonctionne comme un tracker ISS complet avec prédictions de passage SGP4.

ASTRO-SCAN est libre sous licence CC BY-NC-SA 4.0 pour l'éducation, la recherche et la médiation scientifique. En mai 2026 : **2 195+ visiteurs · 49+ pays touchés**.

## Description longue (300 mots)

**ASTRO-SCAN** est un observatoire spatial indépendant en temps réel, conçu et exploité en solo par **Zakaria Chohra** depuis Tlemcen, Algérie (34,87°N · 1,32°O). La mission est simple : transformer le flot de données scientifiques ouvertes publiées quotidiennement par la NASA, le NOAA, l'ESA, le JPL et leurs partenaires en une interface unifiée, sans publicité, bilingue, accessible à tous — étudiant, chercheur, journaliste, scientifique citoyen — sans inscription, paywall ni traceurs.

**Ce qu'il fait.** ASTRO-SCAN suit la Station Spatiale Internationale en direct (propagation SGP4/TLE), prédit les passages visibles pour tout observateur, surveille la météo spatiale (NOAA SWPC : indice Kp, tempêtes géomagnétiques, prévisions d'aurores), diffuse l'image astronomique du jour de la NASA avec commentaire français traduit par IA, intègre les flux JWST et Hubble, calcule la position des missions interplanétaires (Voyager 1/2, Parker Solar Probe, BepiColombo) via JPL Horizons, indexe 1 500+ observations d'anomalies, et opère un panneau radio SDR avec 8 canaux audio NASA. Un chatbot IA AEGIS répond aux questions astronomiques en français et anglais, en orchestrant Anthropic Claude, Google Gemini, Groq et xAI Grok avec basculement automatique.

**Comment c'est construit.** Stack de production : Flask 3.1 (pattern factory, 25 blueprints, 266 routes, 13 modules de service), Gunicorn (4 workers préchargés), proxy inverse Nginx, SSL Let's Encrypt, SQLite + WAL, cache Redis optionnel, observabilité Sentry, logs structurés, circuit breakers par API. La base de code a fait l'objet d'une migration en 19 passes depuis un monolithe de 12 159 lignes vers une architecture blueprint+factory, exécutée sans interruption de service.

**Pourquoi c'est important.** ASTRO-SCAN est l'un des rares observatoires spatiaux opérant depuis l'Afrique du Nord, avec une interface bilingue français/anglais (sitemap hreflang, persistance par cookie) servant explicitement les communautés francophones et arabophones. Licence CC BY-NC-SA 4.0 — libre pour l'éducation, la recherche et la médiation — et ouvert aux collaborations scientifiques avec les universités, agences et observatoires mondiaux.

**En mai 2026 : 2 195+ visiteurs uniques · 49+ pays touchés · 8 sources de données externes · 266 routes · zéro publicité.**
