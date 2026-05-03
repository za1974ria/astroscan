# REPORT — Next Steps Analysis

**Author**: Strategic technical assessment for Zakaria Chohra, Director, ORBITAL-CHOHRA Observatory.
**Date**: 2026-05-03 — 22:30 (Tlemcen, Algérie).
**Context**: Post-PASS-21. ASTRO-SCAN production-ready. SneakerBot v2 pipeline live, no paying customer. Decision needed: what to launch tomorrow morning?

---

## 0. Executive Summary

**TL;DR — pour décider en 60 secondes**

| Question | Réponse |
|---|---|
| Demain matin, première action ? | **Envoyer 3 emails outreach (ESA Education, UNAWE, IAU). 90 minutes.** |
| Cette semaine, focus principal ? | **Security hardening ASTRO-SCAN (1j) + outreach Algérie (1-2j) + analyse funnel SneakerBot (1j).** |
| À éviter ce mois-ci ? | **Phase 3 architecture (Redis/Prometheus) et tests E2E supplémentaires. Gold-plating.** |
| Le plus gros risque ? | **Disperser. 6 pistes c'est trop pour single director — choisir 2-3 et finir.** |

**Recommandation finale — résumée :**

1. **Demain matin (90 min)** : 3 emails outreach (PISTE 1, démarrage, low-cost)
2. **Demain après-midi + jour 2 (1j)** : Security hardening systemd (PISTE 6, foundational)
3. **Jour 3-4 (1.5j)** : Outreach Université Tlemcen + CRAAG (PISTE 2)
4. **Jour 5 (0.5j)** : Audit funnel SneakerBot — où décrochent les utilisateurs ?
5. **Jour 6-7** : Tampon, premières réponses outreach, itération

**Ce qui est volontairement exclu de la semaine** : PISTE 3 (architecture Phase 3) et PISTE 5 (tests E2E supplémentaires). Voir §4.4 pour la justification.

---

## 1. Contexte & contraintes

### 1.1 État opérationnel — 03/05/2026 22:25

**ASTRO-SCAN / ORBITAL-CHOHRA**

| Indicateur | Valeur | Statut |
|---|---|---|
| Production URL | https://astroscan.space | LIVE |
| Architecture | Flask 3.1 + factory `create_app()` | post-PASS-18 stable |
| Routes | 262 | servies par 21 BPs |
| Services modules | 13 (`app/services/`) + 8 (`services/`) | extraction terminée |
| Lignes monolithe | 5 466 (depuis 11 918 — −54 %) | cleanup PASS 19 OK |
| Tests pytest | 51 passing / 0 failing / 85 skipped (env-bound) | baseline solide |
| CI/CD | GitHub Actions configuré (Python 3.11/3.12) | prêt |
| Documentation | README + ARCHITECTURE + DEPLOYMENT + tests/README | internationale-ready |
| Tags Git permanents | 7 (80pct, 95pct, 97pct, bascule-ok, cleanup-ok, docs-complete, …) | rollback toujours possible |
| Audience | 2 100+ visiteurs / 47 pays | trafic organique modeste mais international |
| Sources externes | 8/8 opérationnelles (NASA, NOAA, ESA partners, JPL, CelesTrak, Harvard, AMSAT, IAU) | aucun blocage |
| Sentry | actif, DSN configuré | observabilité OK |
| Branche actuelle | `migration/phase-2c` | sync avec origin |

**SneakerBot v2**

| Indicateur | Valeur | Statut |
|---|---|---|
| URL | sneakerbot.shop | LIVE |
| Pipeline technique | opérationnel | OK |
| Customers payants | **0** | bloquant business |
| Trial accounts | 4 | conversion 0/4 actuellement |
| Awin / Tradedoubler | scrapers créés, clés API en attente | bloqué externe |
| Marketing TikTok | actif depuis 13/04/2026 (20 jours) | 0 conversion paying |
| Premier prix cible | 29 €/mois | non atteint |

### 1.2 Contraintes structurelles

**Bandwidth opérationnelle** — Single director (Zakaria Chohra). Pas d'équipe. Toute heure passée sur une piste est non-disponible pour les autres. Sur 6 pistes ouvertes, en réalité 2-3 peuvent avancer en parallèle, pas plus.

**Géographie — Tlemcen, Algérie** :
- Time zone Algérie (UTC+1) compatible Europe (réponses rapides ESA/CNES) mais désynchro avec NASA Ames / JPL (UTC-7/-8) — décalage 8-9 h.
- Contraintes export tech vers certains partenaires US (ITAR / EAR) → ne pas cibler les programmes classifiés. Cibler **outreach scientifique public** uniquement (NASA Education, ESA Education, IAU public engagement, UNAWE).
- Visa/déplacement physique : pas un blocage immédiat (toutes les actions rétrogrades de cette semaine sont faisables remotely).
- Crédibilité institutionnelle locale : à construire — réseau CRAAG / Aboubekr Belkaïd / USTHB est le levier le plus rapide.

**Financier** : pas de budget marketing payant. Tout outreach est cold email + organic. SneakerBot conversion est aussi organic-only.

**Temporel** : "Demain matin" = 04/05/2026 ~08-09h locale Tlemcen. Le rapport vise les 7 jours suivants (jusqu'au 11/05/2026).

### 1.3 Ce qui n'est PAS encore fait / prouvé

À reconnaître honnêtement avant de planifier :

- **Aucun pitch international envoyé** à ce jour. Les contacts mentionnés dans README (UNAWE, IAU, ESA Education, Astronomers Without Borders) sont des cibles *à contacter*, pas des partenaires actuels. Aucune réponse, aucun rendez-vous.
- **Aucun test e2e contre la prod réelle** — 51 tests pytest, mais tous tournent localement contre `create_app("testing")`. Aucun monitoring synthétique externe (Pingdom / Datadog / UptimeRobot non configurés).
- **SneakerBot : zéro conversion payante** après 20 jours de marketing TikTok actif. Le bottleneck pourrait être : produit, tunnel, prix, audience, ou les quatre. Pas de funnel analytics actuellement (pas confirmé).
- **Sécurité** : service tourne en `User=root`, `.env` mode 0600 root-owned. Avant de pitcher NASA/ESA, ça doit être hardened. Non-bloquant fonctionnel, mais ça se voit dans une revue technique sérieuse.
- **Aucun NDA / accord de confidentialité prêt** pour démarches institutionnelles. Pas critique pour un pitch outreach (données publiques), mais à anticiper si réponse positive d'un partenariat.
- **Pas de versioning d'API publique** (`/api/v1/*` n'existe pas). Pour un pitch sérieux NASA/ESA, c'est un manque visible — mais c'est un *travail*, pas un blocage.

### 1.4 Ce qui est déjà acquis et utilisable demain

- 3 documents techniques (README EN, ARCHITECTURE FR, DEPLOYMENT EN) prêts à joindre à n'importe quel email.
- Production stable depuis le 03/05 (PASS 18 bascule). Healthcheck 200 sur 11 endpoints critiques.
- 7 tags git de restauration permanents — *aucun risque opérationnel* à laisser tourner.
- Suite de tests + CI/CD GitHub Actions — argument crédible pour audience technique.
- Audience organique 2 100+ visiteurs / 47 pays — preuve modeste mais réelle de pertinence.
- Domaine `astroscan.space` (OVH, propre) + DuckDNS de secours.

### 1.5 Calibration — projets comparables et taux de réponse réalistes

Pour fixer des attentes honnêtes sur les probabilités de succès des pistes outreach, voici une lecture rapide d'autres initiatives similaires dans la sphère astronomy public engagement / citizen science. Ces benchmarks ne sont **pas** des comparaisons de qualité — ce sont des points de référence pour calibrer le réalisme de "X mois pour obtenir Y".

| Initiative | Origine | Modèle | Ce qui a marché | Cycle "premier partenariat" |
|---|---|---|---|---|
| Universe Awareness (UNAWE) | NL, 2005 | Réseau éducation | Diffusion par universités relais | 12-18 mois pour adhésion régionale |
| Astronomers Without Borders | US, 2008 | Coordination événements | Global Astronomy Month | 6-12 mois pour activation locale |
| Stellarium (open source) | FR, 2001 | Logiciel public | Adoption planetariums | 24+ mois pour reconnaissance institutionnelle |
| Heavens-Above (Chris Peat) | UK | Solo developer, satellite tracking | Demande technique précise → bouche à oreille IAU | 36+ mois |
| AstroPixie (Amanda Bauer) | AU/US | Outreach personnalité | Visibility via blog + conférences | 12-24 mois |

**Lecture pour ORBITAL-CHOHRA** : en partant de zéro institutionnel (pas d'antériorité IAU, pas de publication papier, pas de chercheur affilié connu), la fourchette réaliste pour un **premier engagement formel** est de **6-12 mois**, avec **2-5 réponses qualifiées dans les 30-60 premiers jours** comme indicateur précoce de traction.

Inversement : ne **pas** attendre :
- Une réponse NASA Ames "publique" en 7 jours.
- Un partenariat ESA dans 30 jours.
- Une couverture média non-payée dans le mois.

Un signal positif réaliste à J+30 : ≥ 3 réponses, dont ≥ 1 demande de RDV, dont ≥ 1 introduction à un autre contact qualifié. Inférieur à ça → ne pas paniquer, intensifier mais sans changer de stratégie.

### 1.6 Carte des forces et faiblesses — vue brutale

**Forces** (utilisables demain, sans préparation) :
- Plateforme **opérationnelle** publiquement vérifiable (`curl https://astroscan.space/api/health` répond 200, n'importe qui peut tester).
- **Code source**, **architecture**, **déploiement** documentés dans le repo.
- **51 tests** + CI/CD = preuve d'hygiène d'ingénierie.
- **2 100+ visiteurs / 47 pays** = audience réelle, modeste mais distribuée.
- **Histoire migratoire propre** (PASS 1 → 21) = démonstration d'évolution maîtrisée d'un projet.
- **Localisation Tlemcen** = histoire forte (Global South, diaspora francophone, Maghreb).

**Faiblesses** (à reconnaître avant tout pitch sérieux) :
- **Aucun chercheur académique affilié** au projet.
- **Aucune publication scientifique** (pas même un *preprint* ArXiv).
- **Aucune mention publique** par une institution scientifique reconnue.
- **Single director** (à présenter comme "independent observatory" — pas "solo dev").
- **Service tournant en `User=root`** (à corriger PISTE 6 *avant* tout pitch).
- **Pas de SLA documenté** (pas de monitoring synthétique externe).
- **Pas de versioning d'API** (`/api/v1/*` n'existe pas — peut être un blocage pour intégration tiers).
- **Pas de citation source explicite** dans certaines réponses API (les destinataires de pitch institutionnel y seront sensibles).

**Implications stratégiques** :
- Pitcher la plateforme **sur ses forces réelles** (audience, fonctionnement, architecture, story Maghreb), pas sur ce qu'elle pourrait devenir.
- Reconnaître proactivement l'absence d'antériorité scientifique formelle dans les emails outreach — un destinataire informé le verra de toute façon ; mieux vaut le reconnaître comme contexte qu'attendre qu'on le souligne.
- Cibler en priorité les programmes **éducation / public engagement** où l'absence de publi n'est pas disqualifiante, et reporter les approches "scientific data partnership" à 12-24 mois.

---

## 2. Analyse des 6 pistes

### 2.1 PISTE 1 — Outreach scientifique international

**Cibles** : NASA Education / Public Engagement, ESA Education, JPL Outreach, CNES Education, UNAWE, IAU OAE (Office of Astronomy for Education), Astronomers Without Borders.

**À NE PAS cibler** au stade actuel : programmes classifiés (Airbus Defence & Space classifié, JPL mission ops, NASA Ames missions actives) — contraintes ITAR/EAR + crédibilité institutionnelle insuffisante. La porte d'entrée crédible est **éducation / public engagement**, pas opérations missions.

**Description précise**
Préparer un kit de 4 pièces : (a) email type EN court (200 mots) + email FR pour CNES/ESA/CRAAG, (b) one-pager PDF (architecture diagram + 5 use-cases + 3 metrics réelles), (c) screenshot reel 90 s de astroscan.space, (d) lien GitHub repo (privé, accès sur demande). Envoyer 3-5 emails ciblés par jour pendant 5 jours = 15-25 contacts de qualité. Suivi à J+7 et J+14.

**Effort réaliste**
- Préparation kit : 1-1.5 jour (one-pager + reel vidéo + emails types).
- Envoi initial : 30 min/jour × 5 j = 2.5 h.
- Suivis : 30 min × 2 vagues = 1 h.
- **Total** : ~2 jours étalés sur 2 semaines.

**Pré-requis**
- Adresses email institutionnelles cibles (la plupart publiques sur les sites des organisations).
- One-pager PDF (à créer — Canva ou Pages, 2 h).
- Screen recording du site (1 h, OBS suffit).
- README/ARCHITECTURE déjà prêts → joindre tels quels.
- Adresse email professionnelle (`director@astroscan.space` ou `zakaria.chohra@gmail.com` — la première donne plus de poids).

**Risques techniques / opérationnels**
- Faible. Le site doit rester up pendant la fenêtre de pitch (J+0 à J+30) — corollaire : faire le hardening (PISTE 6) **avant** d'envoyer pour limiter le risque d'incident embarrassant pendant qu'un destinataire visite le site.

**Risques business**
- Rejet poli ou silence : le scénario par défaut. Aucun coût direct.
- Réponse positive à mauvais moment : si un contact veut une démo et la prod tombe → impact réputationnel disproportionné. → **Conséquence** : hardening avant outreach, monitoring synthétique pendant.
- Engagement non-honorable : si un partenariat se concrétise et tu ne peux pas livrer ce qui a été pitché. → **Conséquence** : pitcher ce qui existe, pas ce qui pourrait exister.

**Probabilité de succès estimée** (baseline cold outreach scientifique) :
- Réponse de quelque type : **30-50 %** sur 20 contacts qualifiés.
- Réponse intéressée (suite de conversation) : **10-20 %**.
- Rendez-vous / call : **5-10 %**.
- Partenariat formel / collaboration : **2-5 %** sur 6-12 mois.
- Partenariat avec apport de valeur (data feed officiel, mention publique, lien institutionnel) : **1-3 %** réaliste.

Ce sont des fourchettes optimistes pour un single contact center sans antériorité institutionnelle. À recalibrer après les 5 premiers retours.

**Métriques de succès — explicites**
- Court terme (J+30) : ≥ 3 réponses sur 20 emails ; ≥ 1 conversation poursuivie.
- Moyen terme (J+90) : ≥ 1 mention publique / lien sur un site institutionnel ; ≥ 1 introduction à un autre contact qualifié.
- Long terme (J+180) : ≥ 1 collaboration concrète (data feed, mention dans un programme édu, intervention dans un workshop public).

**Dépendances**
- Bénéficie de PISTE 6 (sécurité) en amont — pour ne pas pitcher un site avec service en `root`.
- Bénéficie de PISTE 2 (Algérie) en parallèle — un appui CRAAG / Université local renforce la crédibilité institutionnelle et peut servir de référence dans les emails internationaux.
- Indépendant de PISTE 3, 4, 5.

**Score d'intérêt — 3 axes**

| Axe | Score (1-10) | Justification |
|---|---:|---|
| Impact court terme (1-3 mois) | 6 | Quelques réponses positives possibles, mais cycle institutionnel lent. |
| Impact long terme (6-24 mois) | **9** | Une seule collaboration scientifique = transformation du positionnement. |
| Effort/ROI | 8 | 2 jours pour un upside non-borné, downside ≈ 0. |

**Verdict** : meilleur ratio strategic-play / effort de toutes les pistes. À démarrer sans attendre la complétion totale du kit — les 3 premiers emails peuvent partir avec README + ARCHITECTURE seuls.

**Détail tactique — séquencement précis sur 14 jours**

| Phase | Jours | Action | Output |
|---|---|---|---|
| Vague 1 — minimal viable | J1 | 3 emails ciblés (ESA Education, UNAWE, IAU OAE) avec README + ARCHITECTURE en lien | 3 contacts ouverts |
| Préparation kit | J2-J3 | One-pager PDF (Canva, 1 j) + screen reel 90 s (OBS, 0.5 j) + page `/press` sur le site (0.5 j) | Kit complet |
| Vague 2 — élargie | J4-J5 | 8-12 emails avec kit complet : NASA Education, JPL Education, CNES Education, AWB, OAE Subsidiary nodes, CRAAG (en parallèle PISTE 2) | 11-15 contacts ouverts |
| Suivi vague 1 | J7 | Relance courte aux 3 contacts vague 1 (1 paragraphe, "courtesy follow-up") | 0-3 réponses |
| Vague 3 — niche | J9-J10 | 5-8 emails ciblés : éditeurs de revues astronomy popularisation (Sky & Telescope, Ciel et Espace), responsables planétariums francophones, profs astro lycées prestigieux | 16-23 contacts |
| Suivi vague 2 | J12 | Relance vague 2 | 0-5 réponses additionnelles |
| Bilan | J14 | Compter retours, identifier qui répond / qui ouvre / qui ignore. Itérer wording si signal négatif. | Plan ajustement |

**Ce que le kit doit contenir** :
- **One-pager PDF** : titre + tagline + ASCII architecture simplifiée + 5 use-cases (ISS tracking, JWST imagery, NOAA alerts, AEGIS chat, Hilal calculator) + 3 metrics réelles (262 routes, 47 countries, 2100+ visitors) + 1 photo de toi + 3 liens (site, README, ARCHITECTURE).
- **Screen reel 90 s** : montre la home, le globe 3D, l'ISS tracker, le module Hilal (différenciateur unique), AEGIS chat. Pas de voix off (s'il faut sous-titrer ou doubler en EN/FR/AR plus tard, c'est plus facile sans audio dès le départ).
- **Page `/press`** : version web du one-pager + screenshots HD téléchargeables + bio courte du Director + contact direct.

**Mesure d'efficacité par étape**
- Open rate du email (si tu utilises un tracker comme Mailtrack ou similaire — *à débattre éthiquement*) : > 50 % bon, > 70 % excellent.
- Réponse rate : > 5 % normal pour cold outreach institutionnel ; > 15 % très bon ; < 2 % signal "wording à revoir".
- Forward rate (mention par destinataire à un tiers) : très difficile à mesurer sans demander explicitement. À demander dans les emails de relance ("if this isn't your area, would you know someone for whom it might be?").

**Ce qu'il faut éviter explicitement**
- Mass mailing avec mail merge automatisé : 80 % chance de finir en spam folder, 100 % chance de tuer la crédibilité du domaine `astroscan.space` pour 30 jours.
- Pièces jointes lourdes au premier contact : > 1 MB est bloqué par certains MTA institutionnels.
- Ton défensif ("je sais que je ne suis pas une institution...") : retourne le cadrage en force ("ORBITAL-CHOHRA is the **first** independent francophone observatory of its kind... **").
- Promesse de fonctionnalité non-existante : si on dit "we offer real-time NASA data feeds", il faut que ce soit littéralement vrai, pas "presque vrai".

**Ce qu'on peut faire si la vague 1 obtient zéro réponse à J+10**
- Hypothèse 1 : wording trop générique → personnaliser bien plus (mentionner un projet spécifique du destinataire).
- Hypothèse 2 : sujet trop vague → reformuler avec une demande précise ("Would you consider a 5-min mention in your next newsletter?").
- Hypothèse 3 : timing (mai = fin année académique, beaucoup d'OoO) → reporter de 4 semaines.
- Hypothèse 4 : adresse inactive → vérifier en cherchant la même personne sur LinkedIn / ResearchGate.

---

### 2.2 PISTE 2 — Outreach Algérie / Université Tlemcen + CRAAG

**Cibles** :
- **Université Aboubekr Belkaïd, Tlemcen** — Faculté des Sciences, Département de Physique (proximité géographique + branding "from Tlemcen" naturel).
- **CRAAG** (Centre de Recherche en Astronomie, Astrophysique et Géophysique, Bouzaréah, Alger) — l'institution astronomique de référence en Algérie.
- **USTHB** (Université des Sciences et de la Technologie Houari Boumédiène, Alger) — département physique / astrophysique.
- **APAA** (Association Populaire des Astronomes Amateurs, Alger) — réseau amateur actif.

**Description précise**
Trois contacts physiques + courriers formels FR. Pour Tlemcen : visite directe possible (une demi-journée). Pour CRAAG / USTHB : courrier officiel + email. Objectifs : (a) référencement croisé, (b) accueil de stagiaires master 2 / doctorants pour contributions au projet, (c) intervention en workshop / conférence locale, (d) crédibilité institutionnelle utilisable dans outreach international (PISTE 1).

**Effort réaliste**
- Préparation dossier FR (1 page) : 0.5 jour.
- Visite Université Tlemcen : 0.5 jour (incluant déplacement).
- Courrier CRAAG + USTHB + APAA : 0.5 jour.
- **Total** : 1.5 jour. Suivi : 1 h/semaine.

**Pré-requis**
- Dossier FR (peut être un sous-set du README + ARCHITECTURE — pas de travail nouveau).
- Identifier un contact-clé à Tlemcen (chef département physique / responsable communication scientifique). Probablement déjà connu localement.
- Adresses postales / emails CRAAG, USTHB.
- Aucune autorisation administrative spéciale à obtenir.

**Risques techniques / opérationnels** : nuls.

**Risques business** :
- Délais administratifs algériens : réponse formelle peut prendre 4-12 semaines. Ne pas attendre cette piste pour avancer.
- Désintérêt local : possible si l'écosystème ne valorise pas une plateforme web. → Atténué par approche directe physique à Tlemcen.

**Probabilité de succès**
- Réponse Université Tlemcen : **70-85 %** (proximité + nature publique).
- Réponse CRAAG : **50-70 %** (institution sérieuse, ils répondent généralement aux démarches motivées).
- Engagement concret (stagiaire / mention / workshop) : **30-50 %**.
- Citation officielle / partenariat formel à 12 mois : **20-30 %**.

Significativement plus élevé qu'à l'international en raison de la proximité.

**Métriques de succès**
- J+30 : au moins une réunion physique / call. Au moins une réponse écrite formelle.
- J+90 : au moins un stagiaire ou un étudiant identifié pour contribuer / utiliser la plateforme.
- J+180 : intervention publique (workshop, journée portes ouvertes, conférence) liant Université Tlemcen ↔ ORBITAL-CHOHRA.

**Dépendances**
- Renforce PISTE 1 (mention "supported by Université de Tlemcen / referenced by CRAAG" change les emails internationaux).
- Indépendant techniquement.

**Score d'intérêt**

| Axe | Score (1-10) | Justification |
|---|---:|---|
| Impact court terme | 7 | Réponses rapides probables, ancrage local utile. |
| Impact long terme | 7 | Réseau étudiants + contributeurs + crédibilité durable. |
| Effort/ROI | 9 | 1.5 jour, downside nul, upside concret. |

**Verdict** : à faire en parallèle de PISTE 1. Pas urgentissime mais hautement rentable.

**Détail tactique — Algérie**

| Cible | Action recommandée | Channel | Effort |
|---|---|---|---|
| Université Aboubekr Belkaïd Tlemcen — Faculté des Sciences | Visite physique avec demande de RDV au chef du département de physique. Si le département a un club d'astronomie étudiant, l'identifier en priorité. | RDV physique + email follow-up | 0.5 j |
| CRAAG (Bouzaréah, Alger) | Courrier formel (papier + email) au directeur, mention explicite de la dimension "outreach scientifique francophone". Joindre dossier FR. | Courrier postal recommandé + email | 0.5 j |
| USTHB Alger — Département Physique | Email au responsable du département. Moins prioritaire que CRAAG mais utile en redondance. | Email | 1 h |
| APAA (Association Populaire des Astronomes Amateurs) | Demande d'intervention / présentation lors d'une de leurs réunions mensuelles. | Email + Facebook | 1 h |
| Lycées scientifiques de Tlemcen (Lycée Ibn Khaldoun, autres) | Proposition d'intervention en sciences physiques / astronomie. Public différent (lycéens) mais ancrage local fort. | Email + RDV | 1 h |

**Bénéfice transversal pour PISTE 1**
Toute mention "supported by Université Aboubekr Belkaïd, Tlemcen" ou "in collaboration with CRAAG" — même informelle — change la nature des emails outreach internationaux. Passer d'une démarche "individuelle indépendante" à "ancrée institutionnellement Algérie" multiplie probablement par 2 ou 3 le taux de réponse qualifié à l'international.

**Risque spécifique à atténuer**
Lenteur administrative algérienne. Recommandé : démarches en parallèle (5 cibles simultanément) plutôt que séquentiellement (une à la fois en attendant retour). Le coût est faible, le gain en vitesse est x3-x5.

**Ce qu'il ne faut pas faire**
- Demander un partenariat formel d'emblée. Trop tôt. Demander d'abord une simple visite, présentation, ou mention.
- Mentionner monétisation/revenu/business model. ASTRO-SCAN est sans monétisation, c'est cohérent avec le pitch éducation/recherche. Toute mention business risque de brouiller le message dans un cadre académique algérien.
- Promettre des contributions (open source contributor account, etc.) avant d'avoir validé que l'équipe peut suivre la collaboration. Mieux vaut commencer petit et dire oui à quelque chose de concret, que dire oui en grand et décevoir.

---

### 2.3 PISTE 3 — Phase 3 architecture (Redis + Prometheus + JWT)

**Description précise**
- **Redis** comme backend cache cross-worker (remplacement de `services.cache_service` actuellement par-worker).
- **Prometheus + Grafana** : exporter `/metrics`, dashboard observatoire, alertes Kp / circuit-breakers.
- **Rate-limiting nginx** : `limit_req_zone` agressif sur `/api/ai/*` (anti-abuse Claude/Groq quota).
- **JWT auth** : protéger `/api/internal/*` (admin, debug, force-monolith) — actuellement Bearer token statique en dur.

**Effort réaliste**
- Redis migration : 1.5 j (installation, refactor cache_service, tests, redéploiement).
- Prometheus + Grafana : 1.5 j (exporter, scrape config, dashboard, 5-6 alertes).
- Rate-limiting nginx : 0.5 j (déjà partiellement présent, à étendre + tester).
- JWT auth : 1 j (libs, refactor middleware, rotation des tokens).
- **Total** : 4-5 jours.

**Pré-requis**
- Redis installé sur le serveur (probablement déjà car `services.circuit_breaker` est Redis-backed post-PASS-15 — à vérifier).
- Prometheus + Grafana à provisionner (Hetzner) ou utiliser hosted (Grafana Cloud free tier).
- Renouveler `SECRET_KEY` Flask + générer paire clés JWT.

**Risques techniques / opérationnels**
- **Élevés**. Toute migration cache/auth touche du chemin critique. Une régression silencieuse = downtime ou pire (auth cassée).
- Prometheus self-hosted = +1 process à maintenir. Grafana Cloud free tier = OK pour l'usage actuel.
- JWT mal implémenté = vecteur d'attaque (CVE classiques : alg=none, key confusion).

**Risques business**
- **Aucun bénéfice immédiat** au volume actuel. La charge actuelle (≤ 50 req/s pic) est servie confortablement par 4 workers × 4 threads sur SQLite WAL. Le cache per-worker est suffisant.
- Le risque réel : passer 5 jours sur de l'infra invisible aux destinataires de PISTE 1 et PISTE 2. Aucun email outreach ne va dire "wow, ils ont Prometheus". Ce qui *se voit* dans un pitch, c'est : feature, données, design, fiabilité observée — pas le stack interne.

**Probabilité de succès** (technique) : 80 %. C'est faisable, c'est juste long.

**Probabilité que ça change quelque chose de mesurable d'ici 3 mois** : < 20 %.

**Métriques de succès**
- p99 latency `/api/iss` : non-changée significativement (le bottleneck n'est pas le cache).
- Cache hit rate cross-worker : visible (à 60-80 %). Métrique propre, ROI faible.
- Time-to-detect d'un incident : amélioré de "X minutes" à "X-2 minutes". Marginal vu l'audience actuelle.

**Dépendances**
- N'apporte rien à PISTE 1, 2, 4.
- A un faible bénéfice marginal sur PISTE 6 (sécurité) — JWT + rate-limiting recoupent partiellement.

**Score d'intérêt**

| Axe | Score (1-10) | Justification |
|---|---:|---|
| Impact court terme | 2 | Aucun. La prod tient sans. |
| Impact long terme | 5 | Utile *si* trafic explose. Non garanti. |
| Effort/ROI | 3 | 5 jours pour un upside hypothétique. |

**Verdict** : **fausse bonne idée à ce stade**. À reconsidérer le jour où soit (a) trafic > 100 req/s soutenu, soit (b) un partenaire explicitement demande monitoring/SLA. Ni l'un ni l'autre actuellement.

**Exception** : la **partie rate-limiting nginx + JWT auth** sur `/api/internal/*` (sécurité) doit être faite — mais c'est dans PISTE 6, pas ici. Le découpage : sécurité = oui (PISTE 6), Redis/Prometheus = non.

**Détail tactique — quand reconsidérer**

Voici les **conditions explicites** sous lesquelles PISTE 3 redevient prioritaire :

| Trigger | Condition observable | Action déclenchée |
|---|---|---|
| Trafic prod > 100 req/s soutenu sur 1 h | Logs nginx + ratio CPU workers | Lancer Redis migration |
| p99 latency `/api/iss` > 500 ms régulier | Sentry performance ou logs | Lancer cache cross-worker |
| Demande explicite d'un partenaire "SLA monitoring required" | Email de partenaire | Lancer Prometheus + dashboard |
| Incident silencieux (downtime non-détecté > 30 min) | Rapport utilisateur post-fact | Lancer monitoring synthétique externe |
| Coût Claude/Groq > 50 €/mois | Stripe / billing | Activer rate-limiting + circuit-breakers usage-based |

Aucune de ces conditions n'est actuellement remplie. Tant que ce n'est pas le cas, **chaque heure investie dans PISTE 3 est de l'optimisation prématurée**.

**Coût caché trop souvent ignoré**
Une fois Prometheus + Grafana installés, **il faut les maintenir**. Mises à jour, reboot, failed scrape, alertes faussement positives qui réveillent à 3 h du matin pour rien. Pour un single director, chaque ajout d'infra est une *future dette opérationnelle*. Le bon moment pour ajouter un système de monitoring c'est quand l'absence de ce système te coûte plus que sa présence.

**Mini-version acceptable (si vraiment l'envie démange)**
- Ajouter `UptimeRobot` (gratuit, externe) sur `/api/health` toutes les 5 min. Coût : 10 min de setup, zéro maintenance, alerte SMS/email gratuite. → C'est `--cov` 80 % du bénéfice de PISTE 3 monitoring pour 0.5 % du coût.

---

### 2.4 PISTE 4 — SneakerBot v2 : premier client payant 29 €/mois

**Description précise**
Conversion du premier client payant. Trois leviers :
- (a) **Activer Awin + Tradedoubler** (clés API en attente — bloqué externe). Sans elles, l'inventaire d'offres est limité.
- (b) **Polish funnel d'inscription** — étapes login → trial → paywall. Identifier où décrochent les 4 trials sans conversion.
- (c) **Acquisition** — TikTok 20 jours actif sans conversion ; envisager nouveau canal (groupes Facebook sneakers FR, Discord sneaker FR, micro-influenceurs niche).

**Effort réaliste**
- (a) Awin/Tradedoubler : bloqué externe → effort = 1 h relance + attente. **Pas de levier direct cette semaine.**
- (b) Funnel polish : nécessite données. Étape 1 = audit actuel (1 h). Étape 2 = identification des fuites (selon données : 0.5 j à 2 j). Étape 3 = correctifs (variable).
- (c) Acquisition diversifiée : 1 j de prospection groupes/Discord, 1 j de production de contenu adapté.
- **Total réaliste cette semaine** : 2-3 jours, mais avec faible probabilité d'aboutir à un client en 7 jours.

**Pré-requis**
- Funnel analytics fonctionnel (pas confirmé) — sinon, étape 0 = installer Plausible / GoatCounter / Posthog (2 h).
- Accès aux logs/comportement des 4 trial accounts.
- Identifiants groupes Facebook / Discord cibles.

**Risques techniques / opérationnels** : faibles.

**Risques business** :
- 20 jours de TikTok actif sans conversion = **signal fort** que le problème n'est probablement pas le canal seul. Continuer à pousser le même funnel sur de nouveaux canaux risque de produire le même résultat.
- Le bottleneck possible : (i) prix 29 €/mois trop élevé pour la value perçue actuelle, (ii) tunnel friction (étapes, paiement, langue), (iii) produit incomplet (Awin/Tradedoubler manquants = inventaire pauvre), (iv) audience TikTok mal-ciblée (jeunes ados sans CB).
- **Ne pas faire** : continuer à investir dans l'acquisition sans avoir trouvé le bottleneck. C'est jeter du temps sur un funnel cassé.
- **À faire** : audit funnel (où décrochent-ils ?) + interview qualitative des 4 trials (pourquoi pas convertis ?).

**Probabilité de succès — premier client en 7 jours** : **15-25 %** réaliste, conditionné à :
- Awin/Tradedoubler activées d'ici là (incertain — externe).
- Audit funnel révélant un bottleneck simple à corriger.
- Acquisition élargie aux canaux à plus haute intentionnalité d'achat.

**Probabilité — premier client en 30 jours** : **40-60 %** si l'audit révèle des actionables.

**Métriques de succès**
- Taux de conversion trial → paying : > 0 % (basique mais factuel).
- Taux d'inscription trial : connu et trackable.
- Retention D7 trial : signal qualité produit.
- 1 client à 29 €/mois = **première validation business du portfolio Chohra**.

**Dépendances**
- Indépendante d'ASTRO-SCAN (différent projet).
- Conflit de bandwidth direct avec PISTE 1, 2, 6 (toute heure SneakerBot = pas ASTRO-SCAN).

**Score d'intérêt**

| Axe | Score (1-10) | Justification |
|---|---:|---|
| Impact court terme | **8** | Premier euro de revenu = preuve commerciale. |
| Impact long terme | 7 | Pipeline B2C éprouvée = base pour pivoter / scaler. |
| Effort/ROI | 6 | Forte dépendance externe + funnel à diagnostiquer ; ROI réel après diagnostic. |

**Verdict** : **prioritaire pour le revenu**, mais **pas en pousse acquisition** cette semaine. La bonne allocation : **0.5 jour audit funnel** cette semaine, puis décision basée sur données (le résultat de l'audit dictera s'il faut 2 j de polish, 2 j d'acquisition, ou pivot prix).

**Détail tactique — audit funnel SneakerBot (le 0.5 j de jour 5)**

**Étape 0 — installer analytics si absent (1 h max)**
Si pas déjà fait : Plausible Cloud (9 €/mois, GDPR-compliant, simple) ou GoatCounter (gratuit, open source). Eviter Google Analytics 4 — trop verbeux pour un audit rapide.

**Étape 1 — cartographier le funnel actuel (30 min)**
Lister explicitement les étapes :
1. Visiteur landing page
2. Click "Try free" / "Sign up"
3. Formulaire d'inscription
4. Email confirmation
5. Premier login
6. Découverte du produit (combien de clics avant de comprendre ?)
7. Page paywall
8. Click "Subscribe"
9. Form Stripe
10. Paiement validé

**Étape 2 — identifier où décrochent les 4 trials (2-3 h)**
Pour chacun des 4 trial accounts existants :
- Quand se sont-ils inscrits ? (date)
- Combien d'actions ont-ils faites ? (login count, pages visitées, alertes créées, etc.)
- Combien de temps total ?
- À quel moment ont-ils arrêté ? (dernière session)
- Ont-ils vu le paywall ? Cliqué ?

Si les données ne sont pas disponibles dans la DB actuelle, c'est un signal qu'il faut **ajouter du tracking minimum** avant tout autre travail funnel — sinon, on optimise en aveugle.

**Étape 3 — formuler 1 hypothèse principale + 2 alternatives (1 h)**
Exemple typique :
- H1 (probable) : Les utilisateurs s'inscrivent par curiosité TikTok mais l'inventaire d'offres limité (Awin/Tradedoubler manquants) ne génère pas la valeur attendue → décrochage avant paywall.
- H2 : Les utilisateurs voient le paywall mais 29 €/mois est perçu trop cher pour la valeur démontrée pendant le trial → décrochage AU paywall.
- H3 : Le tunnel d'inscription a une friction technique (email confirmation lente, formulaire trop long, langue mauvaise) → décrochage AVANT le trial.

**Étape 4 — décision allocation S+1 (30 min)**
- Si H1 dominant : attendre Awin/Tradedoubler + relancer en intensifiant offres existantes.
- Si H2 dominant : tester un prix plus bas (9.99 €/mois) ou modèle freemium.
- Si H3 dominant : remettre le tunnel à plat (1-2 j de UX).

**Garde-fou — interview qualitative**
Idéalement, contacter directement (email, sympathique) les 4 trials pour leur poser **1 question** :
> "Hi, I noticed you signed up to SneakerBot last week and didn't subscribe. No worries — but if you have 30 seconds, what could have made the product more valuable for you?"

Taux de réponse attendu : 25-50 %. Même 1 réponse honnête = 10x plus utile que 100 lignes d'analytics.

**Pourquoi c'est IMPORTANT que cet audit se fasse cette semaine**
Sans audit, l'arbitrage "intensifier acquisition vs. polir produit vs. baisser prix" est un coin flip. Avec audit, c'est une décision *informée*. Le coût d'un audit (0.5 j) est nettement inférieur au coût d'un mauvais arbitrage (2-3 j gaspillés sur le mauvais levier).

---

### 2.5 PISTE 5 — Tests d'intégration end-to-end (ASTRO-SCAN)

**Description précise**
Compléter la suite pytest actuelle (51 tests / 21 BPs) par :
- Tests E2E réels contre `create_app("testing")` couvrant les 11 endpoints critiques avec mocks des APIs externes (Anthropic, NASA, NOAA).
- Coverage > 70 % sur `app/services/`.
- Test de régression visuelle (screenshots) optionnel.
- Tests de charge basique (locust / ab) sur `/api/iss` et `/api/health`.

**Effort réaliste**
- E2E + mocks : 1 jour.
- Coverage push de ~50 % actuel à > 70 % : 1 jour.
- Locust setup + scénarios : 0.5 j.
- **Total** : 1.5-2.5 jours.

**Pré-requis**
- `pytest-cov` déjà installé (PASS 21).
- `responses` ou `httpx_mock` à ajouter à `requirements-dev.txt`.
- Locust : optionnel.

**Risques techniques / opérationnels** : nuls.

**Risques business** :
- **Gold-plating**. La suite actuelle (51 tests) est suffisante pour l'argument "code testé" dans un pitch. Doubler la suite = marginal pour la décision d'un destinataire.
- Le coût d'opportunité : 2 jours sur des tests = 2 jours non passés sur outreach (PISTE 1+2) où l'effet est asymétrique (réponses concrètes vs. nombre).

**Probabilité de succès — technique** : 90 %.

**Probabilité que ça change la décision d'un destinataire de pitch** : < 5 %.

**Métriques de succès**
- Coverage : 50 % → 70 %+. Visible mais peu actionnable.
- Régressions détectées en CI : 0 actuellement, probablement pareil après.
- Temps avant rollback en cas d'incident prod : non-affecté (les tests CI ne tournent pas en prod).

**Dépendances**
- Renforce *marginal* PISTE 1 (peut citer "70 % coverage" dans pitch).
- Indépendant des autres pistes.

**Score d'intérêt**

| Axe | Score (1-10) | Justification |
|---|---:|---|
| Impact court terme | 3 | 51 tests existants suffisent à passer toute discussion technique normale. |
| Impact long terme | 5 | Utile à long terme pour la maintenance, mais déjà couvert par baseline actuelle. |
| Effort/ROI | 4 | 2 jours pour passer de "honorable" à "honorable+". |

**Verdict** : **fausse bonne idée pour cette semaine**. À reprendre dans 6-8 semaines, ou si un destinataire de pitch demande explicitement coverage > 70 %. La plupart ne demandent même pas — ils regardent le README, l'architecture, et la live demo.

**Détail tactique — version "minimum acceptable" si vraiment l'envie démange**
Si malgré tout, du temps mort apparaît dans la semaine, voici **les 4 ajouts tests les plus utiles** (par ordre de ROI décroissant) — chacun est < 1 h de travail :

1. **`tests/smoke/test_external_apis_mocked.py`** — un test par API externe (NASA, NOAA, JPL Horizons, CelesTrak) avec `responses` mock, vérifie que la couche service gère bien : (a) succès normal, (b) timeout, (c) 5xx error, (d) malformed JSON. Coût : 30 min/API × 4 = 2 h. Bénéfice : démontre la maturité défensive du code.

2. **`tests/smoke/test_health_payload_complete.py`** — vérifie que `/api/system-status` retourne une structure JSON conforme à un schéma fixé (workers, memory, cache hit rate, circuit-breakers). Coût : 30 min. Bénéfice : empêche un drift de payload de passer en silence.

3. **`tests/integration/test_static_assets_present.py`** — vérifie que tous les assets `static/img/` référencés dans les templates sont effectivement présents. Coût : 30 min. Bénéfice : détecte les liens cassés avant un visiteur de pitch.

4. **`tests/smoke/test_no_secrets_in_code.py`** — grep sur `repo` à la recherche de patterns de tokens connus (Bearer, sk-, ghp_, AKIA, etc.). Coût : 20 min. Bénéfice : garde-fou avant chaque PR.

Si on en fait un, c'est le n°4 (anti-régression de fuite de credentials). Si on en fait deux, n°1 puis n°4. Au-delà, retour gold-plating.

---

### 2.6 PISTE 6 — Hardening sécurité ASTRO-SCAN

**Description précise**
- **Drop privileges systemd** : créer user `astroscan` (uid dédié), chown du repo, modifier `User=astroscan` dans `astroscan.service`. Le `.env` reste mode 600 mais owned `astroscan`.
- **Sandboxing systemd** : `PrivateTmp=yes`, `ProtectSystem=strict`, `ProtectHome=yes`, `NoNewPrivileges=yes`, `ProtectKernelTunables=yes`, `RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6`.
- **Rate-limiting nginx** : `limit_req_zone` strict sur `/api/ai/*` (anti-abuse Claude/Groq quota), modéré sur `/api/*`.
- **HTTP headers** : HSTS strict, CSP renforcée, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy.
- **Rotation des tokens admin** : remplacer le Bearer statique du `/api/admin/circuit-breakers` par un token rotaté (peut être lié à PISTE 3 JWT, mais une rotation manuelle 2026-Q2 suffit pour l'instant).
- **Audit `.env`** : vérifier qu'aucun secret n'est en clair dans le repo (a priori non, à confirmer).

**Effort réaliste**
- Drop privileges + sandboxing : 0.5 j (incluant test rollback).
- Rate-limiting + headers nginx : 0.5 j.
- Rotation tokens + audit : 0.25 j.
- **Total** : 1 jour pleinement.

**Pré-requis**
- Accès root sur le serveur (acquis).
- Test de redéploiement avec rollback prêt (déjà documenté dans `ROLLBACK_PASS18.md`).
- Vérifier qu'aucun chemin n'est codé en dur sur `/root/astro_scan` dans station_web (sinon, écrire à `/var/lib/astroscan`).

**Risques techniques / opérationnels**
- **Modérés**. Le drop privileges peut casser des chemins en dur (`/root/astro_scan/...`) si présents dans le code. Probabilité : moyenne (legacy monolith). Mitigation : test de smoke `make test-smoke` avant restart, rollback systemd drop-in si KO.
- Les sandboxing systemd peuvent bloquer un appel système qu'on ignorait utiliser (rare en pure Flask + requests). Mitigation : démarrage en `Verbose` la première fois, lecture de journalctl.

**Risques business**
- **Inverse**. Le risque est de **ne pas le faire** : un pitch international qui mène à une revue technique, et le reviewer voit `User=root` → impact réputationnel disproportionné. C'est un detail, mais un détail qui fait mauvais genre.

**Probabilité de succès** : 90 %.

**Métriques de succès**
- `ps -ef | grep gunicorn` montre user `astroscan`, pas `root`.
- `systemd-analyze security astroscan.service` : score de sécurité passe de "UNSAFE" (~9.x/10) à "MEDIUM" ou mieux.
- `curl -I https://astroscan.space` montre HSTS + CSP + autres headers de sécurité.
- Prod toujours up, 11 endpoints critiques toujours 200.

**Dépendances**
- **Pré-requis souhaitable de PISTE 1** (avant outreach). Pas bloquant strict, mais à faire avant d'envoyer la 5e vague d'emails à des destinataires sérieux.
- Indépendant techniquement de PISTE 2, 3, 4, 5.

**Score d'intérêt**

| Axe | Score (1-10) | Justification |
|---|---:|---|
| Impact court terme | 7 | Pré-requis à PISTE 1, ROI direct au pitch. |
| Impact long terme | 8 | Réduit attack surface durablement. |
| Effort/ROI | **9** | 1 jour, ROI immédiat, downside négligeable. |

**Verdict** : **à faire avant la fin de la semaine.** Idéalement jour 1 ou 2.

**Détail tactique — étapes ordonnées avec tests à chaque palier**

**Étape 1 — Préparer le terrain (30 min, sans toucher prod)**

```bash
# 1.1 Identifier tous les chemins en dur sur /root/ ou /home/
cd /root/astro_scan
grep -rn "/root/astro_scan" station_web.py app/ services/ | head -30
# Lister les chemins d'écriture (DBs, exports, logs, cache)
grep -rn "open(.*['\"]w" station_web.py app/ services/ | head -20
```

**Étape 2 — Créer user astroscan + chown (15 min)**

```bash
# 2.1 Créer le user
sudo useradd -r -s /usr/sbin/nologin -d /root/astro_scan astroscan

# 2.2 Préparer les chemins d'écriture en dehors de /root
sudo mkdir -p /var/lib/astroscan /var/log/astroscan
sudo chown -R astroscan:astroscan /var/lib/astroscan /var/log/astroscan

# 2.3 Donner accès lecture au repo (sans donner write)
sudo chown -R root:astroscan /root/astro_scan
sudo chmod -R g+rX /root/astro_scan
sudo chmod 640 /root/astro_scan/.env
sudo chown root:astroscan /root/astro_scan/.env

# 2.4 Donner write sur les sous-dossiers utilisés
sudo chown -R astroscan:astroscan /root/astro_scan/data
sudo chown -R astroscan:astroscan /root/astro_scan/exports
```

**Étape 3 — Modifier l'unit systemd avec drop-in (10 min)**

```bash
sudo systemctl edit astroscan
```

Ajouter dans le drop-in :

```ini
[Service]
User=astroscan
Group=astroscan
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
RestrictNamespaces=yes
LockPersonality=yes
RestrictRealtime=yes
SystemCallArchitectures=native
ReadWritePaths=/root/astro_scan/data /root/astro_scan/exports /var/lib/astroscan /var/log/astroscan
```

**Étape 4 — Test à blanc avant restart (5 min)**

```bash
# Vérifier la syntaxe
sudo systemd-analyze verify astroscan.service

# Voir le score de sécurité
sudo systemd-analyze security astroscan.service
# Avant : score ≈ 9.6/10 "UNSAFE"
# Après : score visé ≤ 5.5/10 "MEDIUM"
```

**Étape 5 — Restart avec rollback prêt (5 min, attentif)**

```bash
sudo systemctl daemon-reload
sudo systemctl restart astroscan
sleep 8

# Smoke test immédiat — si KO, rollback
curl -fsS https://astroscan.space/api/health
journalctl -u astroscan -n 50 --no-pager | grep -E "ERROR|Permission|Read-only"
```

**Si OK** → continuer Étape 6 (nginx).
**Si KO** → rollback immédiat :

```bash
sudo systemctl revert astroscan
sudo systemctl restart astroscan
# diagnostiquer via journalctl quel sandboxing a cassé
```

**Étape 6 — Nginx rate-limiting (30 min)**

Ajouter dans `/etc/nginx/nginx.conf` (bloc `http { }`) :

```nginx
limit_req_zone $binary_remote_addr zone=api_general:10m rate=30r/s;
limit_req_zone $binary_remote_addr zone=api_ai:10m rate=10r/m;
limit_req_zone $binary_remote_addr zone=admin_zone:10m rate=2r/m;
limit_req_status 429;
```

Et dans `/etc/nginx/sites-available/astroscan` (bloc `server { }`) :

```nginx
location ~ ^/api/admin/ {
    limit_req zone=admin_zone burst=2 nodelay;
    proxy_pass http://127.0.0.1:5003;
    # ... headers usuels
}

location ~ ^/api/(ai|aegis)/ {
    limit_req zone=api_ai burst=10 nodelay;
    proxy_pass http://127.0.0.1:5003;
    proxy_buffering off;          # SSE streaming
    proxy_read_timeout 120s;
    # ... headers usuels
}

location /api/ {
    limit_req zone=api_general burst=60 nodelay;
    proxy_pass http://127.0.0.1:5003;
    # ... headers usuels
}
```

Test : `nginx -t && systemctl reload nginx`. Vérifier avec `curl` rapide en boucle sur `/api/ai/explain` qu'on obtient bien 429 après dépassement.

**Étape 7 — HTTP Headers (15 min)**

Voir Annexe 8.5 pour le snippet complet. Démarrer la CSP en mode `Content-Security-Policy-Report-Only` pendant 48 h, puis enforcer.

**Étape 8 — Rotation tokens admin (15 min)**

Le `/api/admin/circuit-breakers` utilise actuellement un Bearer statique (`lXnUPqYSFsX6bWIXL9AQnYdo-_EzFNFci6O-sqzByXc` est dans le repo, à révoquer). Action :
- Générer un nouveau token (`openssl rand -hex 32`).
- L'ajouter à `.env` comme `ADMIN_TOKEN=...`.
- Modifier le code pour lire `os.environ['ADMIN_TOKEN']` au lieu d'une constante en dur.
- Révoquer l'ancien (= ne plus l'accepter).
- Mettre à jour les tests qui l'utilisaient (test_legacy_routes.py) pour skip si `ADMIN_TOKEN` absent.

**Étape 9 — Audit final & doc (15 min)**

- `systemd-analyze security astroscan.service` → noter le score avant/après.
- Tester les 11 endpoints critiques.
- Mettre à jour `DEPLOYMENT.md §14` (Security Hardening Checklist) — cocher les 3 items "TODO".
- Commit avec message "PASS 22 — Hardening sécurité (drop privileges + sandboxing + rate-limit + headers)".

**Total cumulé : 2-2.5 h de travail effectif**, étalé sur 1 j calendaire pour permettre observation entre étapes (40 % du temps = vérification, pas action).

---

## 3. Tableau comparatif des 6 pistes

### 3.1 Vue synthétique

| # | Piste | Effort (j) | Court terme | Long terme | Effort/ROI | Score moyen | Risque | Dépendances |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| **1** | Outreach international | 2 | 6 | **9** | 8 | **7.7** | bas | bénéficie de 6, 2 |
| **2** | Outreach Algérie | 1.5 | 7 | 7 | 9 | **7.7** | nul | renforce 1 |
| 3 | Phase 3 architecture | 4-5 | 2 | 5 | 3 | 3.3 | élevé | aucun bénéfice 1, 2, 4 |
| 4 | SneakerBot 1er client | 2-3 | **8** | 7 | 6 | 7.0 | bas | indépendant ASTRO-SCAN |
| 5 | Tests E2E | 1.5-2.5 | 3 | 5 | 4 | 4.0 | nul | marginal pour 1 |
| **6** | Hardening sécurité | 1 | 7 | 8 | **9** | **8.0** | modéré | pré-requis pour 1 |

### 3.2 Probabilités de succès — vue côte à côte

| # | Piste | Métrique-clé | P(succès) court | P(succès long) |
|---|---|---|:---:|:---:|
| 1 | Outreach intl. | ≥ 1 mention publique J+90 | 30-50 % | 50-70 % |
| 2 | Outreach Algérie | ≥ 1 réunion physique J+30 | 70-85 % | 80-95 % |
| 3 | Phase 3 archi | p99 amélioré J+90 | 80 % tech / < 20 % perçu | < 30 % business |
| 4 | SneakerBot 1er | 1 client payant J+7 / J+30 | 15-25 % / 40-60 % | 60-80 % à 6 mois |
| 5 | Tests E2E | Coverage > 70 % | 90 % tech / < 5 % perçu | 50 % business |
| 6 | Hardening | Score systemd MEDIUM+ | 90 % | 95 % |

### 3.3 Matrice de risque — combinaisons de pistes

Si plusieurs pistes sont menées en parallèle, certaines combinaisons sont sûres, d'autres dangereuses. Lecture rapide :

| Piste A + Piste B | Compatibilité | Pourquoi |
|---|:---:|---|
| 1 + 2 | **EXCELLENT** | 2 renforce 1 (réf. institutionnelle locale). Pas de conflit bandwidth. |
| 1 + 6 | **EXCELLENT** | 6 est pré-requis à 1 (sécurité avant pitch). Séquentiel naturel. |
| 1 + 4 | OK | Bandwidth partagé. Peut faire les deux à 50/50, mais pas à 100/100. |
| 1 + 3 | DANGER | 3 = 5 j sur infra invisible aux destinataires de 1. Cannibalise 1. |
| 1 + 5 | OK marginal | 5 ne renforce 1 que de quelques %. Bandwidth mieux investi ailleurs. |
| 2 + 6 | **EXCELLENT** | Pas de conflit, complémentaires. |
| 2 + 4 | OK | 2 majoritairement courrier/visite Algérie ; 4 majoritairement digital. Indépendants. |
| 3 + 6 | OK partiel | Recoupe sur sécurité (rate-limit, JWT). 6 capture l'essentiel ; 3 ajoute Redis et Prometheus pour peu de gain. |
| 3 + 5 | DANGER | Cumul de gold-plating, total ~7 j sans bénéfice mesurable cette saison. |
| 4 + 6 | OK | Indépendants techniquement. Bandwidth partagé seulement. |
| 5 + 6 | OK | Indépendants. 5 marginal, 6 critique. |
| 4 + 5 | DANGER | Conflit business — investir sur ASTRO-SCAN tests pendant que SneakerBot a 0 paying = mauvaise priorisation. |

**Combinaison recommandée** : **{1, 2, 6}** + diagnostic minimal sur 4. C'est précisément le plan §4.4.
**Combinaison à éviter absolument** : **{3, 5}** ce mois-ci, dans toute combinaison.

### 3.4 Coût d'opportunité — visualisation

Si chaque jour de la semaine est investi dans une piste, le coût d'opportunité (= ce qu'on ne fait PAS) est asymétrique :

```
                   Day 1  Day 2  Day 3  Day 4  Day 5  Day 6  Day 7
Plan recommandé:   [1+6]  [6]    [2]    [2+1]  [1]    [4]    [bilan]
                     ↓     ↓      ↓      ↓      ↓      ↓
                   3 mails secur.  Tlemcen courrier intl.   audit
                                          +CRAAG  vague2

Plan "all PISTE 3": [3]    [3]    [3]    [3]    [3]    [-]    [-]
                   ↓
                   Redis    Prom.  JWT  rate    test   pas
                   migrate setup auth  limit  recap   d'outreach,
                                                       pas d'audit,
                                                       pas de Algérie,
                                                       pas de hardening *visible*

Plan "all PISTE 4": [4]    [4]    [4]    [4]    [4]    [-]    [-]
                   ↓
                   audit + polish + acquisition + … sans diagnostic préalable
                   = forte chance de jeter du temps sur un funnel cassé
```

Le coût d'opportunité du plan recommandé : **on n'avance pas sur PISTE 3 ni PISTE 5 cette semaine**. C'est volontaire et assumé.

---

## 4. Recommandations

### 4.1 QUICK WIN (effort < 1 jour, impact immédiat)

**PISTE 6 — Hardening sécurité.** 1 jour. Foundational. ROI immédiat dès le premier email PISTE 1 envoyé. Aucun substitut crédible.

Variante encore plus courte (< 90 min) : **les 3 premiers emails outreach de PISTE 1**. Puisqu'ils peuvent partir avec README + ARCHITECTURE actuels, sans attendre le kit complet (one-pager + reel). Premier email = première réponse possible = pipeline démarré.

**Préconisation** : faire les 3 emails *demain matin* (90 min) **et** le hardening *demain après-midi + jour 2* (1 j). Les deux ne se gênent pas — un email envoyé n'est pas en exécution sur le serveur.

### 4.2 STRATEGIC PLAY (effort 3-5 j, impact 6+ mois)

**PISTE 1 — Outreach scientifique international**, **fully executed** (kit complet : one-pager + reel + 20 emails sur 5 jours + suivis).

Pourquoi celui-là plutôt que PISTE 4 (SneakerBot) ? Trois raisons :
1. **Asymmetric upside** : un seul partenariat institutionnel (ESA Education ou IAU OAE) transforme le positionnement long terme d'ORBITAL-CHOHRA pour 2-5 ans. SneakerBot 1er client à 29 €/mois est important mais borné dans son upside.
2. **Pipeline déjà partiellement construit** : README/ARCHITECTURE/DEPLOYMENT prêts. PISTE 4 demande encore d'élucider le bottleneck du funnel (incertitude).
3. **Coût d'opportunité** : 20 jours TikTok sans conversion suggère que le problème SneakerBot n'est pas une simple intensification d'effort. Il faut diagnostiquer avant d'investir plus, pas l'inverse.

PISTE 4 reste prioritaire en parallèle, mais en mode **diagnostic-first** (0.5 j d'audit funnel) plutôt qu'**effort-first** (2 j de polish/acquisition).

### 4.3 FAUSSES BONNES IDÉES (high effort, low ROI ce mois-ci)

| # | Piste | Pourquoi écarter |
|---|---|---|
| 3 | Phase 3 architecture (Redis/Prometheus complet) | 5 jours pour résoudre un problème qui n'existe pas au volume actuel. Marginal sur PISTE 1. **Excepter** la portion sécurité (rate-limit + JWT) qui est dans PISTE 6. |
| 5 | Tests E2E supplémentaires + coverage > 70 % | 51 tests + CI/CD suffisent largement pour l'argument "tested code". Travailler sur la coverage = polir un argument déjà acceptable plutôt que sur des arguments manquants (institutional reference, cas d'usage concrets). |

Ces deux pistes ne sont **pas mauvaises** — elles sont **mal-timed**. À reprendre Q3 2026.

### 4.4 Plan 7 jours — concret

| Jour | Date | Focus principal | Allocation indicative |
|---|---|---|---|
| 1 | lun. 04/05 | **Outreach kickoff + hardening start** | 1.5 h matin : 3 emails PISTE 1 (ESA Education, UNAWE, IAU OAE). 6 h après-midi : drop privileges systemd + sandboxing (PISTE 6 partie A). |
| 2 | mar. 05/05 | **Hardening complet + audit SneakerBot** | 4 h matin : finir nginx rate-limit + headers + rotation tokens (PISTE 6 partie B). 4 h après-midi : audit funnel SneakerBot (0.5 j PISTE 4). |
| 3 | mer. 06/05 | **Outreach Algérie kickoff** | Préparation dossier FR (3 h) + visite Université Tlemcen ou prise de RDV (3 h). PISTE 2. |
| 4 | jeu. 07/05 | **Outreach Algérie suite + kit international** | Courrier CRAAG + USTHB (2 h). One-pager PDF + screen recording (4 h). PISTE 2 + PISTE 1. |
| 5 | ven. 08/05 | **Outreach international vague 2** | 5 h : envoi de 8-12 emails additionnels avec kit complet (NASA Education, JPL Outreach, CNES Education, Astronomers Without Borders, partenaires ESA tier 2). PISTE 1. |
| 6 | sam. 09/05 | **Tampon + diagnostic SneakerBot continue** | Selon les données du jour 2 : si bottleneck identifié simple → 4 h de correctifs. Sinon : tampon outreach (suivis J+5). |
| 7 | dim. 10/05 | **Bilan semaine + planification S+1** | 2 h : compter réponses outreach, analyser funnel SneakerBot, décider pivot ou intensification S+1. |

**Total temps actif** : ~5 j sur 7. Le tampon (jour 6) est *non-négociable* — c'est le buffer qui empêche le plan de dérailler à la première imprévue.

### 4.5 Demain matin — la première action après le café

**08h30-10h00 (90 min). Trois emails.**

Pas une vague de 20. Pas un kit complet. **Trois.**

| # | Destinataire | Adresse (à confirmer sur le site officiel) | Langue |
|---|---|---|---|
| 1 | ESA Education / Public Outreach | education@esa.int (générique) ou contact dédié sur esa.int/Education | EN |
| 2 | UNAWE (Universe Awareness) | info@unawe.org | EN |
| 3 | IAU OAE (Office of Astronomy for Education) | oae.iau.org/contact | EN |

**Structure de l'email** (200 mots max) :

```
Subject: ORBITAL-CHOHRA observatory — independent French/Arabic
         astronomy platform from Algeria

Dear [Name / Education Team],

I am the director of ORBITAL-CHOHRA, an independent web observatory
operating from Tlemcen, Algeria, since [date]. We aggregate live data
from NASA, NOAA, ESA and JPL into a unified French-language platform
serving the Francophone and Arabic-speaking community
(2,100+ visitors / 47 countries).

Production stack: Flask 3.1, 21 blueprints, 13 service modules,
262 routes, full CI/CD. Architecture and deployment documents are
available at:
- https://astroscan.space
- README:        [github link if public, or attached]
- ARCHITECTURE:  [link]
- DEPLOYMENT:    [link]

We would welcome an introduction to your education / public engagement
team, or a referral to programs aligned with our mission of expanding
astronomy accessibility to the Global South.

I am available for a 30-minute call at your convenience.

Best regards,
Zakaria Chohra
Director, ORBITAL-CHOHRA Observatory
zakaria.chohra@gmail.com
+213 [téléphone optionnel]
```

**Points-clés** :
- Pas de pièce jointe lourde au premier email (le destinataire ouvre et lit en 30 sec).
- Liens vers les 3 docs déjà commitées hier.
- Pas d'« opportunité business » mentionnée — pure démarche scientifique / éducative.
- Demande explicite et borne (« 30-minute call »).
- Nom + titre + contact direct.

**Pourquoi 3 et pas 20 ?**
- Permet d'itérer le wording après les premiers retours (ou non-retours).
- Évite le syndrome « j'ai envoyé 20, j'ai 0 réponse, je doute » — plus économe psychologiquement.
- 3 emails = 2 h de réflexion par destinataire pour personnaliser la phrase d'ouverture (différence qualitative vs. mass mailing).

**Après les 3 emails (10h00)** : passer immédiatement au hardening (PISTE 6 partie A — drop privileges systemd). Pas d'attente passive de réponses.

### 4.6 Ce qu'il faut explicitement NE PAS faire demain

- Ne PAS commencer Phase 3 architecture (PISTE 3). Aucun bénéfice mesurable cette semaine.
- Ne PAS écrire 5 nouveaux tests pytest (PISTE 5 hors scope). 51 tests = baseline déjà solide.
- Ne PAS pousser TikTok SneakerBot avant l'audit funnel. Investir effort dans un funnel cassé = double perte.
- Ne PAS envoyer 20 emails outreach simultanés. 3 ciblés > 20 génériques.
- Ne PAS pitcher Airbus Defence & Space, Lockheed, Northrop. Mauvais cibles pour un observatoire civil indépendant en Algérie. Pas avant 12-24 mois et un sponsor institutionnel formel.

### 4.7 Plans B et C — si la semaine ne se déroule pas comme prévu

**Plan B — Hardening jour 1 casse la prod**
Probabilité : 10-20 % (drop privileges peut révéler des chemins en dur).
Action :
1. Revert systemd drop-in immédiatement (`systemctl revert astroscan`).
2. Lister les chemins en dur problématiques (logs typiques : "Permission denied", "Read-only file system").
3. Patcher le code pour utiliser des chemins relatifs ou env vars (typiquement 30-60 min de patching).
4. Re-tester en local avant retry production.
5. Si échec persistant à J+2, reporter PISTE 6 à S+1 et continuer S+1 outreach (PISTE 1 + 2). Le service reste en `User=root` une semaine de plus, ce n'est pas idéal mais pas bloquant.

**Plan C — Outreach vague 1 obtient zéro réponse à J+10**
Probabilité : 30-40 %.
Action :
1. Revoir wording (cf. §2.1 hypothèses 1-4).
2. Demander revue à un contact externe de confiance (ami ingénieur dans une institution scientifique).
3. Repartir sur 3 nouveaux destinataires différents avec wording ajusté.
4. **Ne pas paniquer.** Cycle institutionnel = 2-12 semaines. Zéro réponse à J+10 ≠ échec.

**Plan D — Audit SneakerBot révèle un produit pas viable au prix actuel**
Probabilité : 25-35 % (en cohérence avec 0 conversion sur 4 trials sur 20 jours).
Action :
1. Documenter clairement les bottlenecks identifiés.
2. Décider entre 3 options :
   - (a) Pivot prix (tester 9.99 €/mois pour 30 jours).
   - (b) Pivot positionnement (B2B revendeurs plutôt que B2C amateurs).
   - (c) Mise en sommeil temporaire (3-6 mois) pendant que ASTRO-SCAN génère du momentum, puis reprise avec recul.
3. **Ne PAS continuer en business as usual** si l'audit montre un produit non-viable. Le coût d'opportunité est trop élevé.

**Plan E — Trois pistes en retard simultanées**
Probabilité : 15-25 % (single director = imprévus inévitables).
Action :
1. Ré-allouer la priorité à **une seule piste** : PISTE 1 (outreach).
2. Tout le reste en pause.
3. Reconstruire un plan de 7 jours plus modeste à J+7.

**Principe directeur des plans B/C/D/E** : ne pas s'entêter. Mieux vaut ajuster vite et garder l'élan que persister sur un plan qui ne fonctionne pas.

### 4.8 Ce qui est explicitement reporté à J+30 / S+5

Pour clarifier que ces sujets **ne sont pas oubliés**, ils sont *reportés* :

| Sujet | Date de réévaluation | Pourquoi reporté |
|---|---|---|
| PISTE 3 — Redis cross-worker | S+8 (mi-juin) | Trafic actuel ne le justifie pas. Réévaluer à 50+ req/s soutenu. |
| PISTE 3 — Prometheus + Grafana | S+12 (août) | Mini-version (UptimeRobot) suffit. Réévaluer si SLA partenaire. |
| PISTE 5 — Coverage > 70 % | S+6 (juin) | 51 tests = baseline. Réévaluer après pitch S+5 (signal demande tiers). |
| PISTE 5 — Tests E2E réels | S+8 | Idem. |
| API versioning `/api/v1/*` | S+6 | Pas demandé actuellement. Réévaluer si partenaire intégration. |
| Multi-language (Arabic, English UI) | S+10 | Stratégique mais ~1 mois de travail. Réévaluer après outreach feedback. |
| Mobile app (React Native) | S+24 | Pas dans l'horizon court. Réévaluer après J+90 outreach. |
| Partenariat CRAAG formel (papier signé) | S+24 | Cycle institutionnel algérien long. Réévaluer après réunion initiale. |

---

## 5. Métriques d'évaluation à J+30 (rétro-analyse)

Liste explicite des indicateurs à mesurer pour évaluer le plan ci-dessus :

| Indicateur | Cible J+30 | Source |
|---|---|---|
| Emails outreach envoyés | ≥ 20 | log local |
| Réponses outreach (toutes) | ≥ 5 | inbox |
| Réponses qualifiées (poursuite conversation) | ≥ 2 | inbox |
| Calls / réunions tenues (intl.) | ≥ 1 | calendar |
| Réunions tenues (Algérie) | ≥ 1 | calendar |
| `systemd-analyze security` score | "MEDIUM" ou mieux | shell |
| 11 endpoints critiques `/api/health` 200 | 100 % uptime | curl + UptimeRobot (à activer) |
| Coverage tests | ≥ 50 % (pas de hausse forcée) | `pytest --cov` |
| SneakerBot trial → paying | ≥ 1 ou diagnostic clair documenté | Stripe + funnel notes |
| Mention publique d'ORBITAL-CHOHRA | ≥ 1 (blog, post, mention) | Google Alerts |

Si, à J+30 :
- ≥ 6 indicateurs sur 10 atteints → plan à reconduire S+5 à S+8 avec intensification.
- 3-5 atteints → identifier le frein principal (acquisition outreach ou funnel SneakerBot) et pivoter.
- < 3 atteints → réviser fondamentalement la stratégie. Possiblement rebudgeter le temps ASTRO-SCAN/SneakerBot (50/50 actuel → 70/30 ou 30/70 selon données).

---

## 6. Tableau décisionnel final — décider en 30 secondes

```
═══════════════════════════════════════════════════════════════════════
  RECOMMANDATIONS PRIORITAIRES — ORDRE D'EXÉCUTION DEMAIN
═══════════════════════════════════════════════════════════════════════

  [1] DEMAIN MATIN 08h30-10h00 (90 min)
      → 3 emails outreach EN : ESA Education, UNAWE, IAU OAE
      → PISTE 1 — kickstart sans attente de kit complet

  [2] DEMAIN APRÈS-MIDI + JOUR 2 (1 j)
      → Hardening sécurité : drop privileges + sandboxing systemd
      → Rate-limit nginx + HSTS/CSP + rotation tokens
      → PISTE 6 — pré-requis à toute escalade outreach

  [3] JOUR 3-4 (1.5 j)
      → Outreach Algérie : Université Tlemcen + CRAAG + USTHB
      → PISTE 2 — réseau local, crédibilité institutionnelle

  [4] JOUR 5 (0.5 j)
      → Audit funnel SneakerBot — où décrochent les 4 trials ?
      → PISTE 4 — diagnostic AVANT intensification

  [5] JOUR 6-7
      → Tampon + suivis outreach + bilan S+1

═══════════════════════════════════════════════════════════════════════
  EXPLICITEMENT EXCLUS DE LA SEMAINE
═══════════════════════════════════════════════════════════════════════

  ✗  PISTE 3 — Phase 3 architecture (Redis/Prometheus complet) : 5 j,
     marginal au volume actuel. À reconsidérer Q3 2026.

  ✗  PISTE 5 — Tests E2E supplémentaires : 51 tests + CI/CD suffisent.
     Pas de bottleneck identifié.

═══════════════════════════════════════════════════════════════════════
  PRINCIPE DIRECTEUR
═══════════════════════════════════════════════════════════════════════

  Single director, bandwidth limitée. 6 pistes ouvertes, 2-3 peuvent
  vraiment avancer en parallèle.

  La règle :
    • Un strategic play (PISTE 1)
    • Un foundational must (PISTE 6)
    • Un quick relational (PISTE 2)
    • Un diagnostic side (PISTE 4)
    • Tampon non-négociable (jour 6)

  → 3 pistes en mode "execute", 1 en mode "diagnose", 0 en mode "build
    new infra". Discipline du focus > optimisme de l'agenda.

═══════════════════════════════════════════════════════════════════════
```

---

## 7. Limites et hypothèses du présent rapport

À reconnaître honnêtement :

1. **Probabilités de succès** — toutes les estimations chiffrées (% réponse outreach, % conversion SneakerBot, etc.) sont des **fourchettes basées sur baselines public**. Pas de données propres au profil ORBITAL-CHOHRA / SneakerBot. À recalibrer après les 5 premiers retours réels.
2. **Bandwidth single director** — l'allocation 7 jours suppose ~5 h productives/jour. Toute interruption (travail rémunéré parallèle, contraintes familiales, événement local) retarde proportionnellement.
3. **Awin / Tradedoubler** — bloquant externe pour PISTE 4. Si les clés arrivent jour 3, allouer une demi-journée additionnelle. Si elles n'arrivent pas du tout d'ici jour 7, réévaluer le plan SneakerBot.
4. **Réponses outreach** — peuvent demander 1-12 semaines selon institution. Le bilan jour 7 est *trop tôt* pour juger PISTE 1. Vraie évaluation à J+30 (cf. §5).
5. **Pas de revue par tiers** — ce rapport est une assistance technique automatisée, pas un audit business. Les arbitrages business finaux (prix SneakerBot, choix des canaux, orientations institutionnelles) restent au Director.
6. **Contraintes export Algérie** — non-vérifiées en détail pour chaque destinataire. Cibles présélectionnées (éducation publique uniquement) sont a priori sûres, mais une vérification par contact ne fait pas de mal avant un éventuel partenariat formel.

---

## 8. Annexes — modèles utilisables tels quels

### 8.1 Email outreach EN — version courte (à personnaliser destinataire par destinataire)

```
Subject: ORBITAL-CHOHRA — independent astronomy web observatory
         from Tlemcen, Algeria

Dear [Name / Education team],

ORBITAL-CHOHRA (astroscan.space) is an independent web observatory
that aggregates live data from NASA, NOAA, ESA, and JPL into a
unified French / Arabic interface for the Maghreb and Francophone
public.

The platform has been operational since [date] and currently serves
2,100+ visitors across 47 countries. Production stack: Flask 3.1,
21 blueprints, 13 service modules, 262 routes, with full CI/CD and
public technical documentation (README, ARCHITECTURE, DEPLOYMENT).

I am writing to introduce the project and explore whether there
might be alignment with [name of the program / division]'s public
engagement or education initiatives. A 30-minute call at your
convenience would be most welcome.

Best regards,
Zakaria Chohra
Director, ORBITAL-CHOHRA Observatory
Tlemcen, Algeria
zakaria.chohra@gmail.com  ·  https://astroscan.space
```

### 8.2 Email outreach FR — version courte (CNES, CRAAG, Université Tlemcen)

```
Objet : ORBITAL-CHOHRA — observatoire web indépendant depuis Tlemcen

Madame, Monsieur,

ORBITAL-CHOHRA (astroscan.space) est un observatoire web indépendant
qui agrège en temps réel des données scientifiques de la NASA, NOAA,
ESA et JPL au sein d'une interface francophone unifiée, à destination
du public maghrébin et francophone.

La plateforme est opérationnelle depuis [date] et accueille
2 100+ visiteurs répartis sur 47 pays. Architecture : Flask 3.1,
21 blueprints, 13 modules de service, 262 routes, intégration
continue, documentation technique publique.

Je me permets de prendre contact pour explorer une possible mise en
relation avec votre [équipe / département / programme] en éducation
ou diffusion scientifique. Je suis disponible pour une présentation
de 30 minutes à votre convenance.

Bien cordialement,
Zakaria Chohra
Directeur, Observatoire ORBITAL-CHOHRA
Tlemcen, Algérie
```

### 8.3 Hardening systemd — drop-in à appliquer (PISTE 6)

```ini
# /etc/systemd/system/astroscan.service.d/hardening.conf
[Service]
User=astroscan
Group=astroscan
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
RestrictNamespaces=yes
LockPersonality=yes
RestrictRealtime=yes
SystemCallArchitectures=native
ReadWritePaths=/root/astro_scan/data /root/astro_scan/exports /var/log/astroscan
```

À adapter : `User=astroscan` requiert création préalable du user et chown.
`ReadWritePaths` à compléter avec tout chemin où l'app écrit (DBs, exports, logs).

### 8.4 Rate-limiting nginx — snippet à ajouter (PISTE 6)

```nginx
# Dans le bloc http { } (typiquement /etc/nginx/nginx.conf)
limit_req_zone $binary_remote_addr zone=api_general:10m rate=30r/s;
limit_req_zone $binary_remote_addr zone=api_ai:10m rate=5r/m;

# Dans le bloc server { } d'astroscan
location /api/ai/ {
    limit_req zone=api_ai burst=10 nodelay;
    proxy_pass http://127.0.0.1:5003;
    proxy_buffering off;
    # ... headers usuels
}

location /api/ {
    limit_req zone=api_general burst=60 nodelay;
    proxy_pass http://127.0.0.1:5003;
    # ... headers usuels
}
```

### 8.5 Headers HTTP renforcés — snippet nginx (PISTE 6)

```nginx
# Headers de sécurité — à appliquer dans le server { } HTTPS
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "geolocation=(self), microphone=()" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' https://cesium.com; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' https://api.cesium.com https://api.nasa.gov https://services.swpc.noaa.gov; frame-ancestors 'none'" always;
```

À tester progressivement — la CSP est notoirement difficile à calibrer du premier coup. Démarrer en `Content-Security-Policy-Report-Only` pour collecter 48 h de violations avant d'enforcer.

### 8.6 Script d'interview qualitative SneakerBot — version courte

Pour les 4 trial accounts non-convertis (PISTE 4, audit) :

```
Subject : Quick question about your SneakerBot trial

Hi [first name],

I noticed you signed up to SneakerBot a few [days/weeks] ago and gave
the trial a try. I'm the maker (single operator on this side, no
sales team). I'm not trying to sell you anything — but if you have
30 seconds, I'd genuinely value a one-line answer to:

  "What would have made SneakerBot worth 29 €/month for you?"

Your answer (even "nothing, I'm not the right user") is more useful
than 100 lines of analytics. No follow-up unless you want.

Thanks,
Zakaria
```

Adapter en FR si le trial parle FR :

```
Objet : Petite question sur ton essai SneakerBot

Salut [prénom],

J'ai vu que tu as testé SneakerBot il y a quelques jours/semaines.
Je suis le créateur (pas d'équipe commerciale, juste moi). J'essaie
pas de te vendre quoi que ce soit — mais si tu as 30 secondes, je
serais vraiment preneur d'une réponse d'une ligne à :

  "Qu'est-ce qui aurait rendu SneakerBot suffisant pour 29 €/mois
   à tes yeux ?"

Une réponse honnête (même "rien, je suis pas la bonne cible") est
plus utile que 100 lignes d'analytics. Aucune relance prévue, sauf
si tu veux échanger.

Merci,
Zakaria
```

Taux de réponse attendu : 25-50 %. Même 1 réponse honnête = signal directionnel actionnable.

### 8.7 KPI dashboard simple — fichier markdown à maintenir

Pour suivre l'avancement sur 30 jours sans setup complexe, un simple fichier `KPI_30D.md` à updater chaque dimanche :

```markdown
# KPI 30D — semaine du [date]

## Outreach (PISTE 1 + 2)
- Emails envoyés cette semaine : N
- Total cumulé : N
- Réponses reçues cette semaine : N (+ détail qui)
- Taux de réponse cumulé : N %
- RDV / calls planifiés : N
- Mentions publiques détectées : N (Google Alerts)

## Sécurité (PISTE 6)
- systemd-analyze score : X.X / 10 (objectif < 5.5)
- Items checklist DEPLOYMENT.md §14 : Y / 10 cochés
- Incidents de sécurité observés : N

## Production (ASTRO-SCAN)
- Uptime hebdo : N %
- Endpoints critiques 200 (sample 100 req) : 11/11 ?
- Tests CI passants : 51/51 (drift à surveiller)
- Sentry erreurs hebdo : N

## SneakerBot (PISTE 4)
- Nouveaux trials : N
- Conversions trial → paying : N
- Réponses interview qualitative : N / 4
- Hypothèse dominante (H1/H2/H3) : ?

## Décisions de la semaine
- [Décision 1]
- [Décision 2]

## Prochaine semaine — top 3 priorités
1. ...
2. ...
3. ...
```

10 minutes de mise à jour chaque dimanche = 7 h de visibilité préservée sur 30 jours. Coût/bénéfice imbattable.

### 8.8 Liste de contacts cibles — démarrage

À adapter au cas par cas (vérifier les emails actuels sur les sites institutionnels, les noms changent souvent).

**International — premier cercle (vague 1)**

| Organisation | Cible préférée | Channel privilégié | Notes |
|---|---|---|---|
| ESA Education | education@esa.int | Email | Formulaire web esa.int/Education aussi |
| UNAWE (Universe Awareness) | info@unawe.org | Email | Site unawe.org pour formulaire |
| IAU OAE (Office of Astronomy for Education) | Formulaire oae.iau.org/contact | Web form | OAE node coordinator par région |

**International — deuxième cercle (vague 2)**

| Organisation | Cible préférée | Channel | Notes |
|---|---|---|---|
| NASA Education | education@nasa.gov | Email | Réponse souvent automatique d'abord |
| JPL Education / Outreach | Formulaire jpl.nasa.gov/edu | Web form | |
| CNES Education | education@cnes.fr | Email | Cible francophone, devrait répondre |
| Astronomers Without Borders | info@astronomerswithoutborders.org | Email | Coordinateur régional plus efficace |
| Sky & Telescope (magazine) | Formulaire skyandtelescope.org/contact | Web form | Pour mention article éventuelle |
| Ciel et Espace (FR) | redaction@cieletespace.fr | Email | Cible francophone |

**Algérie — démarrage**

| Organisation | Cible préférée | Channel | Notes |
|---|---|---|---|
| Université Aboubekr Belkaïd Tlemcen | Doyen Faculté des Sciences | Visite physique + email | Décanat + chef département physique |
| CRAAG Bouzaréah | Direction | Courrier postal recommandé + email | craag@craag.dz (à vérifier) |
| USTHB Alger | Département physique | Email | Moins prioritaire que CRAAG |
| APAA Alger | Bureau | Facebook + email | Réseau amateur actif |

**Reporters / Bloggers astronomie francophones (J+15)**

À identifier au cas par cas via Google + Twitter/X. Cible : 5-10 noms. Par exemple : Eric Lagadec (CNRS Nice), Florence Porcel (vulgarisation YouTube), David Fossé (Ciel et Espace), Olivier Sanguy (CNES rédaction).

**Liste vivante — à enrichir au fil des suggestions des destinataires de vague 1.**

### 8.9 Argumentaire défensif — anticiper les objections probables

Pour chaque type de destinataire, voici les objections **probables** et la réponse honnête + courte. À mémoriser, pas à réciter.

**Destinataire institutionnel — objection 1** :
> "Vous n'avez aucune publication scientifique."

Réponse :
> "Correct. ORBITAL-CHOHRA est positionné comme observatoire de **diffusion** (public engagement / education), pas comme producteur de recherche primaire. La plateforme agrège des données scientifiques publiques (NASA, NOAA, ESA) et les rend accessibles dans une interface francophone unifiée. C'est un travail d'ingénierie au service de la science, pas de production de connaissance nouvelle."

**Destinataire institutionnel — objection 2** :
> "Comment êtes-vous différent de Stellarium / Heavens-Above / d'autres trackers existants ?"

Réponse :
> "Trois différenciateurs : (1) interface unifiée FR pour 5 verticales (ISS, weather, deep space, NEO, hilal) — la plupart des outils sont mono-vertical ; (2) calcul Hilal multi-critères (ODEH/UIOF/Oum Al Qura) qui est unique pour le monde musulman francophone ; (3) ancrage Maghreb explicite — décor mental différent pour notre audience cible. Ce n'est pas mieux ou moins bien que Stellarium — c'est destiné à un public différent."

**Destinataire institutionnel — objection 3** :
> "Quelle est votre garantie de continuité ? Vous êtes seul, donc bus factor = 1."

Réponse :
> "Vous avez raison, c'est le risque structurel. Atténuants : (a) le code est public (utilisable par n'importe qui), (b) les données viennent de sources publiques pérennes (NASA / NOAA / ESA — pas de dépendance propriétaire), (c) l'infrastructure est documentée (DEPLOYMENT.md) au point qu'un ingénieur tiers peut la reprendre en quelques jours. La discontinuité reste possible mais elle ne détruit pas l'œuvre."

**Destinataire reporter / blogger — objection** :
> "Pourquoi je vous donnerais 5 minutes ? Il y a 100 projets astronomy chaque mois."

Réponse :
> "Trois angles éditoriaux possibles : (1) 'Indépendant Tlemcen, Algérie' — angle Global South, peu couvert. (2) 'Calcul Hilal scientifique' — pertinence diaspora musulmane francophone. (3) 'De monolithe 12 000 lignes à architecture moderne en 3 semaines' — angle technique pour la communauté ingénieur. Vous choisissez l'angle qui parle à votre audience."

**Destinataire trial SneakerBot — objection** :
> "29 €/mois c'est trop cher."

Réponse :
> "Compréhensible. Avant de baisser le prix, j'aimerais comprendre : à quel prix le produit serait pour vous *intéressant* (pas seulement *abordable*) ? La réponse 'gratuit' est honnête et OK — ça nous dirait que le produit n'est pas adapté à votre usage."

### 8.10 Autocritique — ce que ce rapport ne couvre pas

Reconnaître les angles morts du présent rapport :

1. **Pas d'analyse coût financier précis** — le rapport ne chiffre pas en euros le coût d'opportunité. Ex : 1 jour de travail = ~150-300 € de tarif consultant équivalent ; investir 5 jours sur PISTE 3 = 750-1500 € d'opportunité. Pas inclus, mais à intégrer mentalement.

2. **Pas d'analyse fiscale Algérie** — si SneakerBot ou ASTRO-SCAN génèrent du revenu, les implications fiscales (TVA, impôts, déclaration entreprise) ne sont pas abordées. C'est hors scope mais à anticiper.

3. **Pas d'analyse compétitive SneakerBot** — quels sont les concurrents directs (Sole Retriever, NSB, etc.), à quel prix, avec quelle proposition de valeur ? Sans cette analyse, l'arbitrage prix dans PISTE 4 reste partiel.

4. **Pas de plan de communication coordonné** — le rapport traite outreach et acquisition séparément. À 30 jours, il faudrait un plan de comm. cohérent (qui est ORBITAL-CHOHRA ? quel ton ? quelle bio courte ?). Pas critique cette semaine.

5. **Pas de plan de gestion d'urgence** — que faire si la prod tombe pendant qu'un destinataire de pitch consulte le site ? À documenter (DEPLOYMENT.md §11 couvre les incidents génériques mais pas le scénario "incident pendant pitch").

6. **Pas d'analyse psychologique** — la motivation et l'énergie d'un single director sont des ressources finies. Le rapport est purement opérationnel ; les considérations de bien-être / soutenabilité (sommeil, sport, vie sociale) sont absentes alors qu'elles déterminent la viabilité d'un plan 7-jours.

7. **Pas d'évaluation de l'effet réseau** — l'effet d'une mention par un seul destinataire fort (ex. : un retweet IAU) peut transformer la dynamique au-delà de ce que le rapport modélise linéairement.

Ces angles morts ne disqualifient pas le plan — mais ils méritent une révision à J+30 quand les premières données réelles seront disponibles.

---

## 9. Conclusion

ASTRO-SCAN / ORBITAL-CHOHRA sort de PASS 21 dans un état technique solide : production stable, architecture propre, tests + CI/CD, documentation internationale. **Les conditions sont réunies pour démarrer un cycle d'outreach scientifique.**

La ressource limitante n'est ni le code ni la documentation — c'est la **bandwidth single director**. La discipline du focus l'emporte sur l'optimisme de l'agenda.

**Recommandation d'arbitrage final** :

> **Demain matin 08h30 : 3 emails outreach.**
> **Demain après-midi : drop privileges systemd.**
> **Le reste de la semaine : Algérie + audit SneakerBot.**
> **Pas d'architecture nouvelle. Pas de tests supplémentaires.**

Le travail de ces 7 jours sera évalué à J+30 sur les indicateurs §5. Toute réponse outreach positive change l'équilibre — préserver une marge pour itérer.

---

## 10. FAQ — questions probables sur ce rapport

**Q1 — Pourquoi seulement 3 emails demain et pas 10-20 ?**

Trois emails permettent de :
- Personnaliser intensément chaque message (15-20 min/destinataire de réflexion).
- Itérer le wording avant la vague 2 (50-80 % du gain de vague 2 vient des leçons de vague 1).
- Préserver la santé mentale (envoyer 20 et avoir 0 réponse à J+5 est démoralisant ; avoir 3 emails ouvre une fenêtre d'attente plus saine).

20 emails de masse = stratégie de spammeur, sans offre de valeur claire. 3 emails ciblés = stratégie de relation, conforme aux conventions institutionnelles.

**Q2 — Pourquoi pas SneakerBot en priorité 1 ? C'est là que sont les revenus.**

Triple raison :
- **20 jours de TikTok actif → 0 conversion** signale un problème de produit ou positionnement, pas seulement d'acquisition. Investir plus en acquisition sans diagnostic = jeter du temps.
- **0.5 j d'audit funnel** cette semaine donne le diagnostic nécessaire. Reprise prioritaire à S+1 si l'audit révèle un actionable simple.
- ASTRO-SCAN PISTE 1 est un **strategic play** au upside non-borné. Un seul retour positif (mention IAU OAE, reprise par UNAWE) change le positionnement long terme.

Ce n'est pas "ASTRO-SCAN > SneakerBot". C'est "audit avant intensification". Le revenu reste l'objectif business.

**Q3 — Hardening en 1 jour, c'est réaliste ?**

Le breakdown :
- Préparer terrain (audit chemins, créer user) : 45 min.
- Drop privileges + sandboxing systemd + restart + smoke test : 60-90 min.
- Nginx rate-limiting + headers + reload : 60 min.
- Rotation tokens + audit final : 30 min.
- **Tampon imprévu** : 60-90 min (chemin en dur découvert, rollback, retry).

Total : 4-5 h actives, étalées sur une journée pour permettre observation après chaque étape. C'est tendu mais réaliste si on commence à 13 h après la matinée outreach.

Si à 17 h le hardening n'est pas terminé : pause, finir jour 2 matin avant outreach Algérie. Ne JAMAIS forcer un drop privileges fatigué — risque d'incident.

**Q4 — Pourquoi pas pitcher Airbus, JPL Engineering, NASA Ames missions ?**

Trois raisons :
- **Mauvaise cible** : ce sont des programmes opérations / classifiés. ORBITAL-CHOHRA est une plateforme civile éducative. Mauvais match.
- **Contraintes export** : ITAR/EAR rendent un pitch "from Algeria" plus complexe pour ces destinataires. Pas impossible, mais pas adapté à la phase actuelle.
- **Crédibilité institutionnelle** : pour ces programmes, l'absence de chercheur affilié et de publi est disqualifiante. Pour les programmes Education / Outreach, c'est neutre.

À reprendre à 12-24 mois avec un sponsor institutionnel formel (CRAAG par exemple). Pas avant.

**Q5 — Que faire si je reçois une réponse positive très exigeante (ex. : "envoyez une démo live demain") ?**

Trois étapes :
- **Acquittez en 4 h max** ("Yes, I can do a live demo. Could we schedule [3 dates]?").
- **Préparez la démo** : 30 min de pratique, scénario écrit (5 features × 1 min), backup screen recording si la live capote.
- **Faites la démo en mode "show, don't tell"** : montrer 5 features au lieu d'expliquer 50.

Ne pas reporter sous prétexte que le hardening n'est pas fini. Une opportunité ratée vaut moins qu'un site moins-que-parfait pendant 30 min de démo.

**Q6 — Ce rapport est long. Combien de temps faut-il vraiment lui accorder ?**

Lecture utile : ~15-20 minutes (executive summary §0, recommandations §4, tableau §6).
Référence détaillée : utiliser comme document de consultation, pas comme lecture linéaire.
Mise à jour : compter ~30 min/mois pour tenir KPI dashboard §8.7.

**Q7 — Faut-il informer SneakerBot ou ASTRO-SCAN audience que le focus change ?**

Non. Aucune communication externe sur le pivot interne. La communication externe doit rester **product-focused** (nouvelles fonctionnalités, données, événements astro), pas **operational-focused** (réorganisation interne du planning).

Exception : si tu lances une initiative publique (ex. : "ORBITAL-CHOHRA cherche des stagiaires pour 2026"), c'est de la communication produit/programme, pas opérationnelle. OK.

**Q8 — Que faire si à J+7 aucun des plans B/C/D/E n'est nécessaire mais aucun gros succès non plus ?**

C'est le scénario **modal** (le plus probable). Indicateurs typiques :
- 3 emails partis, 0-1 réponses (normal vu cycle).
- Hardening fait.
- Algérie : RDV pris à J+10-J+14.
- SneakerBot audit : 1-2 hypothèses, pas de pivot urgent.

Action S+2 :
- Vague 2 outreach (12 emails additionnels).
- RDV Algérie tenu.
- Selon audit : décision SneakerBot (intensifier / pivot / pause).
- Tampon : 1 j pour imprévu / fonctionnalité ASTRO-SCAN demandée par feedback.

Ne pas paniquer, ne pas accélérer, ne pas ralentir. **Maintenir le rythme.**

**Q9 — Et si la branche `migration/phase-2c` n'est pas pushée sur GitHub avant lundi ?**

Push le. Tu dois pouvoir donner un lien GitHub public (au minimum read-only) dans les emails outreach. Sinon les destinataires institutionnels pensent que "code privé / propriétaire / vapor-ware".

Action 5 min : `git push origin migration/phase-2c`. Faire une PR vers `main` aussi, pour avoir un historique propre. Vérifier qu'aucun secret n'a été push (`.env` est dans `.gitignore`, à confirmer).

**Q10 — Le tag GitHub `phase-2c-tests-ok` doit-il être créé ?**

Oui. Convention établie : chaque jalon technique stable a son tag permanent. Après push de PASS 21 :

```bash
git tag phase-2c-tests-ok
git push origin phase-2c-tests-ok
```

Tag de plus à la liste des 7 existants (80pct, 95pct, 97pct, bascule-ok, cleanup-ok, docs-complete) → 8 tags. Démontre une discipline release pour les revues techniques.

---

## 11. Notes de mise à jour de ce rapport

| Date | Trigger | Sections à mettre à jour |
|---|---|---|
| J+7 (10/05) | Bilan semaine 1 | §4.4 (réviser plan S+1), §5 (KPIs), §10 (FAQ avec apprentissages) |
| J+30 (02/06) | Bilan mois 1 | §1.5 (recalibrer P(succès) selon retours réels), §3 (ajuster scores), §4 (réviser priorités), §6 (renouveler tableau décisionnel) |
| J+60 (02/07) | Bilan trimestre | Réécrire le rapport intégralement si > 50 % des hypothèses sont invalidées |
| Toute réponse outreach majeure | Imprévu | §4.7 (plans B/C/D/E selon nature de la réponse) |
| Tout incident production | Imprévu | §1.6 (réviser carte forces/faiblesses), §11 plans contingence |

Ce rapport n'est **pas figé**. Le maintenir vivant lui donne valeur ; le laisser obsolète le rend nuisible.

---

*Rapport généré le 03/05/2026 à 22:30 UTC+1 (Tlemcen, Algérie).*
*Pour le Director Zakaria Chohra, ORBITAL-CHOHRA Observatory.*
*Document de travail interne — à mettre à jour à chaque jalon.*
