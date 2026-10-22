# Mémo risques — modifications du 21/10/2026

Deux changements, déployés **sans aucun essai sur machine** (simulation PC uniquement).
Mise en service directe chez le client, sans test préalable.

## 1. EV purge pompe (commit `33f57e7`)

**Fonction :** relais V5 (GPIO 23, contact NO, EV 230 V normalement fermée). La purge s'ouvre
5 s à chaque démarrage pompe (PRG2, PRG4, PRG5 et chaque relance PRG5). Elle se ferme
immédiatement si la pompe s'arrête avant la fin des 5 s.

| Risque | Gravité | Parade |
|---|---|---|
| Commutation réelle relais V5 / EV jamais testée | Moyenne | `tests/test_ev_purge.py` dès que possible |
| EV d'occasion, sans terre, 230 V | Sécurité des personnes | Hors code — à traiter côté câblage |
| Thread de fermeture : jamais testé avec le vrai `lgpio` | Faible | Filet de sécurité `tick()` + 18 tests de simulation OK |
| Débitmètre après la purge → débit faussé pendant 5 s | Faible | Délai de garde PRG5 passé à 7,5 s |
| Plantage brutal pendant la purge → EV peut rester ouverte | Faible (accepté) | Remise à zéro au redémarrage |

**Désactivation d'urgence :** `PURGE_ENABLED = False` dans `config.py`.

## 2. VIC avec réducteur 5:1 (non commité ce soir)

**Changements :**
- Course de 500 pas, NEUTRE à 250.
- Vitesse 40 pas/s : course complète en 12,5 s.
- Dépassement de 15 pas (au lieu de 6 % et 10 %).
- Homing progressif.
- Ancrages faits depuis la position connue.
- PRG3 : 4 pas par tour de boucle.

| Risque | Gravité | Parade |
|---|---|---|
| **Piges en surcharge :** environ 57 N·m pour 38 N·m admissibles, à chaque arrivée en butée (12 N·m × 5 × 0,96) | **Élevée** | Seule vraie parade : baisser le courant du DM860H. Choix actuel : courant max |
| **Sens de rotation non vérifié** (réducteur à renvoi d'angle) → DEPART et RETOUR inversés | Moyenne | Permuter `VIC_DIR_OUVERTURE` et `VIC_DIR_FERMETURE`. À voir pendant le homing : après le 1er ancrage, la VIC doit monter vers RETOUR |
| Homing au démarrage : l'ancrage initial force contre la pige (position inconnue) | Moyenne | Environ 8 s si la VIC est en NEUTRE, jusqu'à 14 s si elle est en DEPART. Inévitable sans capteur |
| Ancrage depuis la position connue : plus de 15 pas perdus ne sont pas rattrapés avant le prochain démarrage | Faible | `VIC_ANCHOR_FULL_TRAVEL = True` remet l'ancien comportement (mais 6,6 s de forçage à chaque lancement de programme) |
| Timing réel à 40 pas/s sur le Raspberry jamais mesuré | Faible | Réglage `VIC_SPEED_SPS` |
| Lancement des programmes plus long | Info | Mise en place de la VIC : environ 6,6 s vers DEPART, 12,9 s vers NEUTRE, 19 s vers RETOUR. Homing environ 3 min 20 |
| Traversée PRG3 environ 13 à 15 s (contre 11 s avant) | Info | — |

## Réglages modifiables sans toucher au code (`config.py`)

| Réglage | Valeur | Effet |
|---|---|---|
| `PURGE_ENABLED` | `True` | Coupe la purge |
| `PURGE_TIME_S` | `5.0` | Durée de purge (doit rester inférieure à 7,5 s) |
| `PRG5_FLOW_GRACE_S` | `7.5` | Délai de garde PRG5 |
| `VIC_DIR_OUVERTURE` / `VIC_DIR_FERMETURE` | `1` / `0` | Sens de la VIC |
| `VIC_SPEED_SPS` | `40.0` | Vitesse de la VIC |
| `VIC_ANCHOR_OVERCOURSE_STEPS` | `15` | Dépassement des ancrages |
| `PRG3_VIC_OVERCOURSE_STEPS` | `15` | Dépassement des traversées PRG3 |
| `VIC_ANCHOR_FULL_TRAVEL` | `False` | `True` = ancrage sur toute la course |
| `VIC_HOMING_CYCLES` | `10` | Nombre de cycles du homing |
| `VIC_HOMING_FIRST_PCT` / `VIC_HOMING_STEP_PCT` | `30` / `10` | Progression du homing |

## À regarder dans les logs après les essais

- `Purge — EV ouverte` puis `Purge — EV fermée (fin temporisation)` environ 5 s plus tard.
  Si `minuterie en retard` apparaît : le thread a échoué et le filet de sécurité a pris le relais.
- `VIC homing — terminé, position NEUTRE (250 pas)` et la durée du homing.
- `VIC mini-homing — ancrage …` et les traversées PRG3 (`PRG3 — VIC en butée …`).
- Arrêts de sécurité inattendus : `Débit insuffisant` ou `Cuve vide détectée`.
