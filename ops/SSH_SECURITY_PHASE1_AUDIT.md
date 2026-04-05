# Phase 1 — Audit SSH (lecture seule)

**Date** : 2026-04-04  
**Règle** : aucune modification de configuration SSH dans ce document.

## 1. Fichier `sshd_config` et includes

| Directive | État effectif (audit) |
|-----------|------------------------|
| **Port** | 22 (défaut, `#Port 22` commenté) |
| **PermitRootLogin** | `yes` (fichier principal `/etc/ssh/sshd_config` ligne ~42) |
| **PasswordAuthentication** | `yes` (fichier **`/etc/ssh/sshd_config.d/50-cloud-init.conf`** — prioritaire pour cette valeur) |
| **PubkeyAuthentication** | `#PubkeyAuthentication yes` commenté → **valeur par défaut OpenSSH : activée** |
| **KbdInteractiveAuthentication** | `no` |

**Include** : `Include /etc/ssh/sshd_config.d/*.conf` (chargé en tête du fichier principal).

## 2. Clés et permissions `/root/.ssh`

| Élément | Constat |
|---------|---------|
| **Répertoire** | `drwx------` (700) — **correct** |
| **authorized_keys** | `-rw-------` (600) — **correct** |
| **Nombre de clés** | 1 entrée dans `authorized_keys` |
| **Clés locales** | Présence de `id_ed25519` / `id_ed25519.pub` (paire sur le serveur) |

**Risque** : exposition du contenu exact des clés dans les journaux — ne pas recopier les clés publiques dans des canaux non sécurisés.

## 3. Session / contexte (instantané audit)

| Info | Valeur observée |
|------|-----------------|
| Utilisateur | `root` |
| Connexion | `sshd` depuis IP externe (session type `notty` possible — automation/IDE) |

**Accès alternatif** : non vérifiable automatiquement (console hébergeur, autre session). **À confirmer manuellement** avant tout durcissement.

## 4. Fail2ban (jail `sshd`)

- Jail **active** ; IPs bannies présentes (comportement normal sous attaque/bruteforce).

## 5. Synthèse risques & faisabilité

| Risque | Niveau |
|--------|--------|
| Lockout si `PasswordAuthentication no` sans clé valide testée | **Critique** si appliqué trop tôt |
| `PermitRootLogin` restrictif sans clé root testée | **Élevé** |
| Modifier `sshd` + erreur de syntaxe | **Élevé** (coupe tout accès sauf console) |

**Faisabilité sans lockout** : **oui**, à condition de :
1. Ne jamais désactiver le mot de passe avant **deux** preuves : nouvelle session SSH par clé **réussie** + garde-fou (session/mot de passe encore possible).
2. Toujours garder une session SSH ouverte ou un accès console avant redémarrage `ssh`.

**État actuel** : authentification par clé **déjà possible** si un client possède la clé privée correspondant à l’entrée `authorized_keys` ; mot de passe **toujours** disponible tant que `PasswordAuthentication yes`.
