# Backlog V5 — sujets reportés

Sujets identifiés et volontairement repoussés. À reprendre plus tard.
Ne rien traiter ici sans validation explicite.

---

## 1. Refonte des écrans LCD

**Statut :** à faire — date non fixée
**Périmètre :** *tous* les écrans, modifications légères sur chacun.

Écrans concernés (`display.py`) :
- `render_splash()` — démarrage machine
- `render_homing()` — homing VIC en cours
- `render_idle()` — attente sélection programme
- `render_cuve_vide_confirm()` — avertissement cuve vide PRG2/PRG4
- `render_starting()` — avant `program.start()`
- `render_running()` — délègue à `program.lcd_info()` (donc les 5 `lcd_info()` de `programs.py` sont aussi concernés)
- `render_stopping()` — avant `program.stop()`
- `render_prg5_summary()` — récap volume PRG5

Écrans construits **en dur**, hors `display.py` :
- Sécurité débit PRG5 — dans `_pump_restart()` (`programs.py`)
- Alerte cuve vide PRG2/PRG4 — dans `_cuve_vide_stop()` (`programs.py`)
- Écran final "ARRET" — dans le `finally` de `main.py`

**Note :** ces trois écrans ne passent pas par `display.py`.
Les y centraliser serait cohérent au moment de la refonte.

---

## 2. Procédure `_pump_restart()` — à revoir

**Statut :** comportement actuel **validé et voulu**, mais sujet à rouvrir plus tard.

Décision utilisateur : le blocage de la boucle principale pendant la procédure de
relance est **intentionnel**. L'objectif est du **100 % automatique** — l'opérateur
ne doit pas pouvoir intervenir pendant que la machine tente de se rétablir.
Ce n'est donc **pas** un défaut à corriger.

Rappel du coût actuel : `PRG5_FLOW_RESTART_COUNT (3)` × 2 × `PRG5_FLOW_RESTART_PAUSE_S (5 s)`
= jusqu'à **30 s** sans lecture bouton ni rafraîchissement LCD hors messages de la procédure.
(C'était 90 s avant le passage de la pause de 15 s à 5 s.)

Ne concerne plus que **PRG5** : PRG2 et PRG4 sont passés sur la sécurité cuve vide,
qui coupe la pompe sans relance.

Points à reprendre le jour où le sujet est rouvert :
- Faut-il un temps de blocage maximal borné ?
- Faut-il conserver un rafraîchissement du chrono / débit pendant la procédure ?

---

## 4. Constantes de pause de relance pour PRG2 / PRG4

**Statut :** question ouverte, non bloquante.

La demande initiale était « une constante de pause de relance par programme ».
Après l'ajout de la sécurité cuve vide, **PRG2 et PRG4 n'ont plus de relance du tout** :
une constante de pause pour eux n'aurait aucun effet et deviendrait du code mort
(exactement le cas de `FLOW_SAFETY_ENABLED_PROGRAMS`, supprimée pour cette raison).

Elles n'ont donc **pas** été créées. À trancher si la relance devait être réintroduite
sur PRG2/PRG4 un jour.

---

## 3. Horloge RPi sans RTC

**Statut :** constaté, non traité.

Les logs peuvent sauter de plusieurs semaines en plein run
(ex. `run_20260627_042809.log` : 27/06 04:28 → 22/07 15:42 pendant le homing).
Le RPi n'a pas d'horloge sauvegardée : la resynchro NTP après boot décale l'horodatage absolu.
Les durées relatives restent justes. À traiter uniquement si le diagnostic par logs devient gênant.
