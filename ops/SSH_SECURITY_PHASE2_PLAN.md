# Phase 2 — Plan sécurisé (étapes manuelles opérateur)

**Aucune étape ci-dessous n’a été exécutée automatiquement sur le serveur** (sauf idempotence permissions si explicitement demandée).

## Étape 1 — Préparation clé SSH (poste opérateur)

1. Générer une paire (exemple) :
   ```bash
   ssh-keygen -t ed25519 -C "astroscan-admin" -f ~/.ssh/astroscan_ed25519
   ```
2. Afficher la **clé publique** :
   ```bash
   cat ~/.ssh/astroscan_ed25519.pub
   ```
3. **Ne jamais** partager la clé **privée**.

**Changement** : rien sur le serveur tant que la clé n’est pas ajoutée.  
**Rollback** : supprimer la paire locale si non utilisée.

---

## Étape 2 — Ajouter la clé sur le serveur (sans couper l’accès)

**Condition** : session SSH **ouverte** (celle-ci) + idéalement accès console hébergeur en secours.

1. Sur le serveur, **ajouter** la ligne de `*.pub` à la fin de :
   ```text
   /root/.ssh/authorized_keys
   ```
2. Vérifier permissions (idempotent) :
   ```bash
   chmod 700 /root/.ssh
   chmod 600 /root/.ssh/authorized_keys
   ```

**Changement** : une nouvelle clé autorisée en plus des existantes.  
**Rollback** : éditer `authorized_keys` et supprimer la ligne ajoutée.

**Ne pas** redémarrer `sshd` pour cela (rechargement des clés généralement pris en compte sans coupure si `AuthorizedKeysFile` standard).

---

## Étape 3 — Test connexion par clé (OBLIGATOIRE avant durcissement)

1. **Ouvrir un nouveau terminal** (ne pas fermer la session actuelle).
2. Tester :
   ```bash
   ssh -i ~/.ssh/astroscan_ed25519 -o PreferredAuthentications=publickey -o PubkeyAuthentication=yes root@<IP_SERVEUR>
   ```
3. Si demande de mot de passe → **échec** → **STOP** (ne pas désactiver PasswordAuthentication).

**Condition pour étape 4** : connexion **réussie sans mot de passe** dans cette nouvelle session.

---

## Étape 4 — Durcissement (OPTIONNEL, manuel)

**Uniquement après** validation étape 3 **et** accès console confirmé.

1. Créer un fichier **drop-in** (exemple, à valider) :
   ```text
   /etc/ssh/sshd_config.d/99-hardening.conf
   ```
   Contenu **proposé** (non appliqué par ce dépôt) :
   ```text
   PasswordAuthentication no
   PermitRootLogin prohibit-password
   PubkeyAuthentication yes
   ```
2. Vérifier syntaxe :
   ```bash
   sshd -t
   ```
3. Recharger OpenSSH (selon OS) :
   ```bash
   systemctl reload ssh
   ```
   ou `systemctl reload sshd` selon l’unité active.

**Rollback immédiat** : restaurer `PasswordAuthentication yes` et `PermitRootLogin yes` dans les fichiers concernés, `sshd -t`, puis `systemctl reload ssh`.

---

## Condition bloquante

Si **un seul doute** sur la reconnexion → **ne pas** appliquer l’étape 4.
