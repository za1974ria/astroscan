# SSH durci — 2026-04-04

## Fichiers modifiés

| Fichier | Changement |
|---------|------------|
| `/etc/ssh/sshd_config.backup` | Copie de secours (idem demande utilisateur) |
| `/etc/ssh/sshd_config.backup.20260404_*` | Copie horodatée |
| `/etc/ssh/sshd_config` | `PermitRootLogin prohibit-password` (l.42) ; suppression doublons fin de fichier |
| `/etc/ssh/sshd_config.d/50-cloud-init.conf` | `PasswordAuthentication no` (**nécessaire** : ce fichier imposait `yes` avant le reste) |
| `/etc/ssh/sshd_config.d/50-cloud-init.conf.backup.*` | Sauvegarde |

## Rollback rapide

```bash
cp -a /etc/ssh/sshd_config.backup /etc/ssh/sshd_config
cp -a /etc/ssh/sshd_config.d/50-cloud-init.conf.backup.20260404_103014 /etc/ssh/sshd_config.d/50-cloud-init.conf
# ajuster le nom du backup cloud-init si différent
sshd -t && systemctl reload ssh
```

## Vérification

```bash
sshd -T | grep -iE 'passwordauthentication|permitrootlogin'
```

Attendu : `passwordauthentication no`, `permitrootlogin without-password` (équivalent `prohibit-password`).

## Test obligatoire (nouvelle fenêtre)

```text
ssh -i C:\Users\User\.ssh\id_rsa root@5.78.153.17
```

Ne fermer la session Cursor actuelle qu’après succès du test.
