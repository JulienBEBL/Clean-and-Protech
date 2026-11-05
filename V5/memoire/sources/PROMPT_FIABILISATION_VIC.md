# Prompt — nouvelle session Claude : fiabiliser la VIC (Clean & Protech V5)

> À copier-coller tel quel comme premier message d'une nouvelle session Claude Code.

---

Tu vas m'aider à **fiabiliser le fonctionnement de la VIC** sur la machine Clean & Protech
SERENA 230V. **On modifie la V5 existante, on ne crée pas de V6.** Réponds en français,
de façon résumée, directe et franche, **sans rien inventer** : si une info te manque, pose la question.

## 0. Contexte des essais — à prendre en compte dans tout ce que tu me proposes

- Je suis chez le client **cet après-midi seulement** pour tester la VIC. Va à l'essentiel :
  des tests courts, dans le bon ordre, avec ce que je dois observer à chaque fois.
- **Essais à sec uniquement** : pas d'eau, le plombier n'est pas là. Donc :
  - **ne me fais jamais faire tourner la pompe**, elle tournerait à sec ;
  - PRG2, PRG4 et PRG5 démarrent la pompe : on les exclut, ou alors je laisse le
    sélecteur pompe du variateur sur OFF, et seulement si c'est utile au test VIC ;
  - les sécurités débit (cuve vide, relance PRG5) se déclencheront forcément : ce n'est pas un défaut ;
  - privilégie `tests/test_homing.py`, `tests/test_vic.py`, `tests/test_rodage_vic.py`,
    et PRG1 et PRG3 dans `main.py` (sans pompe).
- Je t'enverrai les infos détaillées sur le moteur, le réducteur, la mécanique et les piges.
  Range-les dans ta mémoire (§2) et sers-t'en pour tes calculs (couples, vitesses, marges).

## 1. Ta mission, dans l'ordre

1. **Apprendre le projet avant tout :**
   - lis `V5/CLAUDE.md` en entier, puis `V5/MEMO_RISQUES_2026-10-21.md` ;
   - lis le code VIC : `V5/libs/vic.py`, la section VIC de `V5/config.py`, les helpers VIC
     et `Prg3._tick_vic_invert()` dans `V5/programs.py`, ainsi que `V5/tests/test_homing.py`,
     `V5/tests/test_vic.py` et `V5/tests/test_rodage_vic.py`.
2. **Récupère le terrain auprès de moi :**
   - ce que fait la VIC (bruit, à-coups, mauvaise position, blocage, sens inversé…) ;
   - les logs `V5/logs/run_*.log` du Raspberry ;
   - les réglages réellement présents sur la machine.
3. **Diagnostique**, propose des corrections, fais-les valider par moi, puis implémente-les.
4. **Vérifie sans la machine :**
   - simule le code sur PC avec un faux module `lgpio` (journal des écritures GPIO) ;
   - ajoute un modèle physique de la VIC : piges à 0 et 500 pas, position de départ inconnue,
     comptage des pas où le moteur force contre une pige.
   - L'ancienne simulation n'existe plus : recrée-la si besoin, dans le repo, sous `V5/tests/sim/`.
5. **Commite et pousse** chaque étape validée (voir §3).

## 2. Mémoire du projet — dans la V5, versionnée dans le repo

- La mémoire doit vivre **dans la V5**, commitée et poussée avec le code. Elle doit permettre
  à n'importe quelle session future de reprendre sans rien perdre.
- **À toi de choisir la meilleure organisation** : un fichier, ou un dossier (par exemple
  `V5/memoire/`) avec un index et un fichier par sujet. Choisis, explique-moi ton choix en
  deux lignes, puis mets-le en place dès le début.
- **Intègre ce qui existe déjà :**
  - `V5/CLAUDE.md` ;
  - `V5/MEMO_RISQUES_2026-10-21.md` ;
  - ce prompt ;
  - mes notes de mémoire Claude Code actuelles, dans
    `C:\Users\Julien\.claude\projects\C--Users-Julien-Documents-1--Clean-and-protech-Code-2026-Clean-and-Protech\memory\`.
  Lis-les, reprends ce qui est utile, évite les doublons avec `CLAUDE.md`, et signale-moi
  toute contradiction.
- **Pendant la session**, ajoute chaque fait appris : infos matérielles que je t'envoie,
  symptômes, mesures, réglages essayés et leur résultat, décisions et leur raison.
  Corrige ou supprime ce qui devient faux. Date les entrées de terrain.
- Tiens `V5/CLAUDE.md` à jour à chaque changement de comportement de la VIC, et indique
  dans `CLAUDE.md` où se trouve la mémoire, pour que toute session la lise au démarrage.

## 3. Droits sur le repo

- **Repo :** https://github.com/JulienBEBL/Clean-and-Protech (branche `main`).
  - Tu travailles **toujours sur mon PC Windows**, dans Claude Code (l'app) :
    `C:\Users\Julien\Documents\1. Clean and protech\Code\2026\Clean-and-Protech`.
  - Le Raspberry est à `/home/bebl/Desktop/Clean-and-Protech`. **Tu n'y as pas accès.**
- **Notre façon de travailler :**
  1. Tu modifies, commites et pousses depuis le PC.
  2. Je me connecte au Raspberry via **RPi Connect**, j'ouvre VS Code sur le RPi, je fais
     un `git pull`.
  3. Je lance et je vérifie que ça tourne.
  - Tu ne peux donc **rien exécuter sur la machine** : donne-moi à chaque fois les commandes
    exactes à lancer sur le RPi et ce que je dois observer.
  - Après chaque push, rappelle-moi de faire le `git pull` sur le RPi.
- **Tu es autorisé à lire, modifier, commiter et pousser en autonomie sur `main`.**
  Fais un `git pull` avant de commencer, et des commits petits et ciblés, au format
  `feat(VIC): …` ou `fix(VIC): …`.
- **Jamais :** `push --force`, réécriture d'historique, suppression de branche.
- **V1 à V4 sont en lecture seule.** On modifie uniquement la V5. On ne crée pas de V6.
- Avant chaque push, au minimum `python -m py_compile` sur les fichiers touchés,
  plus la simulation si la logique VIC change.

## 4. La VIC aujourd'hui (depuis le 21/10/2026)

**Matériel**

| Élément | Détail |
|---|---|
| Driver | DM860H, 400 pas/tour moteur (DIP), courant 6.0 A (pic 7.2 A) |
| Signaux | STEP = GPIO 27, DIR = GPIO 17, ENA = GPIO 22 (actif bas). GPIO direct, `lgpio`, gpiochip4, RPi 5 |
| Moteur | STEPPERONLINE 34IP65-120 : NEMA 34, 12 N·m, 6 A. Courbe constructeur : ≈ 9 N·m à 100 tr/min (60 V, 2000 microsteps) |
| Réducteur | STEPPERONLINE RYG34-G5 : planétaire **à renvoi d'angle**, 5:1, rendement 96 %, jeu ≤ 10 arcmin, 90 N·m admissibles (180 N·m momentané) |
| Butées | 2 piges dans la VIC, **38 N·m chacune**. Pas de capteur de position |

**Course et vitesse**
- **Tout est en pas** dans le programme ; les degrés seulement en commentaire.
  2000 pas par tour de VIC, 1 pas = 0,18°.
- DEPART = 0, NEUTRE = 250, RETOUR = 500 (90°).
- Vitesse constante 40 pas/s, sans rampe : course complète en 12,5 s. Exigence terrain : 15 s maximum.

**Homing au démarrage** (`VICController.homing()`)
1. Ancrage DEPART sur toute la course + 15 pas : la position est inconnue au démarrage.
2. 8 cycles centrés sur NEUTRE, d'amplitude 30 % à 100 % de la course, sans toucher les piges.
3. 2 cycles RETOUR puis DEPART, avec 15 pas de dépassement.
4. Fin en NEUTRE. Durée calculée : environ 3 min 20.

**Ancrage au lancement de chaque programme** (`_anchor_and_move_vic`)
- La VIC va en butée DEPART en parcourant la position connue + 15 pas, puis rejoint sa cible.
- `VIC_ANCHOR_FULL_TRAVEL = True` remet l'ancien comportement : toute la course à chaque fois.

**PRG3 (séchage)**
- La VIC fait des allers-retours DEPART ↔ RETOUR toutes les 50 s, sans bloquer la boucle.
- Elle avance de 4 pas par tour de boucle (boucle à 10 Hz) : 515 pas par traversée.
- `step_once()` tient le compteur à jour, donc un arrêt en pleine traversée laisse une position juste.

**Réglages dans `config.py`**
- `VIC_SPEED_SPS`, `VIC_ANCHOR_OVERCOURSE_STEPS`, `PRG3_VIC_OVERCOURSE_STEPS` ;
- `VIC_ANCHOR_FULL_TRAVEL` ;
- `VIC_HOMING_CYCLES`, `VIC_HOMING_ANCHOR_CYCLES`, `VIC_HOMING_FIRST_PCT`, `VIC_HOMING_STEP_PCT` ;
- `VIC_DIR_OUVERTURE` et `VIC_DIR_FERMETURE`.

## 5. Risques et points ouverts connus

1. **Piges en surcharge.** En butée, la pige reçoit couple moteur × 5 × 0,96, soit environ
   **57 N·m pour 38 N·m admissibles**. J'ai choisi de garder le courant au maximum. Les
   dépassements courts réduisent la durée du forçage, pas la force.
2. **Sens de rotation jamais vérifié** depuis le montage du renvoi d'angle. S'il est inversé,
   on permute `VIC_DIR_OUVERTURE` et `VIC_DIR_FERMETURE`.
3. **L'ancrage initial du homing force contre la pige** : environ 8 s si la VIC est en NEUTRE,
   jusqu'à 14 s si elle est en DEPART.
4. **Pas perdus :** au-delà de 15 pas, l'écart n'est pas rattrapé avant le prochain homing de démarrage.
5. **Timing réel à 40 pas/s sur le Raspberry jamais mesuré.** Les pas sont générés par
   `time.sleep()`, et un callback LED (I2C) est appelé après chaque pas bloquant.
6. **Hors VIC, à surveiller.** Le débitmètre est en aval de la purge. Valeurs actuelles :
   `PURGE_TIME_S = 10`, `PRG5_FLOW_GRACE_S = 10`, `PRG5_FLOW_RESTART_PAUSE_S = 10`,
   `PRGx_CUVE_VIDE_GRACE_S = 10`. La purge dure donc autant que ces délais : le débit peut être
   lu pendant qu'elle se referme, avec un risque de fausse alarme débit. Signale-le-moi, ne le
   « corrige » pas sans mon accord.

## 6. Conventions du projet — à respecter

- Toute constante matérielle ou réglable vit dans `config.py`, jamais en dur.
- Un seul handle `lgpio` via `libs/gpio_handle`. `gpio_free()` dans les `close()`.
- Le LCD (HD44780) n'accepte que l'**ASCII pur**, 20 caractères par ligne. Aucun compte à rebours à l'écran.
- La machine est **100 % automatique** : les procédures de sécurité bloquantes sont voulues.
- `DEBITMETRE_K_FACTOR` et les seuils de débit sont des **réglages vivants**. Ne jamais les
  signaler comme une erreur, ni les « corriger ».
- Le seul thread autorisé est la minuterie de purge, dans `relays.py`. Aucun accès I2C hors du thread principal.
- La validation finale se fait par l'usage réel de `main.py`, pas par `tests/test_main.py`.

## 7. Sécurité sur la machine réelle

- **C'est moi qui lance tout sur la machine.** Pour chaque test, donne-moi :
  - la commande exacte ;
  - ce que le test va faire bouger et combien de temps il dure ;
  - ce que je dois observer ;
  - comment l'arrêter (Ctrl+C).
- **Rien qui fasse tourner la pompe** : essais à sec (§0).
- Pour lancer un script de test, il faut d'abord arrêter le `main.py` qui tourne, sinon les
  GPIO sont déjà pris. Dis-moi comment le faire : le service se repère avec
  `systemctl list-units | grep -i clean`.
- Après une modification, dis-moi exactement quoi faire sur le Raspberry : `git pull`,
  redémarrage du service ou de `main.py`, puis ce qu'il faut vérifier.

Commence par :
1. Confirmer que tu as tout lu.
2. Me dire comment tu organises la mémoire dans la V5, puis la mettre en place (commit et push).
3. Me poser tes questions sur ce que fait la VIC sur le terrain.
4. Me proposer un plan de tests à sec pour cet après-midi, du plus simple au plus complet.
