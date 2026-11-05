# Risques et points ouverts

> État au 2026-11-05. Origine : `sources/MEMO_RISQUES_2026-10-21.md` + prompt de mission.
> Mettre à jour la colonne État après chaque essai.

| # | Risque | Gravité | Parade / réglage | État |
|---|---|---|---|---|
| 0 | **Symptôme terrain** : VIC bloquée en position extrême, a du mal à repartir à certains redémarrages | **Élevée** | Diagnostic en cours (voir `journal-terrain.md`) | Ouvert |
| 1 | **Piges en surcharge** : ≈ 57,6 N·m pour 35 N·m (≈ 1 900 N pour 1 170 N à 30 mm) à chaque arrivée en butée | **Élevée** | Baisser le courant DM860H (≈ 3,6 A estimé, voir `materiel-vic.md`) et/ou ne plus toucher les piges en usage. Choix actuel : 6 A | Ouvert |
| 2 | **Sens de rotation jamais vérifié** depuis le renvoi d'angle | Moyenne | Permuter `VIC_DIR_OUVERTURE` / `VIC_DIR_FERMETURE`. Contrôle : après l'ancrage initial du homing, la VIC doit monter vers RETOUR | À vérifier 2026-11-05 |
| 3 | Ancrage initial du homing force contre la pige (position inconnue) | Moyenne | ≈ 8 s depuis NEUTRE, ≈ 14 s depuis DEPART. Inévitable sans capteur | Ouvert |
| 4 | Pas perdus > 15 non rattrapés avant le prochain homing | Faible | `VIC_ANCHOR_FULL_TRAVEL = True` (mais ≈ 6,6 s de forçage par lancement) | Ouvert |
| 5 | Timing réel 40 pas/s jamais mesuré (`time.sleep()` + callback LED I2C après chaque pas) | Faible | Mesurer la durée d'une course complète ; réglage `VIC_SPEED_SPS` | À mesurer 2026-11-05 |
| 6 | **Hors VIC** — débitmètre en aval de la purge : `PURGE_TIME_S = 10` = `PRG5_FLOW_GRACE_S = 10` = `PRG5_FLOW_RESTART_PAUSE_S = 10` = `PRGx_CUVE_VIDE_GRACE_S = 10`. Le débit peut être lu pendant que la purge se referme → fausse alarme possible | Moyenne | Valeurs **voulues par le client** (2026-11-05) : ne pas les changer | Accepté |
| 7 | Commutation réelle relais V5 / EV purge jamais testée | Moyenne | `tests/test_ev_purge.py` | Ouvert |
| 8 | EV purge d'occasion, 230 V, **sans terre** | Sécurité des personnes | Hors code — câblage | Ouvert |
| 9 | Plantage brutal pendant la purge → EV peut rester ouverte | Faible (accepté) | Remise à zéro au redémarrage | Accepté |

## À regarder dans les logs (`V5/logs/run_*.log`)

- `VIC homing — terminé, position NEUTRE (250 pas)` et la durée réelle du homing (calcul : ≈ 200 s).
- `VIC mini-homing — ancrage …`, `PRG3 — inversion VIC vers …`, `PRG3 — VIC en butée …`.
- `Purge — EV ouverte` puis `Purge — EV fermée (fin temporisation)` ; `minuterie en retard` = filet de sécurité utilisé.
- Arrêts de sécurité : `Débit insuffisant`, `Cuve vide détectée`.
