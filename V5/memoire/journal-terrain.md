# Journal terrain

> Une entrée par observation, la plus récente en haut. Format : date — contexte — constat — suite.

## 2026-11-08 — Complément (retour client transmis par Julien le 2026-11-10)

- **1er démarrage du jour (absent du compte rendu) : VIC bloquée, n'a jamais bougé.**
- 2e démarrage (coupure générale) : VIC débloquée, PRG1 à PRG3 OK, puis PRG4 : bloquée en DEPART.
- 3e démarrage, sans PRG3 (PRG1, 2, 4, 5) : tout OK.
- **La VIC se bloque toujours en DEPART, jamais en RETOUR.**
- Conséquences : le PRG3 n'est pas la cause unique (blocage avant tout programme) ; l'asymétrie
  désigne le côté DEPART, où le logiciel concentrait tous les appuis (homing initial, ancrage de
  chaque `start()`, repos plaqué en PRG1 / PRG3 / PRG5-DEPART). Non observé : bruit du moteur
  (silence ou claquement) et voyant du driver — c'est ce qui départagerait mécanique et driver.

## 2026-11-08 — Essai client (Valery B.), commit `1b1e2b9` sur le RPi

- Séquence : PRG1, 2, 3, 4, 5, plusieurs PRG5, coupure générale, puis PRG1, 2, 4, 5 OK.
- PRG4 : eau par l'installation (sens départ) au lieu de NEUTRE. PRG5 : VIC « bloquée en départ »,
  sélecteur sur neutre ignoré, sur plusieurs essais. Tout redevient normal après coupure générale.
- Le client voit la position VIC uniquement par le sens de l'eau dans les tuyaux transparents.
- Aucun log récupéré, aucune observation du voyant DM860H ni du moteur.
- Audit (`V5/AUDIT_VIC_2026-11-09.md`) : le code commande bien NEUTRE en PRG4 ; cause la plus
  probable = VIC commandée mais immobile (driver en protection, couple, ou blocage en butée).
- À observer si ça recommence : clignotements du voyant rouge DM860H (1 = surintensité/court-circuit,
  2 = surtension), bruit moteur, repère sur l'axe, températures.

## 2026-11-05 — Essais à sec chez le client (après-midi)

- Contexte : première séance de test de la VIC avec réducteur 5:1. Pas d'eau, pas de plombier.
- Julien : **essais uniquement via `main.py`** (service déjà en place), pas de `tests/*.py`.
  Chaque mise à jour = arrêt service, pull, relance, vérification → une seule mise à jour aujourd'hui.
- Julien demande d'**attendre avant toute proposition** de modification.
- **Finalement aucun essai machine aujourd'hui** (pas le temps). Mise à jour VIC poussée
  (`6bb7fa7`) sans essai ; Julien ne pourra plus rien modifier après aujourd'hui.
- À la prochaine visite : log du homing (durée ≈ 90 s attendue), sens de rotation, chauffe moteur
  driver toujours actif, mesure de course (`procedure-mesure-course.md`), comportement du sélecteur PRG5.

## Avant 2026-11-05 — ce que l'on sait du seul essai depuis le réducteur (Julien absent)

- Le client s'en est servi **une seule fois**, sans résultat ni info exploitable.
- **Le homing va au bout.**
- **La VIC se bloque dans une position extrême** (max ou min, on ne sait pas laquelle).
- **Elle a du mal à repartir à certains redémarrages** : parfois le moteur **claque sur place**, la VIC
  bloquée n'arrive pas à repartir. Voyant du DM860H non visible.
- Ressenti client : la VIC « n'est pas encore parfaite », il veut fiabiliser la VIC et ses mouvements.
- Aucun log reçu à ce jour.

## 2026-10-22 — Mise en service sans essai

- Purge pompe + VIC réducteur 5:1 mis en service chez le client par le chef de Julien et Valery (client),
  **sans aucun test préalable**. Julien lit les logs à distance avec décalage.
