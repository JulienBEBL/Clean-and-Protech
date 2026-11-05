# Règles de travail

## Git et machine

- Repo : https://github.com/JulienBEBL/Clean-and-Protech, branche `main`.
- Claude travaille **uniquement sur le PC Windows** de Julien
  (`C:\Users\Julien\Documents\1. Clean and protech\Code\2026\Clean-and-Protech`).
- Raspberry : `/home/bebl/Desktop/Clean-and-Protech`. **Claude n'y a pas accès.**
  Julien s'y connecte via RPi Connect, ouvre VS Code, fait `git pull`, lance et observe.
- Claude ne peut rien exécuter sur la machine : pour chaque test, donner commande exacte,
  ce qui bouge, durée, ce qu'il faut observer, comment arrêter (Ctrl+C).
  Après chaque push : rappeler le `git pull` sur le RPi.
- Pour lancer un script de test, arrêter d'abord `main.py` (GPIO déjà pris) :
  repérer le service avec `systemctl list-units | grep -i clean`.

### Droit de commit

- **Par défaut** (dit le 2026-10-21) : Claude ne commite pas, Julien relit et commite.
- **Exception 2026-11-05** : la mission « fiabilisation VIC » (`sources/PROMPT_FIABILISATION_VIC.md`)
  autorise lire / modifier / commiter / pousser sur `main` en autonomie.
  Commits petits, format `feat(VIC): …` / `fix(VIC): …`. `git pull` avant de commencer.
- **Jamais** : `push --force`, réécriture d'historique, suppression de branche.
- Avant chaque push : `python -m py_compile` des fichiers touchés, + simulation si la logique VIC change
  (simulation à recréer sous `V5/tests/sim/`, faux `lgpio` + modèle physique piges 0 / 500).

## Périmètre

- On modifie **uniquement V5**. V1 à V4 en lecture seule. Pas de V6.
- Réponses en français, résumées, directes, **sans rien inventer** : si une info manque, demander.

## Règles produit à ne jamais « corriger »

- `DEBITMETRE_K_FACTOR` et les seuils de débit sont des **réglages vivants** (référence terrain 10.84 imp/L,
  valeur active variable). Ne jamais les signaler comme erreur.
- Machine **100 % automatique** : les procédures de sécurité bloquantes (`_pump_restart()`, écrans
  avant-programme) sont **voulues**. À rouvrir seulement sur demande explicite.
- Validation finale par l'usage réel de `main.py`, pas par `tests/test_main.py` (jamais lancé).
- Conventions de code : voir `CLAUDE.md` (constantes dans `config.py`, un seul handle `lgpio`,
  `gpio_free()` dans `close()`, LCD ASCII pur 20 car., aucun compte à rebours, seul thread = minuterie purge,
  aucun I2C hors thread principal).

## Essais à sec (pas d'eau, pas de plombier)

- **Ne jamais faire tourner la pompe à sec.** PRG2, PRG4, PRG5 démarrent la pompe → exclus,
  ou sélecteur pompe du variateur sur OFF, et seulement si utile au test VIC.
- Les sécurités débit (cuve vide, relance PRG5) se déclencheront forcément : ce n'est pas un défaut.
- Tests VIC sans pompe : `tests/test_homing.py`, `tests/test_vic.py`, `tests/test_rodage_vic.py`,
  PRG1 et PRG3 dans `main.py`.
