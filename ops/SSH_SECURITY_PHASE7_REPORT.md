# Phase 7 — Rapport final mission SSH (sécurisation progressive)

## 1. État initial (audit)

- **PermitRootLogin** : `yes`
- **PasswordAuthentication** : `yes` (fichier `sshd_config.d/50-cloud-init.conf`)
- **PubkeyAuthentication** : défaut **activé** (directive commentée dans `sshd_config`)
- **`/root/.ssh`** : déjà **700** ; **`authorized_keys`** : **600**
- **1 clé** présente dans `authorized_keys` (clé autorisée pour connexion par clé si le client a la clé privée correspondante)
- **Fail2ban** `sshd` : actif

## 2. Actions réalisées dans cette mission

| Action | Détail |
|--------|--------|
| Documentation | Fichiers `ops/SSH_SECURITY_PHASE*.md` (audit, plan, proposition durcissement, etc.) |
| Permissions | Idempotent : `chmod 700 /root/.ssh` et `chmod 600 /root/.ssh/authorized_keys` (déjà conformes) |

## 3. Clé SSH installée ou non

- **Aucune nouvelle clé n’a été ajoutée** (aucune clé publique fournie par l’opérateur dans cette mission).
- **Une entrée existait déjà** dans `authorized_keys` avant intervention.

## 4. Test connexion par clé (Phase 4)

- **Non exécuté depuis cet environnement** : un test de connexion SSH **depuis une nouvelle session** avec la clé privée **doit être fait par l’opérateur** (voir `SSH_SECURITY_PHASE2_PLAN.md` étape 3).
- **Statut** : « **clé fonctionnelle validée** » = **non marqué** — à valider manuellement.

## 5. Recommandations

1. Générer une **clé dédiée** poste administrateur et **ajouter** la ligne `.pub` dans `authorized_keys` (sans supprimer les lignes existantes).
2. **Tester** avec `ssh -i ...` dans une **nouvelle fenêtre** sans fermer la session.
3. **Seulement après** succès répété : envisager `PasswordAuthentication no` (voir Phase 5 — proposition).
4. Conserver **accès console** hébergeur ou **session de secours** lors du premier reload SSH après durcissement.

## 6. Commandes rollback (permissions uniquement)

Si besoin de revenir sur les seuls chmod (peu probable) :

```bash
chmod 700 /root/.ssh
chmod 600 /root/.ssh/authorized_keys
```

(Aucune modification de `sshd` n’a été faite.)

## 7. Confirmations

| Affirmation | OK |
|-------------|-----|
| Aucun accès SSH coupé par cette mission | ✓ (aucune modification `sshd_config`, pas de `reload ssh`) |
| Aucune session interrompue par l’agent | ✓ |
| Aucune modification dangereuse appliquée (`PasswordAuthentication` / `PermitRootLogin` inchangés) | ✓ |

---

**Fichiers créés** : `ops/SSH_SECURITY_PHASE1_AUDIT.md`, `SSH_SECURITY_PHASE2_PLAN.md`, `SSH_SECURITY_PHASE5_HARDENING_PROPOSAL.md`, `SSH_SECURITY_PHASE6_ADDITIONAL.md`, `SSH_SECURITY_PHASE7_REPORT.md`.
