# Décisions

> La plus récente en haut. Une décision remplacée est barrée avec la date, pas effacée.

## 2026-11-05 — Arbitrages de Julien (2e passe)

- **Dépassement : 16 pas** homing + ancrages, **8 pas** PRG3.
- Jeu réducteur : ignoré.
- **Homing** : ancrage initial pleine course (obligatoire) → **3 cycles progressifs** → **1 seul cycle butée à
  butée** → NEUTRE.
- **PRG3** : recalage en butée sur une partie des traversées seulement — Julien préfère **1 sur 3** (moi : 1 sur 5).
- **Ne JAMAIS couper la pompe pour changer la VIC de sens.** Depuis le réducteur, la VIC tourne même sous fort
  débit / pression (retour terrain).
- **Aucune modification physique possible**, aucun capteur, nulle part.
- Sauvegarde de la position dans un fichier : idée retenue, à cadrer (nouvelle fonction = nouveau risque).
- Sélecteur PRG5 : besoin de mieux gérer le passage DEP → RET qui traverse NEUTRE (à cadrer).

## 2026-11-05 — Mise à jour du jour : 2 changements validés, EN ATTENTE (pas codés)

1. **Driver toujours actif** : activé à l'ouverture, désactivé seulement à la fermeture de `main.py`.
2. **Dépassement multiple de 8 pas** : 16 (homing, ancrages), 8 (PRG3). Raison : à 400 pulses/tour,
   un point d'équilibre tous les 8 pas → chaque ancrage retombe dans le même état (voir `materiel-vic.md`).
   ~~« repos sur la pige sans poussée garanti »~~ : faux en général, corrigé le 2026-11-05.
   Julien veut d'abord voir d'autres points (homing, ancrage, vitesse, programmes).

## 2026-11-05 — 400 pulses/tour figé

Machine remontée, DIP inaccessibles en pratique, et 400 retenu pour la stabilité de la génération de
signal (`time.sleep()`). Ne plus proposer de changer le micropas.

## 2026-11-05 — Une seule mise à jour par visite

Chaque mise à jour impose : arrêter le service `main.py`, `git pull`, le relancer, vérifier.
Julien veut **une seule mise à jour aujourd'hui**, testée 1 ou 2 fois, **sûrement bénéfique** (réduit le
risque). Donc : changements minimaux, ciblés, simulés sur PC avant push.

## 2026-11-05 — Courant driver au maximum : obligatoire

Il faut un couple très élevé pour faire tourner la VIC sous ≈ 500 L/min. Baisser le courant pour protéger
les piges est **exclu**. La fiabilisation doit se faire **à courant max**, par le logiciel.

## 2026-11-05 — Exigence : driver VIC toujours actif

Julien : le driver ne doit jamais être désactivé en fonctionnement, sinon l'eau fait tourner la VIC.
(Le code actuel le désactive après chaque mouvement — à corriger, modif à valider avant implémentation.)

## 2026-11-05 — Purge et délais de garde : 10 s / 10 s conservés

`PURGE_TIME_S = 10` et `PRG5_FLOW_GRACE_S = 10` (ainsi que `PRG5_FLOW_RESTART_PAUSE_S` et
`PRGx_CUVE_VIDE_GRACE_S` à 10) : **valeurs voulues par le client, ne pas les changer**. La doc est alignée
dessus. Le risque de fausse alarme débit en fin de purge reste noté dans `risques-ouverts.md`, accepté.

## 2026-11-05 — Mémoire projet dans `V5/memoire/`

Dossier avec index + un fichier par sujet, versionné avec le code. Raison : une session future reprend sans
rien perdre, et le terrain / les décisions ne se mélangent pas à la doc technique (`CLAUDE.md`).
Le mémo risques du 21/10 et le prompt de mission sont conservés dans `sources/`.

## 2026-10-21 — Adaptation VIC au réducteur 5:1 (validée en simulation seulement)

- **Courant driver au maximum (6 A)** malgré ≈ 57 N·m sur des piges de 38 N·m. Choix de Julien : garder
  la puissance. Parade retenue : dépassements courts.
- **Dépassement 15 pas** (ancrages et traversées PRG3) au lieu de 6 % / 10 % de la course : réduit la
  durée du forçage, pas la force.
- **Ancrage depuis la position connue** (`VIC_ANCHOR_FULL_TRAVEL = False`) au lieu de toute la course :
  15 pas de forçage par lancement au lieu de ≈ 265. Contrepartie : > 15 pas perdus non rattrapés avant
  le prochain homing.
- **Homing progressif** (ancrage pleine course, 8 cycles 30 → 100 % centrés NEUTRE, 2 cycles butée à
  butée, fin NEUTRE) ≈ 3 min 20.
- **Vitesse 40 pas/s constante, sans rampe** : course complète 12,5 s pour une exigence ≤ 15 s.
- **PRG3 non bloquant** : 4 pas par tour de boucle, compteur suivi par `step_once()`.

## 2026-10-21 — EV purge pompe

Ouverture `PURGE_TIME_S` à chaque démarrage pompe, minuterie `threading.Timer` (seul thread autorisé,
n'écrit que la broche PURGE) + filet de sécurité dans `relays.tick()`. Désactivation : `PURGE_ENABLED = False`.
