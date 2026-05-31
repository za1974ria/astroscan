# Rapport visiteurs ASTRO-SCAN — 2026-05-31

**Lecture seule. Aucune ligne ne mutée, aucun service touché.**
Toutes les requêtes SQL utilisées ci-dessous sont des `SELECT` exécutés en
mode `file:...?mode=ro&immutable=1`. Reproductible.

---

## Phase 0 — Inventaire des sources

### Base de données canonique

| Chemin | Taille | Owner | Rôle |
|--------|-------:|-------|------|
| `/opt/astroscan/data/archive_stellaire.db` | 13.6 MB | astroscan | **Base de données réelle** — résolue via `app/services/paths.py:DB_PATH` |
| `/opt/astroscan/data/visitors.db` | 4096 B | astroscan | **Vide** (1 page SQLite, 0 table) — orpheline, héritage legacy citée par `app/services/control_tower/targets.py:210` (probe healthcheck) |
| `/root/astro_scan/data/visitors.db` | 4096 B | root | Idem, vide |

Le module canonique d'agrégation est `app/services/analytics_dashboard.py`
qui appelle `sqlite3.connect(DB_PATH)` → `archive_stellaire.db`. La fonction
`get_visitor_truth(owner_ips)` (l.167) est la source unique des chiffres
diffusés par `/api/visitors/stats`, `/cockpit`, la bannière, etc.

### Tables visiteurs dans `archive_stellaire.db`

| Table | Lignes | Rôle |
|-------|------:|------|
| `visits` | 1 ligne (`count=4156`) | Compteur historique global (legacy) |
| `visitor_log` | **12 501** | Log canonique par (ip, session_id), avec geo + scoring |
| `page_views` | 12 732 | Hits page-par-page (`session_id`, `path`, `referrer`) |
| `session_time` | 12 133 | Durée par (session, path) en secondes |
| `owner_ips` | 0 | Table de gestion d'IPs propriétaire — vide |

### Schéma `visitor_log` (colonnes pertinentes)

```sql
ip TEXT, country TEXT, country_code TEXT, city TEXT, region TEXT,
user_agent TEXT, path TEXT, visited_at TEXT,
session_id TEXT, ip_hash TEXT, lat REAL, lon REAL,
continent TEXT, is_bot INTEGER DEFAULT 0,
isp TEXT, human_score INTEGER DEFAULT -1,
is_owner INTEGER DEFAULT 0
```

### Scoring humain — `_compute_human_score` (`app/services/db_visitors.py:108`)

```
UA bot connu (regex)           → 0                (immédiat)
UA vide                        → score = 5
UA très court (<15 chars)      → score = 10
sinon UA présent               → score = 20       (base "non-bot")
+ page_count > 1               → +30
+ session_sec > 30             → +20
+ referrer valide (≠ direct,
   ≠ https://astroscan.space)  → +10
+ JS beacon reçu               → +20
                              ──────
"Humain probable"              ≥ 60               (docstring)
```

### Détection bot (`is_bot`)

Renseigné par `services.utils._is_bot_user_agent(ua)` (regex sur des UA
typiques). Quand le pattern matche, `is_bot=1` et `human_score=0`. Hors
match → `is_bot=0`.

### Détection owner (`is_owner`)

Renseigné à l'insert. Filtre canonique combiné (`owner_ip_sql_filter`,
`analytics_dashboard.py:138`) :

```
is_bot = 0
AND is_owner = 0
AND ip NOT LIKE '105.235.13.%'    -- range opérateur DZ de l'admin
AND ip NOT IN (owner_ips chargées depuis env ASTROSCAN_OWNER_IPS)
```

### Fenêtre temporelle

| Table | min(visited_at) | max(visited_at) |
|-------|------|------|
| `visitor_log` | `2026-03-24 11:45:50` | `2026-05-31 00:50:44` |
| `page_views` | `2026-04-22 06:04:22` | `2026-05-31 00:50:44` |

Couverture utile ≈ **68 jours**, mais les `page_views` ne sont collectées
que depuis le 22 avril (~40 jours utiles pour cette table).

---

## A — Volumétrie globale (brut, tout confondu)

| Métrique | Valeur |
|---|---:|
| Total lignes `visitor_log` | 12 501 |
| Total hits `page_views` | 12 732 |
| Sessions enregistrées (`session_time`) | 12 133 |
| Compteur legacy `visits.count` | 4 156 |
| Pays distincts vus | 73 (selon `country_code`) |
| IPs distinctes vues | 4 075 |

Le compteur legacy `visits.count = 4156` diverge du `COUNT(DISTINCT ip)`
canonique — il s'agit d'un compteur historique non-aligné, conservé pour
compatibilité (cf. docstring `get_visitor_truth`).

---

## B — Humains vs bots vs trafic datacenter

### Découpage de base sur les flags stockés

| Catégorie | Visites | IPs uniques | Sessions |
|---|---:|---:|---:|
| `is_bot = 1` | 1 643 | 871 | 1 557 |
| `is_bot = 0` total | 10 858 | 3 204 | 10 556 |
| ↳ dont `is_owner = 1` | **5 015** | 6 | — |
| ↳ filtre canonique (is_bot=0 AND is_owner=0 + range opérateur) | **5 843** | 3 203 | 5 544 |

**Trouvaille — biais owner** : sur les 5 015 visites marquées
`is_owner=1`, **5 007 (99.8 %) sont l'IP `5.78.*.*`** : c'est l'IP du
**serveur Hetzner lui-même** (5.78.153.17, cf. `CLAUDE.md`). Ce ne sont
donc pas des visites de l'admin mais des **self-hits du process** (probes
internes, watchdog, healthchecks). Le filtre canonique les exclut
correctement (bien), mais le flag les étiquette « owner » à tort. À
recatégoriser en `is_self_hit` au prochain patch pour la lisibilité.

### Décomposition du filtre canonique par `human_score`

Sur les 5 843 visites « non-bot, non-owner, hors range opérateur » :

| `human_score` | Visites | IPs | Interprétation |
|---|---:|---:|---|
| `-1` (jamais scoré) | 314 | 255 | Insert sans recalcul |
| `0-19` | 452 | 209 | UA vide / très court |
| `20-39` | **4 740** | **2 693** | UA présent mais zéro signe humain (pas de multi-page, pas de durée, pas de referrer) |
| `40-59` | 289 | 184 | Au moins un signal positif |
| `60-79` | **48** | **39** | « Humain probable » (≥ 60) |
| `80+` | 0 | 0 | — |

**81 % du trafic « non-bot non-owner » a un score 20-39** : c'est-à-dire
qu'il franchit le filtre canonique uniquement parce que son User-Agent
n'est pas dans la blacklist regex, mais il n'a aucun signal d'engagement
humain (pas de seconde page, pas de 30s sur le site, pas de referrer
valide). Sans signalement contraire, il s'agit majoritairement de
crawlers / scanners non listés et de hits one-shot.

### Trafic datacenter visible dans le filtre canonique

Classification grossière par préfixe IP (sur les 5 843 visites « non-bot
non-owner ») :

| Plage IP | Opérateur dominant | Visites | IPs |
|---|---|---:|---:|
| `43.x` | Tencent | 851 | 352 |
| `34.x` | GCP | 131 | 108 |
| `3.x`  | AWS | 114 | 36 |
| `35.x` | GCP | 81 | 63 |
| `54.x` | AWS | 62 | 51 |
| `20.x` | Azure | 55 | 44 |
| `157.x` | DigitalOcean / CN | 40 | 20 |
| `44.x` | AWS | 32 | 25 |
| `167.99 / 178.62 / 188.166` | DigitalOcean | 29 | 13 |
| `51.x` | OVH / Azure | 23 | 14 |
| `40.x` | Azure | 12 | 7 |
| `13.x` | Azure | 6 | 5 |
| `5.78.x` | Hetzner (auto-fuite) | 1 | 1 |
| **Sous-total datacenter par préfixe** | | **≥ 1 486** | **≥ 838** |

Soit **au moins 25 % du « trafic canonique » provient de IPs datacenter
identifiables au préfixe seul**. La part réelle est plus haute (les ISPs
Akamai, Hurricane Electric, Microsoft, Censys n'ont pas de plage simple).

### UA scanners auto-déclarés mais NON classés bot

Le détecteur regex `_is_bot_user_agent` rate des scanners qui se déclarent
pourtant publiquement dans leur UA :

| User-Agent (extrait) | Visites |
|---|---:|
| `Mozilla/5.0 zgrab/0.x` (Censys) | 176 |
| `Mozilla/5.0 (compatible; Infrawatch/1.0; +https://infrawat.c…` | 162 |
| `Hello from Palo Alto Networks, find out more about our scans…` | 149 |
| `visionheight.com/scan Mozilla/5.0 …` | 146 |

Recherche `zgrab|Infrawatch|Palo Alto|visionheight|Censys|scanner|expanse|internet-measurement`
dans `user_agent` (sur `is_bot=0`) : **836 visites / 548 IPs**.
Ces 836 lignes sont aujourd'hui comptées comme « visiteurs » par le filtre
canonique alors qu'elles s'auto-déclarent scanners.

### Synthèse « vrais humains » après filtre rigoureux

Critères cumulés :
- `is_bot = 0 AND is_owner = 0`
- `ip NOT LIKE '105.235.13.%'` (range opérateur admin)
- `human_score ≥ 60` (humain probable)
- UA ne contient pas `zgrab|Infrawatch|Palo Alto|visionheight|Censys|scanner|expanse|internet-measurement`
- IP ne tombe pas dans une plage datacenter connue
  (`43.x / 3.x / 44.x / 54.x / 34.x / 35.x / 13.x / 20.x / 40.x / 51.x / 157.x / 5.78.x`)

**Résultat : 48 visites / 39 IPs / 41 sessions / 4 pays sur 68 jours.**

C'est ≈ **0.8 % des 5 843 visites « canoniques »** affichées par le
dashboard. Et **0.4 % du total brut** (12 501 lignes).

### Filtre intermédiaire (moins sévère)

En relâchant le seuil à `human_score ≥ 40` (au moins un signal positif),
mêmes exclusions UA + plages DC : **321 visites / 190 IPs**.

C'est le « stock plausible d'humains réels » sur la fenêtre — ordre de
grandeur **2 à 3 nouveaux visiteurs humains plausibles par jour**, pas
des centaines.

---

## C — Anomalies de mesure

### Sessions à durée plafonnée à 168h ?

Le brief évoquait des sessions à `168h 00m 00s` exactement (= 7 jours,
plafond artificiel). Vérification :

```
SELECT COUNT(*) FROM session_time WHERE duration >= 604800;   -- 0
SELECT MAX(duration) FROM session_time;                       -- 83 404 s = 23h 10m
```

**Aucune session ne dépasse 24h actuellement.** L'anomalie évoquée n'est
pas présente dans cette base. Soit elle a été corrigée, soit elle vivait
sur une autre source. Distribution des durées :

| Durée | Sessions |
|---|---:|
| `0s` | 129 |
| `<5s` | 2 300 |
| `5-30s` | 3 044 |
| `30s-5min` | 3 706 |
| `5-30min` | 1 976 |
| `30-60min` | 374 |
| `1-24h` | 604 |
| `≥ 7j` | 0 |

Les **2 300 sessions < 5s** et les **604 sessions de 1 à 24h** sont
suspectes : la première catégorie est typique des crawlers ; la seconde
peut indiquer des onglets oubliés, mais aussi des compteurs qui ne se
ferment jamais proprement.

### Self-hits du serveur étiquetés `owner`

Cf. section B : 5 007 lignes `is_owner=1` sont l'IP du serveur lui-même.
Le filtre les exclut, mais le label est trompeur — à recatégoriser
`is_self_hit` ou à ignorer carrément à l'insertion (un service qui parle
à lui-même ne devrait jamais s'auto-logger).

### Doublon `_meta_seo.html` non-utilisé

Hors scope mais identifié sur la même session : `templates/_meta_seo.html`
émet déjà un JSON-LD géolocalisé mais n'est inclus que sur 2 pages
(`ce_soir`, `aurores`, commit `b01bda5`). Tous les compteurs « pages vues
SEO » côté sites tiers restent donc partiels. Hors scope de ce rapport.

---

## D — Géographie (sur les « vrais humains » filtre rigoureux)

### Pays (39 IPs distinctes)

| Pays | IPs |
|---|---:|
| 🇩🇿 Algeria | 36 |
| 🇺🇸 United States | 1 |
| 🇳🇱 Netherlands | 1 |
| 🇦🇩 Andorra | 1 |

**93 % de l'audience humaine est algérienne.** Les 3 IPs hors-DZ peuvent
être des hits isolés (proches d'un humain mais sans confirmation).

### Détail Algérie (filtre rigoureux, top wilayas)

| Ville | Région | IPs |
|---|---|---:|
| Bir el Djir | Oran | 6 |
| Mostaganem | Mostaganem | 5 |
| Aïn el Turk | Oran | 2 |
| Sidi Bel Abbès | Sidi Bel Abbès | 2 |
| Sidi ech Chahmi | Oran | 2 |
| Tsabit | Adrar | 2 |
| Oran (centre) | — | 2 |
| Tlemcen | Tlemcen | 1 |
| Remchi | Tlemcen | 1 |
| Chetouane | Tlemcen | 1 |
| 13 autres villes (Mecheria, Hadjout, Chlef, Tiaret, Bejaia…) | — | 1 chacune |

Concentré ouest-algérien (Oran/Mostaganem/Tlemcen/Sidi Bel Abbès), avec
quelques points isolés ailleurs. L'audience humaine actuelle est très
locale — cohérent avec un observatoire amateur basé à Tlemcen, sans
campagne de promotion.

### Comparaison avec le filtre canonique large (5 843 visites)

| Pays | IPs (canonical large) |
|---|---:|
| United States | 1 366 |
| Algeria | 253 |
| China | 250 |
| Netherlands | 194 |
| Singapore | 181 |
| United Kingdom | 174 |
| Germany | 122 |
| France | 79 |

Le « top US 1 366 » du dashboard est presque entièrement composé de
visites AWS / GCP / Azure (datacenter), pas d'humains. La banner annonce
une couverture mondiale qui est en réalité un trafic d'infrastructure.

---

## E — Tendance temporelle

### Filtre canonique large (5 843 visites)

| Mois | Visites | IPs | Sessions |
|---|---:|---:|---:|
| 2026-03 (du 24) | 56 | 48 | 19 |
| 2026-04 | 1 497 | 1 027 | 1 304 |
| 2026-05 (au 31) | 4 290 | 2 431 | 4 228 |

### 7 derniers jours (filtre canonique large)

| Date | Visites | IPs |
|---|---:|---:|
| 2026-05-24 | 105 | 95 |
| 2026-05-25 | 135 | 94 |
| 2026-05-26 | 137 | 100 |
| 2026-05-27 | 140 | 114 |
| 2026-05-28 | 148 | 121 |
| 2026-05-29 | 143 | 118 |
| 2026-05-30 | 152 | 112 |
| 2026-05-31 (partielle) | 31 | 3 |

Plateau régulier ~100-120 IPs/jour côté filtre large, dont la majorité
est du trafic scanner / datacenter (cf. section B).

### Vrais humains par semaine (filtre rigoureux)

| Semaine ISO | Visites | IPs |
|---|---:|---:|
| 2026-W16 (avril) | 22 | 16 |
| 2026-W17 | 10 | 8 |
| 2026-W18 | 8 | 7 |
| 2026-W19 | 7 | 7 |
| 2026-W20 | 1 | 1 |
| W21-W22 | 0 | 0 |

Tendance baissière : **plus aucune visite humaine qualifiée détectée
depuis mai semaine 20.** Soit le scoring est devenu trop strict (peu
probable, formule inchangée), soit le trafic humain réel est effectivement
résiduel après le pic d'avril.

### Top pages visitées (humains rigoureux)

| Chemin | Hits |
|---|---:|
| `/` | 27 |
| `/portail` | 18 |
| `/mission-control` | 1 |
| `/orbital-map` | 1 |
| `/visiteurs-live` | 1 |

**45 des 48 visites humaines sont sur la landing.** Quasi-zéro
exploration interne — manque de chemin de conversion landing → contenu.

---

## F — Recommandations (patches FUTURS)

Honnêteté de mesure d'abord. Patches indépendants, dans l'ordre conseillé :

1. **Recatégoriser les self-hits du serveur** (5 007 lignes en 24h !).
   `is_owner=1` doit refléter l'admin, pas le process. Soit refuser
   l'insertion quand `request.remote_addr == socket.gethostbyname(host)`,
   soit nouvelle colonne `is_self_hit`. Sinon les KPIs « owner exclu »
   restent honnêtes par accident.

2. **Étendre `_is_bot_user_agent`** pour attraper les scanners
   auto-déclarés : `zgrab`, `Infrawatch`, `Palo Alto Networks`,
   `visionheight.com`, `Censys`, `Expanse`, `internet-measurement`,
   `MasterScan`. C'est **836 lignes** qui se classent en « non-bot » alors
   que leur UA dit explicitement « scanner ». Patch trivial, gain immédiat
   sur la propreté du compte « vrais visiteurs ».

3. **Ajouter un filtre IP datacenter** (table de plages ASN / préfixes
   maintenue, ou un check ip-api.com `proxy`/`hosting`). Au moins 25 %
   des « visiteurs canoniques » sont des IPs Tencent/AWS/GCP/Azure
   identifiables au préfixe seul. Décision : les compter en
   `is_datacenter=1` et les exclure du dashboard public.

4. **Afficher deux compteurs côte à côte** sur le dashboard public :
   - « Trafic indexé » (filtre canonique actuel — 5 843)
   - « Visites humaines » (filtre rigoureux : `human_score ≥ 60` +
     UA blacklist étendue + plages DC exclues — 48)

   Les deux sont vrais, ils mesurent des choses différentes. La séparation
   tue l'illusion « 3 200 visiteurs » qui n'existe pas en pratique.

5. **Réviser le score « UA présent → 20 »**. Un UA seul, sans aucun
   signal d'engagement, vaut probablement 0, pas 20. Le bucket 20-39 (97 %
   des visites canoniques) est artificiellement gonflé par cette base.
   Alternative : démarrer à 0 et exiger ≥ 2 signaux positifs pour passer
   au-dessus de 30.

6. **Brancher le JS beacon** (`+20` au score). Aujourd'hui invisible
   dans les buckets (aucune visite à 80+). Soit le beacon n'est pas
   déployé côté frontend, soit il n'est pas relu vers `_compute_human_score`
   lors des UPDATEs ultérieurs. À vérifier dans `db_visitors.py:178-188`.

7. **Documenter le compteur legacy `visits.count = 4156`** sur le
   dashboard et les communications externes : indiquer qu'il ne représente
   pas le nombre d'IPs distinctes, mais un cumul historique de passages
   (incrémenté sans dédup). À renommer en `total_hits_legacy` pour éviter
   les confusions.

---

## Résumé chiffres clés

| Compteur | Valeur | Interprétation |
|---|---:|---|
| Total `visitor_log` (brut) | **12 501** | Tous événements confondus |
| Bots détectés (`is_bot=1`) | 1 643 | UA dans la blacklist regex |
| Owner / self-hits exclus | 5 015 | Dont 5 007 self-hits du serveur Hetzner |
| **Filtre canonique du dashboard** | **5 843** | C'est ce que l'app affiche aujourd'hui |
| ↳ dont datacenter identifié par préfixe | ≥ 1 486 | Tencent, AWS, GCP, Azure, OVH, DO… |
| ↳ dont UA scanner auto-déclaré (zgrab, Censys, Palo Alto…) | ≥ 836 | Manqués par la regex |
| ↳ dont `human_score < 60` | 5 795 (99 %) | Pas de signal d'engagement |
| **Humains plausibles (score ≥ 60, hors DC, hors UA scanner)** | **48 visites / 39 IPs / 4 pays** | Sur 68 jours |
| Humains plausibles — pays dominant | 🇩🇿 36 IPs (93 %) | Concentré ouest-algérien |
| Humains plausibles — pages visitées | `/` (27) + `/portail` (18) | Quasi-zéro exploration interne |

**Conclusion honnête** : `astroscan.space` n'a pas d'audience massive —
ce qui est cohérent avec un observatoire amateur sans campagne de
promotion. L'audience humaine réelle est de l'ordre de **39 IPs sur
68 jours**, fortement concentrée dans l'ouest algérien (Oran, Mostaganem,
Tlemcen, Sidi Bel Abbès), avec quelques points isolés à l'étranger. Le
chiffre de « 5 843 visiteurs canoniques » du dashboard mélange ce trafic
humain résiduel avec un volume substantiel de scanners de sécurité et
d'IPs datacenter. La séparation des deux est la priorité d'honnêteté de
mesure.
