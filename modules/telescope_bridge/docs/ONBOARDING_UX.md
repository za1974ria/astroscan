# Telescope Bridge — Onboarding UX (V1)

Objectif : un astronome amateur passe de **rien** à **télescope visible dans
le dashboard** en moins de 5 minutes, sans ouvrir de port sur sa box.

## Flux en 5 étapes

### Étape 1 — Dashboard : créer un pairing

L'utilisateur clique sur "Connecter un télescope" depuis le portail.
Modal affiche :
- code 6 chiffres (gros, lisible)
- QR code contenant `astroscan://pair?code=479201`
- compte à rebours 10 minutes
- texte : "Saisissez ce code dans le Bridge Agent sur votre PC d'observatoire."

### Étape 2 — Téléchargement de l'agent

Sous le code, 3 boutons :
- **Windows (.msi)** — agent + dépendances bundlées via PyInstaller
- **Linux .deb (amd64 / arm64)** — paquet pour Ubuntu / Debian / Raspberry Pi OS
- **Source (.tar.gz)** — pour macOS et autres distros

Chaque téléchargement est signé (Authenticode pour msi, gpg pour deb).
La page rappelle l'empreinte SHA-256 attendue.

### Étape 3 — Installation

**Windows** : double-clic msi → service `AstroScanBridge` créé (NSSM ou
sc.exe), démarrage automatique au login.

**Linux** : `sudo apt install ./astroscan-bridge_0.1.0_amd64.deb` →
service utilisateur systemd `astroscan-bridge.service` enregistré.

**Aucun** prompt sudo lors du fonctionnement nominal — l'agent n'a besoin
d'aucune permission root après installation.

### Étape 4 — Premier lancement de l'agent

L'agent ouvre une fenêtre console (Windows) ou affiche dans le journal
(Linux) :

```
AstroScan Bridge Agent v0.1.0
No pairing found. Please enter your AstroScan pairing code:
> 479201
[OK] paired as agent_id=…
[OK] credentials stored in OS keychain
Scanning for telescope ecosystems…
  - Alpaca discovery on 32227/udp …
  - INDI server on localhost:7624 …
[OK] discovered 2 device(s): mount (EQ6-R Pro), camera (ASI2600MM)
[OK] streaming telemetry to https://astroscan.space
```

L'utilisateur peut fermer la console : le service tourne en arrière-plan.

### Étape 5 — Retour au dashboard

Dashboard détecte que la session est passée à `paired` (heartbeat reçu).
La modal "Connecter un télescope" se ferme automatiquement, et la liste
des devices apparaît :

```
[●] EQ6-R Pro          mount      online   2 s ago
[●] ASI2600MM           camera     online   2 s ago
                                                       [ Disconnect ]
```

Cliquer sur un device ouvre la fiche télémétrie (Phase 6).

## États d'erreur visibles

| Symptôme | Cause | Action utilisateur |
|---|---|---|
| Compte à rebours arrive à 0 sans confirmation | code expiré | Cliquer "Régénérer un code" |
| Agent affiche `code_already_consumed` | code déjà utilisé | Régénérer |
| Agent affiche `discovery failed: no devices` | Alpaca/INDI pas lancé | Démarrer ASCOM Remote / indiserver |
| Dashboard reste sur "aucun device" 1 min après pairing OK | l'utilisateur n'a pas démarré son driver | Lien vers FAQ "Configurer ASCOM Remote / INDI" |
| Bandeau rouge "Agent offline" | pas de heartbeat depuis 90 s | Vérifier PC observatoire allumé / réseau |

## Consentement granulaire

Dès qu'un device est découvert, le dashboard demande **explicitement** :
- ☐ Lire la position (RA/Dec) ?
- ☐ Lire l'état tracking ?
- ☐ Lire la température caméra ?
- ☐ Partager les coordonnées du site (lat/lon) ? *Non par défaut.*
- ☐ Partager l'état météo si station connectée ?

Tant qu'une case n'est pas cochée, l'agent reçoit dans son
`/session/heartbeat` la liste des propriétés autorisées et **filtre
lui-même** ce qu'il lit / envoie. Double défense : l'agent filtre, le
serveur rejette si une propriété non-autorisée arrive quand même.
