# Phase 5 — Durcissement SSH (PROPOSITION UNIQUEMENT — NON APPLIQUÉ)

**Ne pas appliquer automatiquement.** Validation humaine + test clé réussi + accès console requis.

## Modifications proposées (après validation)

| Paramètre | Valeur proposée | Risque si mal appliqué |
|-----------|-----------------|-------------------------|
| `PasswordAuthentication` | `no` | Lockout si clé absente ou refusée |
| `PermitRootLogin` | `prohibit-password` | Perte accès root SSH si aucune clé valide pour root |

## Rollback immédiat (fichiers)

Dans `/etc/ssh/sshd_config.d/50-cloud-init.conf` ou fichier créé pour le durcissement :

```text
PasswordAuthentication yes
```

Dans `/etc/ssh/sshd_config` (section Authentication) :

```text
PermitRootLogin yes
```

Puis :

```bash
sshd -t && systemctl reload ssh
```

(Utiliser le nom d’unité réel : `ssh` ou `sshd` selon `systemctl status`)

## Rappel

- **Jamais** désactiver le mot de passe sans **nouvelle session SSH testée avec la clé**.
- Garder une session ouverte **jusqu’à** confirmation du test.
