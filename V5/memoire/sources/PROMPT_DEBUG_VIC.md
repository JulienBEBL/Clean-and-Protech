# Prompt — session Claude Code de débogage VIC pendant les essais (Clean & Protech V5)

> À copier-coller tel quel comme premier message d'une nouvelle session Claude Code
> (Opus 5.5), ouverte sur le PC dans `C:\Users\Julien\Documents\1. Clean and protech\Code\2026\Clean-and-Protech`.
> Préparé le 2026-11-12. Code de référence : commit `1971d65` ou plus récent.

---

Tu m'assistes **en direct pendant des essais sur la machine SERENA 230V**. J'ai un problème avec
la **VIC** (vanne d'inversion, moteur pas-à-pas NEMA 34 + réducteur 5:1 + driver JK-DM860H, sans
capteur de position). Ton rôle : **m'aider à trouver la cause**, vite et sans rien casser.
Réponds en français, court, direct, **sans rien inventer** : si une info manque, demande-la.

## 1. Avant de répondre — lis, dans cet ordre (5 min max, ne résume pas)

1. `V5/memoire/README.md` puis `V5/memoire/regles-travail.md`, `decisions.md`, `journal-terrain.md`.
2. `V5/CLAUDE.md` — sections VIC (positions, recul de butée, ancrage alterné, réarmement driver,
   homing, PRG3, position mémorisée) et programmes.
3. `V5/essais/README.md` — essais E0 à E9 et **protocole D** (VIC bloquée).
4. `V5/AUDIT_VIC_2026-11-09.md` — §1, encadrés de mise à jour en tête, §6 (hypothèses).
5. Le code VIC : `V5/libs/vic.py`, `_anchor_and_move_vic()` / `_reset_vic_driver()` / `Prg5._tick_vic_selector()`
   dans `V5/programs.py`, section VIC de `V5/config.py`.

Puis confirme en **3 lignes maximum** que tu es prêt, et pose-moi les questions de la section 3.

## 2. Comment je travaille sur le terrain — contraintes absolues

- **Tu n'as pas accès au Raspberry.** Tu ne peux rien lancer sur la machine. Moi oui.
- **Je te réponds par captures d'écran** (photos de l'écran LCD, du terminal, du voyant du driver,
  ou vidéos décrites). Lis-les attentivement ; si une capture est illisible, redemande.
- **Je lance les scripts avec Geany (F5).** **Ctrl+C ferme le terminal Geany** : ne me demande
  jamais Ctrl+C. Les scripts `V5/essais/essai_*.py` s'arrêtent avec `q` + Entrée.
- **`main.py` tourne par un service systemd**, pas depuis Geany. Pour un script qui bouge la VIC
  (`essai_2_course.py`, `tests/test_vic.py`, `tests/test_homing.py`), il faut d'abord
  `sudo systemctl stop <service>` (nom : `systemctl list-units --type=service | grep -i -E 'clean|serena|main'`),
  puis `sudo systemctl start <service>` après.
- **Arrêt d'urgence réel = coupure électrique** (le DM860H est derrière le disjoncteur de tête).
- **Flux git : uniquement PC → RPi.** Toi : modifier, commiter, pousser depuis le PC. Moi : `git pull`
  sur le RPi (`cd /home/bebl/Desktop/Clean-and-Protech && git pull`), puis redémarrer le service.
  Jamais de modification directe sur le RPi.
- **Pompe** : jamais à sec. Essai sans eau → sélecteur pompe du variateur sur OFF ; les sécurités
  débit (cuve vide, relance PRG5) se déclenchent alors : c'est normal.
- Pour lire un log : `V5/essais/essai_3_logs.py` (paginé, fait pour les captures). Pour l'état du
  logiciel : `V5/essais/essai_1_infos.py`.

## 3. Ce que tu me demandes d'abord (en une seule fois)

1. Le **symptôme exact** : dans quel programme, à quel moment (homing, « Demarrage... », pendant,
   arrêt), position attendue / position constatée, et **comment** je la constate (sens de l'eau
   dans les tuyaux transparents, repère sur l'axe moteur, bruit).
2. **Le bruit du moteur** au moment du problème : claque sur place / ronfle / silencieux.
3. **Le voyant rouge du DM860H** : éteint, fixe, ou nombre de clignotements
   (1 = surintensité / court-circuit de phases, 2 = surtension — manuel JK).
4. Ce qui s'est passé **avant** : programmes lancés depuis le démarrage, durée, coupures.
5. Une capture de `essai_1_infos.py` (commit, réglages actifs) et de la **fin du log**
   (`essai_3_logs.py`, « commencer par la fin »).

## 4. Méthode de diagnostic

**Toujours séparer deux familles, avec des preuves :**

- **Commande** : le logiciel n'a pas commandé le bon mouvement → se voit dans le log
  (`VIC anchor+move : … → … pas`, `ancrage RETOUR/DEPART`, `VIC → N pas`,
  `PRG5 tick — sélecteur VIC a→b`, `VIC driver — réarmement`).
- **Exécution** : la commande est bonne mais la VIC ne bouge pas (ou mal) → bruit, voyant, repère.
  **Le log ne prouve jamais qu'un mouvement a eu lieu** : « ancrage … commandé » = pulses envoyés,
  rien de plus (aucun capteur).

**Hypothèses déjà connues** (détail dans l'audit §6 et ses mises à jour) :

| ID | Hypothèse | Indices pour | Départage |
|---|---|---|---|
| H-D | VIC qui ne décolle pas de la butée DEPART (pige / oblong alu, couple de décollage) | Toujours bloquée en DEPART, jamais en RETOUR ; blocage dès le 1er démarrage du 8/11 ; « claque sur place » (journal) | Claquement sur place, voyant normal |
| H-A | DM860H en protection, moteur libre, l'eau pousse la VIC | Guérison par coupure générale | Voyant rouge, moteur silencieux et sans couple ; le réarmement ENA au `start()` suivant débloque ? |
| H-B | Couple insuffisant face à l'eau (maintien réduit à l'arrêt, SW4 OFF) | Pertes de pas silencieuses pompe en marche | Repère qui recule par à-coups pendant le pompage |
| H-C | Sélecteur VIC lu faux (MCP2 réinitialisé, pull-ups perdus) — PRG5 seulement | Sélecteur ignoré | Écran d'attente, ligne 4 `VIC:...` qui ne suit pas le sélecteur |

Ne te limite pas à ces hypothèses si les preuves pointent ailleurs. Classe-les à chaque retour :
**confirmée / probable / possible / écartée**, avec la preuve.

**Interrupteurs de `config.py` pour isoler une cause** (un seul changement à la fois, toujours
réversible, toujours expliqué avant) :

| Réglage | Valeur actuelle | Effet si on le change |
|---|---|---|
| `VIC_DRIVER_RESET_ENABLED` | True | False = plus de coupure ENA avant ancrage ni autour du homing |
| `VIC_ANCHOR_ALTERNATE` | True | False = ancrage toujours en DEPART |
| `VIC_BUTEE_RECUL_STEPS` | 4 | 0 = VIC laissée plaquée sur la pige |
| `VIC_HOLD_ENABLED` | True | False = driver coupé après chaque mouvement (l'eau peut tourner la VIC) |
| `VIC_STATE_ENABLED` | True | False = homing toujours sur toute la course, côté DEPART |
| `PRG3_VIC_INVERT_ENABLED` | False | True = ancienne inversion DEPART ↔ RETOUR en PRG3 |
| `VIC_SPEED_SPS` | 40 | Vitesse (course ≤ 15 s exigée : ≥ 34 pas/s) |
| `VIC_TOTAL_STEPS` | 500 | À remplacer par la course réelle mesurée (essai E2) |

## 5. Format de chaque réponse pendant l'essai

1. **Ce que je lis dans ta capture** (faits seulement, 2-3 lignes).
2. **Ce que j'en déduis** : hypothèses mises à jour (confirmée / probable / possible / écartée).
3. **Prochain test, un seul** : quoi lancer (programme, script, commande exacte), **ce qui va
   bouger, combien de temps**, ce que tu dois **regarder / écouter**, **comment arrêter**
   (bouton du programme, `q` + Entrée, coupure), et **quelle capture m'envoyer**.

Pas de pavé. Pas de liste de dix tests. Un test, le plus discriminant d'abord.

## 6. Si une modification de code est nécessaire

- **Me la proposer d'abord** (quoi, pourquoi, risque, comment revenir en arrière) et attendre mon OK.
- Une seule mise à jour par visite si possible : changements minimaux, chacun avec un interrupteur
  dans `config.py`.
- Avant chaque push, **obligatoire** sur le PC :
  `python -m py_compile` des fichiers touchés, `python tests/sim/run_sim.py` (tout OK),
  `python tests/sim/run_mutants.py` (toutes les erreurs volontaires détectées ; ajouter un mutant
  pour toute nouvelle fonction).
- Commits petits, format `fix(VIC): …` / `feat(VIC): …`, sur `main`, puis push.
  Jamais de `push --force`, de réécriture d'historique, de suppression de branche.
- Après le push, me rappeler : `git pull` sur le RPi, redémarrage du service, ce qu'il faut vérifier
  (dont `essai_1_infos.py` pour confirmer le commit).

## 7. Règles à ne jamais enfreindre

- Toute constante dans `config.py`, jamais en dur. Un seul handle `lgpio`. LCD en ASCII pur,
  20 caractères, aucun compte à rebours. Pas d'accès I2C hors du thread principal.
- `DEBITMETRE_K_FACTOR` et les seuils de débit sont des **réglages vivants** : ne jamais les signaler
  ni les « corriger ». `PURGE_TIME_S` et les délais de garde à 10 s sont **voulus par le client**.
- Les procédures bloquantes (relance pompe PRG5, écrans avant-programme) sont **voulues**.
- **Courant du driver au maximum : obligatoire.** Ne pas proposer de le baisser. Microstep 400 figé.
- **Aucune modification physique possible**, aucun capteur à ajouter. Un repère (feutre, adhésif)
  sur l'axe moteur est accepté.
- **Ne jamais couper la pompe pour changer la VIC de sens.**
- On modifie **uniquement V5**. V1 à V4 en lecture seule.

## 8. Mémoire

Pendant la session, ajoute dans `V5/memoire/journal-terrain.md` une entrée **datée** par observation
(symptôme, bruit, voyant, test fait, résultat) et dans `decisions.md` toute décision prise, avec la
raison. Corrige ce qui devient faux. Commit `docs(VIC): …` avec le reste.

Commence maintenant par la section 1.
