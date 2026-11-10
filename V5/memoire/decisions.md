# Décisions

> La plus récente en haut. Une décision remplacée est barrée avec la date, pas effacée.

## 2026-11-10 — Homing revu

- **Côté de l'ancrage initial alterné d'un démarrage à l'autre** (DEPART, RETOUR…), mémorisé dans
  `state/vic_state.json.homing`. Avec ou sans position mémorisée. Le cycle butée à butée fait côté
  initial puis côté opposé ; le 1er ancrage de programme est du côté opposé au dernier du homing.
- **Réarmement du driver avant et après le homing.**
- **Rodage conservé et allongé** (Julien : « il faut un petit rodage au début ») : 6 cycles 15 → 90 %
  au lieu de 3 cycles 30 / 60 / 90 %. Homing ≈ 2 min au lieu de 1 min 30.
- Logs : « ancrage … commandé » au lieu de « butée … atteinte » (rien n'est constaté sans capteur).
- Défaut trouvé et corrigé pendant le codage : le réarmement de début de homing réécrivait le fichier
  de position avant sa lecture → position mémorisée jamais utilisée. Position lue avant le réarmement.
- Simulation 70/70, mutation 19/19. Jamais essayé sur machine.

## 2026-11-10 — Recul de butée de 4 pas

- Les programmes ne laissent plus la VIC plaquée sur une pige : cibles DEPART = 4 pas, RETOUR = 496
  (`VIC_BUTEE_RECUL_STEPS`, 0 = désactivé). Raison : le blocage du 8/11 est toujours côté DEPART, où
  la VIC restait poussée contre la pige pendant des programmes entiers. 4 et non 8 (point d'équilibre
  tous les 8 pas). Précision : dans la tolérance ±1°, au-dessus de l'idéal ±0,5° — accepté par Julien.
- Ne réduit pas la force des coups d'ancrage (courant max inchangé), supprime l'appui permanent après.
- PRG5 : une lecture inconnue du sélecteur vise désormais NEUTRE (et non DEPART).
- Simulation 58/58, mutation 16/16. Jamais essayé sur machine.

## 2026-11-10 — Ancrage alterné DEPART / RETOUR, activé par défaut

- Julien : ancrer **1 fois sur 2 de chaque côté**, indépendamment du programme, pour équilibrer les
  appuis sur les piges. `VIC_ANCHOR_ALTERNATE = True` (`vic.anchor_programme()`), 1er ancrage après le
  homing en RETOUR. Activé **avant** la mesure de course, en connaissance de cause : tant que
  `VIC_TOTAL_STEPS` ≠ course réelle, la cible est décalée de l'écart une fois sur deux.
- Simulation 57/57, contrôle par mutation 15/15 (`tests/sim/run_mutants.py`). Jamais essayé sur machine.
- `tests/test_course_vic.py` supprimé (doublon de `essais/essai_2_course.py`).

## 2026-11-09 — Suite à l'audit du blocage VIC (essai client du 8/11)

Audit : `V5/AUDIT_VIC_2026-11-09.md`. Modifs codées le 9/11, **simulation PC 50/50 (et 12/12 erreurs volontaires détectées, `tests/sim/run_mutants.py`), jamais essayées sur machine** :

| Changement | Réglage (désactivation) |
|---|---|
| PRG3 : VIC fixe en DEPART pendant tout le programme (l'air sèche l'installation ; NEUTRE inutile), retour NEUTRE à l'arrêt sans nouvel ancrage. Remplace l'inversion DEPART ↔ RETOUR (« possiblement mal ajoutée ») | `PRG3_VIC_INVERT_ENABLED` (False) |
| Réarmement driver (ENA coupé 2 s, rétabli, 0,5 s) juste avant l'ancrage de chaque `start()`, pompe arrêtée depuis ≥ 15 s | `VIC_DRIVER_RESET_ENABLED` (True) |
| Cache des lignes LCD (une ligne réécrite seulement si elle change) + réécriture complète toutes les 5 s | `LCD_LINE_CACHE_ENABLED` (True), `LCD_FULL_REFRESH_S` |

Décidé aussi, sans modification de code :
- **PRG5 sans recalage en cours de programme : conservé.** L'opérateur va en DEPART et en RETOUR,
  les pas perdus sont absorbés en butée ; on garde les pas théoriques pour ne pas forcer sur les piges.
- **Position mémorisée : conservée.** Une position fausse est rattrapée par le cycle butée à butée du
  homing (coût : forçage supplémentaire pendant le homing, pas de référence fausse).
- ~~**Ancrage alterné DEPART / RETOUR : souhaité par Julien, en attente de la mesure de course**~~ → codé et activé le 2026-11-10 (essai E2,
  `V5/essais/`). Avec `VIC_TOTAL_STEPS` = course mesurée, NEUTRE est identique depuis les deux butées ;
  alternance possible si la mesure est répétable à ≤ 4 pas. Mesure à refaire à chaque visite (usure).
- **Position mémorisée : pas de condition « pompe » ajoutée** (Julien, 9/11).
- Flux git : uniquement PC → RPi, jamais de modification sur le RPi.
- « Redémarrage » dans le mail client du 8/11 = coupure électrique générale (driver 48 V inclus).

## 2026-11-05 — Mise à jour VIC implémentée (commits `6bb7fa7`, `652631c`)

Validée par Julien, **simulée sur PC seulement (30/30), jamais essayée sur machine** : Julien n'a
finalement pas le temps de tester aujourd'hui et **ne pourra plus rien modifier après aujourd'hui**.

| Changement | Réglage (désactivation) |
|---|---|
| Driver toujours actif | `VIC_HOLD_ENABLED` (False) |
| Dépassements 16 (homing, ancrages) / 8 (PRG3) | `VIC_ANCHOR_OVERCOURSE_STEPS`, `PRG3_VIC_OVERCOURSE_STEPS` |
| Homing : ancrage initial, 3 cycles 30/60/90 %, 1 butée à butée, NEUTRE (≈ 1 min 30) | `VIC_HOMING_*` |
| NEUTRE = milieu de la course configurée | `VIC_NEUTRE_STEPS = VIC_TOTAL_STEPS // 2` |
| PRG3 : recalage 1 traversée sur 3 | `PRG3_VIC_RECAL_EVERY` (1) |
| PRG5 : sélecteur stable 1 s avant mouvement | `PRG5_VIC_SELECTOR_SETTLE_S` (0) |
| Position mémorisée sur SD, sûre seulement pompe OFF ≥ 15 s et VIC immobile | `VIC_STATE_ENABLED` (False) |

Coupure électrique brutale (l'opérateur coupe tout d'un coup) : gérée — pompe en marche ou VIC en
mouvement au moment de la coupure → fichier « pas sûr » → ancrage pleine course au redémarrage.
Écriture atomique ; échec d'écriture → fichier supprimé.

Non fait aujourd'hui : mesure de la course réelle (procédure prête : `procedure-mesure-course.md`).

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
