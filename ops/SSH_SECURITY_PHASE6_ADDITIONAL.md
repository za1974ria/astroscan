# Phase 6 — Sécurité additionnelle (constat & suggestions)

## Fail2ban

- Jail **`sshd`** : **active** (IPs bannies observées lors de l’audit).
- **Action** : aucune modification requise pour l’instant.

## Port SSH

- Port **22** (défaut), exposition **nécessaire** pour l’administration si aucun bastion.
- **Suggestion (NON appliquée)** : changer le port (ex. 2222) + mise à jour UFW + clients SSH — **risque** de se tromper dans règles pare-feu → documenter seulement.

## UFW

- Vérifier que **22/tcp** reste autorisé si vous changez de port ou de politique — **ne pas** retirer 22 sans accès console.
