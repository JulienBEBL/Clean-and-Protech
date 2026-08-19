# Clean & Protech V5 — Documentation projet

## Vue d'ensemble

Système embarqué industriel sur **Raspberry Pi 5** pour le pilotage d'une machine de nettoyage et protection.
Machine **SERENA 230V** — différente de la V4 (SERENA 380V).

Contrôle : 1 moteur pas-à-pas (VIC uniquement), 6 relais GPIO (POMPE + AIR + 4 vannes US Solid),
un buzzer (×2 en parallèle), un débitmètre et un HMI (LCD + boutons + sélecteurs).

**Stack technique :**
- Python 3.11+
- `lgpio` — GPIO et PWM (RPi 5 uniquement, gpiochip4)
- `smbus2` — I2C
- MCP23017 — 2 expandeurs I/O 16 bits via I2C (MCP3 supprimé)

---

## Écarts V4 → V5

| Aspect | V4 | V5 |
|--------|----|----|
| Machine | SERENA 380V | SERENA 230V |
| Vannes-moteurs | 8 (RETOUR, POT_A_BOUE, VIC, CUVE_TRAVAIL, EGOUTS, DEPART, EAU_PROPRE, POMPE-stepper) | VIC uniquement |
| Vannes | 8 moteurs DM860H + VIC | 4 relais US Solid 24VDC (NO, actif haut) + relais POMPE + relais AIR |
| MCP23017 | 3 (MCP1/2/3) | 2 (MCP1/2 — MCP3 supprimé) |
| VIC STEP/DIR/ENA | Via MCP3 (I2C) | GPIO direct RPi 5 |
| VIC positions | 5 (B0..B4) | 3 (B0..B2 : DEPART/NEUTRE/RETOUR) |
| Relais POMPE | GPIO 16, actif bas inversé (HIGH=OFF) | GPIO 19, actif haut direct (HIGH=ON) |
| Relais AIR | GPIO 20 | GPIO 26 |
| Débitmètre | GPIO 21 | GPIO 13 |
| Buzzer | GPIO 26, ×1 | GPIO 21, ×2 en parallèle |
| EGOUTS (PRG3) | Moteur bloquant | Relais non-bloquant |
| Sécurité débit | Absente | PRG2, PRG4, PRG5 (timeout → relance → stop) |
| `tick()` retour | `None` | `bool` (True=OK, False=arrêt forcé) |
| K-factor | 7.13 imp/L | 10.84 imp/L |
| `MachineContext.motors` | `MotorController` | absent |
| `MachineContext.vic` | absent | `VICController` |
| `valve_state` | 7 vannes-moteurs | 4 relais vannes |
| `vic_steps` initial | 0 (DEPART) | 50 (NEUTRE, résultat homing) |
| Homing | VIC + 8 moteurs + rodage 9 cycles | VIC seul, séquence simplifiée |
| K-factor | 7.13 imp/L (fixe) | constante de calibration — ajustée en permanence |

### Logique relais POMPE — point d'attention

En V4, le relais POMPE commandait le câble "OFF" du variateur (logique inversée : GPIO HIGH = pompe OFF).
En V5, le relais POMPE commande le câble "ON" du variateur (logique directe : GPIO HIGH = pompe ON).
⚠️ Si le câblage évolue côté variateur, mettre à jour `config.RELAY_POMPE_GPIO` et les commentaires de `relays.py`.

---

## Structure du projet

```
V5/
├── main.py              # Programme principal — FSM IDLE/STARTING/RUNNING/STOPPING
├── config.py            # Source de vérité unique — toutes les constantes hardware
├── logger.py            # Logger horodaté — crée logs/run_YYYYMMDD_HHMMSS.log
├── programs.py          # Définition des 5 programmes + MachineContext + sécurité débit
├── display.py           # Rendu LCD 20×4 — fonctions render_*()
├── CLAUDE.md            # Ce fichier
├── BACKLOG.md           # Sujets reportés (écrans LCD, pump_restart, horloge RPi)
├── .gitignore           # Ignore logs/*.log, __pycache__, venv, IDE
├── logs/                # Logs générés au runtime (un fichier par démarrage — non versionnés)
├── libs/
│   ├── __init__.py
│   ├── gpio_handle.py   # Handle lgpio singleton (partagé par tous les drivers)
│   ├── i2c_bus.py       # Bus I2C avec retry engine
│   ├── mcp23017.py      # Driver bas niveau MCP23017
│   ├── lcd2004.py       # Driver LCD 20x4 I2C
│   ├── io_board.py      # Couche métier : LEDs, boutons, sélecteurs VIC/AIR (2 MCP)
│   ├── vic.py           # Contrôleur VIC — GPIO direct STEP/DIR/ENA
│   ├── buzzer.py        # Driver buzzer piézo passif (PWM, ×2 en parallèle)
│   ├── debitmetre.py    # Driver débitmètre à impulsions (interrupt GPIO)
│   └── relays.py        # Driver relais POMPE, AIR et 4 vannes US Solid
└── tests/
    ├── test_i2c_scan.py          # Scan bus I2C — vérifie MCP1, MCP2, LCD
    ├── test_lcd.py               # Afficheur LCD 20x4
    ├── test_mcp_inputs.py        # Entrées MCP — boutons PRG + sélecteurs VIC/AIR
    ├── test_homing.py            # Homing VIC — séquence complète, résultat NEUTRE
    ├── test_vic.py               # Pilotage manuel VIC — saisie interactive
    ├── test_rodage_vic.py        # Rodage VIC — cycles de rodage mécanique
    ├── test_buzzer.py            # Buzzer — 5 phases : beep, repeat, sweep, puissance, ringtone
    ├── test_debitmetre.py        # Débitmètre — comptage impulsions, débit, volume
    ├── test_relay_pompe.py       # Relais POMPE — commande ON/OFF variateur
    ├── test_ev_air.py            # Relais AIR — électrovanne d'injection
    ├── test_vannes_us.py         # Vannes — simulation séquentielle des 5 programmes
    ├── test_vannes_aleatoire.py  # Vannes — ouverture/fermeture simultanée aléatoire
    └── test_main.py              # Test machine complet — simulation opérateur (JAMAIS LANCÉ)
```

> `rodage.py` (racine) a été supprimé — commit `790271c`.
> `tests/test_rodage_vic.py` est **conservé** : testé et validé, il reste utile.

---

## Hardware — GPIO BCM (Raspberry Pi 5)

> Chip lgpio : `gpiochip4` (index 4) — spécifique Raspberry Pi 5.

| Signal           | GPIO BCM | Composant                                        |
|------------------|----------|--------------------------------------------------|
| VIC STEP (PUL)   | 27       | Driver DM860H — impulsion pas                    |
| VIC DIR          | 17       | Driver DM860H — direction                        |
| VIC ENA          | 22       | Driver DM860H — enable (actif bas)               |
| Relay POMPE      | 19       | Relais variateur ON — actif haut (HIGH=pompe ON) |
| Relay AIR        | 26       | Relais EV air — actif haut (HIGH=injection ON)   |
| Relay POT_A_BOUE | 7        | Vanne US Solid V1 — actif haut                   |
| Relay EGOUTS     | 8        | Vanne US Solid V2 — actif haut                   |
| Relay CUVE_TRAVAIL | 25    | Vanne US Solid V3 — actif haut                   |
| Relay EAU_PROPRE | 24       | Vanne US Solid V4 — actif haut                   |
| Relay réserve V5 | 23       | Non câblé côté vanne                             |
| Relay réserve V6 | 18       | Non câblé côté vanne                             |
| Relay réserve V7 | 15       | Non câblé côté vanne                             |
| Relay réserve V8 | 14       | Non câblé côté vanne                             |
| Buzzer           | 21       | 2× SEA-1295Y en parallèle (passifs 5V 42Ω 2kHz) |
| Débitmètre       | 13       | Capteur à impulsions (K=10.84 imp/L)             |

### Logique GPIO

| Composant | Actif | Niveau logique |
|-----------|-------|----------------|
| VIC ENA (DM860H) | Driver ON | LOW (0) |
| VIC DIR | Vers RETOUR | HIGH (1) |
| VIC DIR | Vers DEPART | LOW (0) |
| Relay POMPE | Pompe ON | HIGH (1) |
| Relay AIR | Injection ON | HIGH (1) |
| Vannes US Solid | Vanne ouverte | HIGH (1) |
| Boutons PRG (MCP1) | Pressé | LOW (actif bas, pull-up) |
| Sélecteur VIC (MCP2) | Actif | LOW (actif bas, pull-up) |
| Sélecteur AIR (MCP2) | Actif | LOW (actif bas, pull-up) |

---

## Hardware — I2C (bus 1, 100 kHz)

> ⚠️ **Adresses MCP1 et MCP2 à confirmer via `test_i2c_scan.py` après câblage PCB.**
> Valeurs probables : 0x24 (MCP1) et 0x26 (MCP2). Modifier `config.py` si différent.

| Composant | Adresse | Rôle                                      |
|-----------|---------|-------------------------------------------|
| MCP1      | 0x24    | Port A : LEDs 1..6 — Port B : boutons PRG 1..6 |
| MCP2      | 0x26    | Port A : sélecteur AIR — Port B : sélecteur VIC 3 pos |
| LCD 20x4  | 0x27    | Afficheur HMI                             |

---

## IOBoard — Câblage PCB V5

### MCP1 (0x24) — Programmes
- **Port B INPUT** (pull-up) : B0..B5 = PRG1..PRG6 (actif bas)
- **Port A OUTPUT** : A2..A7 = LED1..LED6 (actif haut)
  - LED1→A2, LED2→A3, ..., LED6→A7

### MCP2 (0x26) — Sélecteurs
- **Port B INPUT** (pull-up) : B0..B2 = VIC1..VIC3 (actif bas)
  - ⚠️ **Seules 2 positions sont câblées.** VIC3 (B2) n'est pas connecté et est ignoré
    par `read_vic_selector()`. La position NEUTRE correspond à *aucun contact actif*.
  - VIC1 (B0) actif → retour `1` → DEPART (0 pas)
  - VIC2 (B1) actif → retour `2` → RETOUR (100 pas)
  - aucun actif    → retour `0` → NEUTRE (50 pas) — **position par défaut**
- **Port A INPUT** (pull-up) : A7..A5 = AIR1..AIR3 (actif bas)
  - AIR1 (faible)→A7, AIR2 (moyen)→A6, AIR3 (continu)→A5
  - Position 0 (aucun actif) = pas d'injection

---

## VIC — Driver JK-DM860H

**DIP switch :** courant et microstep réglés physiquement sur le driver.
- `DRIVER_MICROSTEP = 400` pas/tour (SW5..SW8 = ON)
- ENA actif bas : `VIC_ENA_ACTIVE_LEVEL = 0` (driver ON), `VIC_ENA_INACTIVE_LEVEL = 1` (sécurisé)

### Positions VIC

| Position | Pas | Étiquette | Sélecteur MCP2        | `read_vic_selector()` |
|----------|-----|-----------|-----------------------|-----------------------|
| DEPART   | 0   | DEP       | VIC1 (B0) actif       | `1`                   |
| NEUTRE   | 50  | NEU       | aucun contact actif   | `0`                   |
| RETOUR   | 100 | RET       | VIC2 (B1) actif       | `2`                   |

Mapping dans `config.VIC_POSITIONS = {0: 50, 1: 0, 2: 100}`.

### Séquence de homing (`VIC_HOMING_CYCLES` = 10)

```
1.  Ancrage initial : fermeture overcourse → butée DEPART
2.  Cycle 1  : ouverture overcourse → RETOUR, puis fermeture overcourse → DEPART
    ...
11. Cycle 10 : ouverture overcourse → RETOUR (dernier cycle se termine en RETOUR)
12. Fermeture 50 pas → NEUTRE
```

Overcourse = `VIC_TOTAL_STEPS × MOTOR_HOMING_FIRST_CLOSE_FACTOR` = 100 × 1.06 = **106 pas**.
Position finale : `vic_steps = 50` (NEUTRE).

> ⏱️ **Coût en temps** : à `VIC_SPEED_SPS = 10.0`, un run mesuré à 5 cycles prenait **111 s**.
> Avec la valeur actuelle de 10 cycles, compter environ **3 min 30** de homing au démarrage machine.

### Méthodes d'ancrage

`anchor_depart()` et `anchor_retour()` exécutent un déplacement en overcourse jusqu'à
la butée mécanique correspondante et **recalent le compteur de position** (0 ou 100).
Elles sont utilisées par `_anchor_and_move_vic()` dans `programs.py` à chaque `start()`.

---

## Programmes V5

| PRG | Nom            | Vannes ouvertes              | VIC    | Pompe | AIR              | Sécurité débit |
|-----|----------------|------------------------------|--------|-------|------------------|----------------|
| 1   | PREM.VIDANGE   | POT_A_BOUE                   | DEPART | OFF   | AUTO 4s ON/3s OFF | — |
| 2   | VIDANGE CUVE   | CUVE_TRAVAIL, EGOUTS         | NEUTRE | ON    | OFF              | **Cuve vide** (sans relance) + confirmation |
| 3   | SECHAGE        | — (EGOUTS: cycle relay 15s open/30s closed)| **INVERSION auto 60s** | OFF   | AUTO 6s ON/2s OFF | — |
| 4   | REMPLISSAGE    | EAU_PROPRE, POT_A_BOUE       | NEUTRE | ON    | OFF              | **Cuve vide** (sans relance) + confirmation |
| 5   | DESEMBOUAGE    | POT_A_BOUE, CUVE_TRAVAIL     | MANU   | ON    | MANU (sélecteur) | **Débit + relance** (3 tentatives) |

### Écrans avant-programme — consignes opérateur

Chaque programme affiche un écran de consignes **avant toute action machine**
(ni vanne, ni VIC, ni pompe). Affichage **bloquant et purement automatique** :
aucun bouton n'est lu, le programme démarre seul à l'expiration du délai.

| PRG | Message affiché | Durée |
|-----|-----------------|-------|
| 1 | `Referez vous` / `a la notice` | `PRG1_PREMSG_TIME_S` (10 s) |
| 2 | `Activer la pompe` / `Vidage Cuve 1` | `PRG2_PREMSG_TIME_S` (10 s) |
| 3 | `Brancher le` / `compresseur` | `PRG3_PREMSG_TIME_S` (10 s) |
| 4 | `Activer la pompe` / `Verifier niveau` / `max Cuve 2` | `PRG4_PREMSG_TIME_S` (10 s) |
| 5 | `Mettre la VIC en` / `position Neutre` / `Activer la pompe` | `PRG5_PREMSG_TIME_S` (10 s) |

**Mise en page** — ligne 1 : `PROGRAMME x`, lignes 2 à 4 : message centré (3 lignes max).
**Aucun compte à rebours n'est affiché.**

**Motif sonore** — salve de `PREMSG_BEEP_COUNT` (2) bips, puis pause
`PREMSG_BEEP_PAUSE_S` (1 s), répétée jusqu'à la fin : `bip-bip … bip-bip … bip-bip`.
Sur 10 s cela donne 8 salves. La dernière pause est tronquée pour ne pas dépasser la durée.

> ⚠️ Le LCD est un HD44780 : `_write_char()` fait `ord(ch) & 0xFF`, il ne peut **pas**
> afficher de caractères accentués. Les messages de `config.PREMSG_LINES` doivent rester
> en **ASCII pur** et tenir en 20 caractères par ligne.

### Écrans RUNNING — un par programme

Construits par `lcd_info()` dans `programs.py`, affichés à 10 Hz par `render_running()`.
Toutes les lignes sont centrées sur 20 caractères, en **ASCII pur**.

```
   PROGRAMME 1          PRG2 VIDANGE CUVE 1     PROGRAMME 3
 {PREMIERE VIDANGE}     [SURVEILLER CUVE 1]        SECHAGE
 {100% AUTOMATIQUE}       ALLUMER LA POMPE     100% AUTOMATIQUE
   DUREE : 12:34         DEBIT : 123 l/min      DUREE : 12:34

   PROGRAMME 4           PRG5 DESEMBOUAGE
 REMPLISSAGE CUVE 1    [POMPE A L'ARRET POUR]
[SURVEILLER CUVE 1]    [ CHANGEMENT DE SENS ]
 DEBIT : 123 l/min      12:34      123 l/min
```

`[…]` = **ligne clignotante** — `{…}` = **ligne alternée** (voir ci-dessous).

**PRG2 et PRG5 fusionnent l'en-tête** (`PRG2 …` / `PRG5 …` au lieu de `PROGRAMME x`)
pour libérer une ligne et garder les consignes opérateur en toutes lettres.
Sans cette fusion, PRG2 aurait besoin de 5 lignes et PRG5 verrait son message
`POMPE A L'ARRET POUR CHANGEMENT DE SENS` (39 caractères) tronqué.

**`PROGRAMME 1` et non `PROGRAMME N°1`** : `ord('°')` = 176, adresse à laquelle le
HD44780 stocke un caractère katakana. Le vrai symbole degré est à l'adresse 223
(`chr(0xDF)`) si le besoin se représente.

### Consignes clignotantes

Trois consignes critiques clignotent à `LCD_BLINK_PERIOD_S` (1 s allumé / 1 s éteint) :

| Programme | Ligne clignotante |
|-----------|-------------------|
| PRG2 | `SURVEILLER CUVE 1` (ligne 2) |
| PRG4 | `SURVEILLER CUVE 1` (ligne 3) |
| PRG5 | `POMPE A L'ARRET POUR` + `CHANGEMENT DE SENS` (lignes 2 et 3, **en phase**) |

Le helper `_blink(text, elapsed_s)` de `programs.py` dérive le rythme de `elapsed_s`
plutôt que d'un état interne : aucune variable à maintenir, et les lignes multiples
d'un même écran clignotent forcément ensemble. Pendant la phase éteinte, la ligne est
remplie d'espaces — les autres lignes ne bougent pas.

> `LCD_BLINK_PERIOD_S <= 0` désactive le clignotement : le texte reste affiché en permanence.

### Textes alternés — PRG1

PRG1 fait tenir **quatre informations sur deux lignes** en les alternant toutes les
`LCD_ALTERNATE_PERIOD_S` (3 s) :

```
     phase A (3 s)              phase B (3 s)
  +--------------------+    +--------------------+
  |    PROGRAMME 1     |    |    PROGRAMME 1     |
  |  PREMIERE VIDANGE  | ←→ |     ATTENTION      |
  |  100% AUTOMATIQUE  | ←→ | SURVEILLER CUVE 1  |
  |   DUREE : 00:00    |    |   DUREE : 00:03    |
  +--------------------+    +--------------------+
```

Le helper `_alternate(text_a, text_b, elapsed_s)` de `programs.py` suit le même principe
que `_blink()` — rythme dérivé de `elapsed_s`, donc les deux lignes basculent forcément
ensemble. **Différence importante : la ligne n'est jamais vide**, elle porte toujours
une information, alors que `_blink()` l'efface une période sur deux.

> `LCD_ALTERNATE_PERIOD_S <= 0` fige l'affichage sur le premier texte.

**Largeurs fixes anti-scintillement** : `_fmt_flow()` cale le débit sur 3 chiffres et
`_split_line()` colle la durée à gauche / le débit à droite. Les valeurs ne se décalent
donc pas latéralement quand le nombre de chiffres change, malgré le rafraîchissement 10 Hz.

> ⚠️ Ces écrans n'affichent plus la position VIC, l'état AIR ni l'état EGOUTS, qui
> figuraient dans les versions précédentes. Ces informations restent disponibles
> dans les logs. Choix assumé : priorité aux consignes opérateur.

### Enchaînement complet au lancement d'un programme

```
IDLE  ──appui bouton──►  [CONFIRM]  ──►  STARTING  ──►  RUNNING
                         PRG2/PRG4        │
                         uniquement       ├─ 1. Écran avant-programme (10 s, bloquant, bips)
                                          ├─ 2. Vannes séquentielles (bloquant)
                                          ├─ 3. Mini-homing VIC (bloquant)
                                          └─ 4. Pompe / AIR ON
```

Pour PRG2 et PRG4, l'écran `ATTENTION / CUVE VIDE ?` vient **avant** l'écran
avant-programme : l'opérateur valide d'abord, puis reçoit les consignes.

### PRG3 — trois cycles indépendants et non bloquants

PRG3 fait tourner **trois cycles en parallèle**, aucun n'interrompt les deux autres :

| Cycle | Rythme | Constantes |
|-------|--------|------------|
| AIR | 6 s ON / 2 s OFF | `PRG3_AIR_ON_S` / `PRG3_AIR_OFF_S` |
| EGOUTS | 30 s fermé / 15 s ouvert (démarre fermé) | `PRG3_EGOUTS_CLOSED_S` / `PRG3_EGOUTS_OPEN_S` |
| **Inversion VIC** | 50 s en butée, puis traversée ≈ 11,5 s (cycle 61,5 s) | `PRG3_VIC_INVERT_PERIOD_S` |

**Inversion VIC** — la VIC alterne DEPART ↔ RETOUR pour inverser le sens d'injection
d'air et décoller les saletés dans les tuyaux. Chaque traversée fait
`round(VIC_TOTAL_STEPS × PRG3_VIC_OVERCOURSE_FACTOR)` = **115 pas** (overcourse +15 %),
ce qui garantit l'arrivée en butée mécanique ; le compteur est recalé à 0 ou 100 à l'arrivée.

> ⚠️ `round()` et non `int()` : `100 × 1.15` vaut `114.99999…` en flottant, une
> troncature donnerait 114 pas.

**Non-blocage** — un déplacement VIC classique (`move_to`) bloquerait la boucle ~11,5 s
et figerait AIR et EGOUTS. Le cycle PRG3 génère donc **un seul pas par itération** de
la boucle principale, via l'API pas-à-pas de `VICController` (`begin_stepping()` /
`step_once()` / `end_stepping()` / `set_position()`). Le driver reste actif pendant
toute la traversée — le couple de maintien est conservé, contrairement à un
enable/disable par pas.

À `VIC_SPEED_SPS = 10` un pas dure 100 ms, soit exactement la période de boucle
(`MAIN_LOOP_HZ = 10`) : la traversée n'allonge pas la boucle.

**Arrêt de PRG3** — `stop()` exécute dans l'ordre :
1. Coupure AIR
2. Interruption propre d'une traversée VIC en cours (driver relâché)
3. **Fermeture EGOUTS** — commande relais inconditionnelle
4. VIC → NEUTRE (ancrage butée DEPART puis 50 pas, ≈ 15 s)
5. Complément d'attente si nécessaire pour garantir `VALVE_CLOSE_TRAVEL_S` (16 s)
   depuis la commande de fermeture

Les étapes 3 et 4 se **recouvrent** : la course mécanique de la vanne se déroule
pendant le repositionnement de la VIC, le complément final est donc de l'ordre
de la seconde.

### Comportement vannes et VIC au démarrage d'un programme
- `start()` : vannes séquentielles → puis **mini-homing VIC** (`_anchor_and_move_vic()` : overcourse DEPART → recalage à 0 → `move_to()` cible). Garantit la position physique réelle avant chaque programme.
- `stop()` : coupe relais POMPE et/ou AIR. **Les vannes sont laissées en place**, sauf PRG3.
  - ⚠️ **La VIC n'est PAS laissée en place** pour PRG1, PRG3 et PRG5 : leur `stop()`
    ramène la VIC en NEUTRE (déplacement bloquant).
  - ⚠️ **PRG3 ferme EGOUTS** dans son `stop()` — c'est le seul programme qui manœuvre
    une vanne à l'arrêt, parce qu'il la pilote activement pendant son exécution.
  - PRG2 et PRG4 ne touchent pas à la VIC dans `stop()`.
- `start()` suivant : repositionne uniquement les vannes qui changent + mini-homing VIC.

> ⏱️ `start()` est **bloquant** : `_set_valves()` attend `VALVE_CLOSE_TRAVEL_S` (16 s) après chaque
> fermeture et `VALVE_OPEN_CAPACITOR_CHARGE_S` (15 s) après chaque ouverture, en séquence.
> PRG4 (2 vannes à ouvrir) peut donc demander ~60 s de vannes + le mini-homing VIC avant RUNNING.

### ⚠️ Deux sécurités débit distinctes — ne pas les confondre

| | **Cuve vide** (PRG2, PRG4) | **Débit + relance** (PRG5) |
|---|---|---|
| Principe | La cuve est censée être pleine → si le débit tombe, elle est vide | Circuit fermé → la chute peut être passagère |
| Relance pompe | ❌ **Aucune** | ✅ 3 tentatives |
| Action | Coupe la pompe, arrête le programme | Tente de rétablir, arrête si échec |
| Délai de garde après `start()` | ✅ `PRGx_CUVE_VIDE_GRACE_S` | ❌ |
| Confirmation opérateur avant lancement | ✅ écran + 2e appui | ❌ |
| Constantes | `PRG2_CUVE_VIDE_*` / `PRG4_CUVE_VIDE_*` | `PRG5_FLOW_*` |

#### Sécurité cuve vide (PRG2, PRG4)

**Avant lancement** — état FSM `CONFIRM` :
1. 1er appui sur le bouton PRG2 ou PRG4 → écran `ATTENTION / CUVE VIDE ?`
2. L'opérateur valide par un **2e appui sur le même bouton** → STARTING
3. Sans confirmation sous `CUVE_VIDE_CONFIRM_TIMEOUT_S` (5 s) → abandon, retour IDLE

> Aucun compte à rebours n'est affiché sur cet écran — comme sur les écrans
> avant-programme. Règle générale du projet : **pas de décompte à l'écran**.

**Pendant l'exécution** :
1. La surveillance ne s'active qu'après `PRGx_CUVE_VIDE_GRACE_S` (5 s) — évite un
   déclenchement pendant la montée en pression qui bloquerait le démarrage de la pompe.
2. Si `flow_lpm() < PRGx_CUVE_VIDE_MIN_LPM` (50 L/min) en continu pendant
   `PRGx_CUVE_VIDE_TIMEOUT_S` (5 s) :
   - **pompe coupée immédiatement** (avant tout affichage)
   - 3 beeps + écran `PLUS DE DEBIT / Cuve vide` pendant `CUVE_VIDE_ALERT_TIME_S` (5 s)
   - `tick()` retourne `False` → FSM → STOPPING → IDLE
3. **Aucune relance** — il n'y a plus rien à pomper.

Le chrono est remis à zéro dès que le débit repasse au-dessus du seuil : un creux
passager plus court que le timeout ne déclenche pas l'arrêt.

#### Sécurité débit avec relance (PRG5)
1. Si `flow_lpm() < PRG5_FLOW_MIN_LPM` en continu pendant `PRG5_FLOW_TIMEOUT_S` :
2. Lance `PRG5_FLOW_RESTART_COUNT` (3) tentatives : pompe OFF → `PRG5_FLOW_RESTART_PAUSE_S` (5 s) → pompe ON → même pause → vérif débit.
3. Si débit OK après relance → `tick()` retourne `True` → programme continue (vannes/VIC inchangés).
4. Si toutes les tentatives échouent → `tick()` retourne `False` → FSM → STOPPING → IDLE.

> Tous ces seuils sont des **paramètres de réglage** et évoluent avec la calibration du débitmètre.

**🔒 Blocage volontaire :** `_pump_restart()` est **bloquante** — jusqu'à
`3 × 2 × 5 s = 30 s` sans lecture bouton. C'est **voulu** : la machine doit rester
100 % automatique et l'opérateur ne doit pas pouvoir intervenir pendant la tentative
de rétablissement. Ce n'est pas un défaut. Sujet à rouvrir plus tard — voir `BACKLOG.md`.

**Affichage LCD pendant la procédure :**
- Ligne 1 : `SECURITE DEBIT` (centré)
- Ligne 2 : `Debit insuffisant`
- Ligne 3 : `Tentative X/3` (mise à jour à chaque essai)
- Ligne 4 : `Pompe arret...` → `Pompe relance...`
- Après retour de `_pump_restart()`, le LCD est restauré automatiquement par `render_running()` dans la boucle principale.

**Buzzer pendant la procédure :** 3 beeps au déclenchement (voir protocole buzzer ci-dessous).

---

## API — Modules applicatifs

### `VICController` (libs/vic.py)
```python
vic = VICController()
vic.open()
vic.homing()                    # ancrage + N cycles + positionnement NEUTRE (50 pas)
vic.anchor_depart()             # overcourse jusqu'à butée DEPART + recalage position à 0
vic.anchor_retour()             # overcourse jusqu'à butée RETOUR + recalage position à 100
vic.move_to(target_steps)       # déplacement absolu — no-op si déjà en place
vic.move_relative(delta)        # déplacement relatif (test/diagnostic)
vic.disable()                   # désactive driver (état sûr)
vic.position -> int             # position courante (fiable après homing/anchor)
vic.close()

# --- Déplacement pas-à-pas NON BLOQUANT (utilisé par le cycle d'inversion PRG3) ---
vic.begin_stepping(direction)   # 'ouverture' / 'fermeture' : fixe DIR + active driver
vic.step_once()                 # UN pas (~1/VIC_SPEED_SPS s) — driver laissé actif
vic.end_stepping()              # désactive le driver (idempotent)
vic.set_position(steps)         # recale le compteur sans bouger (après butée)
```

### `Relays` (libs/relays.py)
```python
relays = Relays()
relays.open()
relays.set_pompe_on()                    # GPIO HIGH → variateur ON → pompe tourne
relays.set_pompe_off()                   # GPIO LOW  → variateur OFF → pompe arrêt
relays.set_air_on(time_s=None)           # None=indéfini, float=timer auto via tick()
relays.set_air_off()
relays.tick()                            # gère auto-extinction AIR (si timer)
relays.set_valve(name, on: bool)         # vanne US Solid par nom
relays.open_valve(name)                  # raccourci
relays.close_valve(name)                 # raccourci
relays.close_all_valves()               # sécurité — ferme les 4 vannes
relays.pompe_is_on -> bool
relays.air_is_on -> bool
relays.close()
```

### `IOBoard` (libs/io_board.py)
```python
io = IOBoard(bus)
io.init()

# LEDs (1..6)
io.set_led(index, state)
io.set_all_leds(state)

# Boutons PRG (1..6) — actif bas
io.read_btn(index) -> int          # niveau brut
io.read_btn_active(index) -> int   # 1 si appuyé

# Sélecteur VIC (1..3) — actif bas
io.read_vic_selector() -> int      # 0 si aucun, 1=DEP, 2=NEU, 3=RET
io.read_vic_active(index) -> int   # 1 si position active

# Sélecteur AIR — actif bas
io.read_air_mode() -> int          # 0=aucun, 1=faible, 2=moyen, 3=continu
io.read_air_active(index) -> int   # 1 si position active (1..3)
```

### `MachineContext` (programs.py)
```python
@dataclass
class MachineContext:
    vic:         VICController
    relays:      Relays
    io:          IOBoard
    flow:        FlowMeter
    valve_state: dict[str, bool]         # 4 vannes relais : True=ouverte
    vic_steps:   int         = 50        # NEUTRE après homing
    lcd:         LCD2004     = None      # facultatif — pour affichage sécurité débit
    bz:          Buzzer      = None      # facultatif — pour beeps sécurité débit
```

### `ProgramBase` / `PROGRAMS` (programs.py)
```python
from programs import PROGRAMS, MachineContext

prg = PROGRAMS[1]          # Prg1..Prg5
prg.id         : int       # 1..5
prg.name       : str       # affiché LCD
prg.led_index  : int       # LED associée (1..5)

prg.start(ctx)             # set_valves + move_vic + pompe/air ON — bloquant si VIC bouge
prg.stop(ctx)              # relay pompe/air OFF uniquement — vannes en place
ok = prg.tick(ctx) -> bool # True=continuer, False=arrêt d'urgence sécurité débit
prg.lcd_info(ctx, elapsed_s) -> tuple[str,str,str,str]   # 4 × 20 chars
```

---

## config.py — Constantes clés

### VIC et moteur
| Constante | Valeur | Description |
|-----------|--------|-------------|
| `VIC_STEP_GPIO` | 27 | GPIO STEP/PUL |
| `VIC_DIR_GPIO` | 17 | GPIO DIR |
| `VIC_ENA_GPIO` | 22 | GPIO ENA (actif bas) |
| `VIC_TOTAL_STEPS` | 100 | Course totale |
| `VIC_NEUTRE_STEPS` | 50 | Position NEUTRE |
| `VIC_SPEED_SPS` | 10.0 | Vitesse de déplacement |
| `VIC_HOMING_CYCLES` | 10 | Cycles homing (≈ 3 min 30 au démarrage) |
| `VIC_POSITIONS` | `{0:50, 1:0, 2:100}` | Sélecteur → pas (0=NEUTRE par défaut) |
| `MOTOR_HOMING_FIRST_CLOSE_FACTOR` | 1.06 | Overcourse +6% |

### Relais et vannes
| Constante | Valeur | Description |
|-----------|--------|-------------|
| `RELAY_POMPE_GPIO` | 19 | GPIO pompe (actif haut) |
| `RELAY_AIR_GPIO` | 26 | GPIO air (actif haut) |
| `RELAY_POT_A_BOUE_GPIO` | 7 | V1 |
| `RELAY_EGOUTS_GPIO` | 8 | V2 |
| `RELAY_CUVE_TRAVAIL_GPIO` | 25 | V3 |
| `RELAY_EAU_PROPRE_GPIO` | 24 | V4 |

### Sécurité cuve vide — PRG2 et PRG4
| Constante | Valeur | Description |
|-----------|--------|-------------|
| `PRG2_CUVE_VIDE_MIN_LPM` | 50.0 | Seuil débit PRG2 (L/min) |
| `PRG2_CUVE_VIDE_TIMEOUT_S` | 5.0 | Durée continue sous le seuil avant arrêt |
| `PRG2_CUVE_VIDE_GRACE_S` | 5.0 | Délai de garde après `start()` |
| `PRG4_CUVE_VIDE_MIN_LPM` | 50.0 | Seuil débit PRG4 (L/min) |
| `PRG4_CUVE_VIDE_TIMEOUT_S` | 5.0 | Durée continue sous le seuil avant arrêt |
| `PRG4_CUVE_VIDE_GRACE_S` | 5.0 | Délai de garde après `start()` |
| `CUVE_VIDE_CONFIRM_PROGRAMS` | (2, 4) | Programmes exigeant la confirmation opérateur |
| `CUVE_VIDE_CONFIRM_TIMEOUT_S` | 5.0 | Abandon si pas de 2e appui |
| `CUVE_VIDE_ALERT_TIME_S` | 5.0 | Durée affichage "Plus de debit / Cuve vide" |

### Sécurité débit avec relance — PRG5
| Constante | Valeur | Description |
|-----------|--------|-------------|
| `PRG5_FLOW_MIN_LPM` | 50.0 | Seuil débit minimal (L/min) — **paramètre de réglage** |
| `PRG5_FLOW_TIMEOUT_S` | 10.0 | Durée avant déclenchement de la relance |
| `PRG5_FLOW_RESTART_COUNT` | 3 | Tentatives de relance |
| `PRG5_FLOW_RESTART_PAUSE_S` | 5.0 | Durée de chaque phase OFF puis ON |

### Affichage LCD — durées des écrans temporisés
| Constante | Écran concerné |
|-----------|----------------|
| `LCD_WELCOME_SCREEN_TIME_S` | Accueil démarrage machine — "CLEAN & PROTECH / SERENA 230V", avant le homing |
| `LCD_STOP_SCREEN_TIME_S` | Fin de programme — "PROGRAMME x / Arret..." (sauf PRG5) |
| `LCD_PRG5_SUMMARY_TIME_S` | Récapitulatif PRG5 — "Termine / Volume : x.xx L" |
| `LCD_BLINK_PERIOD_S` | Cadence des consignes clignotantes (1 s ON / 1 s OFF ; ≤ 0 = désactivé) |
| `LCD_ALTERNATE_PERIOD_S` | Cadence des textes alternés PRG1 (3 s par texte ; ≤ 0 = figé sur le 1er) |

### Écrans avant-programme
| Constante | Valeur | Description |
|-----------|--------|-------------|
| `PRG1_PREMSG_TIME_S` … `PRG5_PREMSG_TIME_S` | 10.0 | Durée d'affichage, une par programme |
| `PRG1_PREMSG_LINES` … `PRG5_PREMSG_LINES` | — | Message, 3 lignes max, 20 car./ligne, **ASCII pur** |
| `PREMSG_BEEP_COUNT` | 2 | Nombre de bips par salve |
| `PREMSG_BEEP_PAUSE_S` | 1.0 | Pause entre deux salves |
| `PREMSG_TIME_S` | dict | Table `{prg_id: durée}` construite depuis les constantes ci-dessus |
| `PREMSG_LINES` | dict | Table `{prg_id: lignes}` construite depuis les constantes ci-dessus |

> Un programme absent de `PREMSG_TIME_S` (ou avec une durée ≤ 0) n'affiche aucun écran.

### Vannes US Solid — temporisations
| Constante | Valeur | Description |
|-----------|--------|-------------|
| `VALVE_OPEN_CAPACITOR_CHARGE_S` | 15 | Attente après relay ON (course + recharge condo) |
| `VALVE_CLOSE_TRAVEL_S` | 16 | Attente après relay OFF (course mécanique) |

### Cycles AIR et EGOUTS
| Constante | Valeur | Description |
|-----------|--------|-------------|
| `PRG1_AIR_ON_S` / `PRG1_AIR_OFF_S` | 4.0 / 3.0 | Cycle AIR PRG1 |
| `PRG3_AIR_ON_S` / `PRG3_AIR_OFF_S` | 6.0 / 2.0 | Cycle AIR PRG3 |
| `PRG3_EGOUTS_OPEN_S` / `_CLOSED_S` | 15.0 / 30.0 | Cycle relay EGOUTS PRG3 |
| `PRG3_VIC_INVERT_PERIOD_S` | 50.0 | Attente en butée avant chaque traversée VIC |
| `PRG3_VIC_OVERCOURSE_FACTOR` | 1.15 | Overcourse traversée PRG3 → 115 pas |
| `PRG5_AIR_FAIBLE_ON_S` / `_OFF_S` | 2.0 / 2.0 | AIR mode 1 (faible) |
| `PRG5_AIR_MOYEN_ON_S` / `_OFF_S` | 4.0 / 2.0 | AIR mode 2 (moyen) |

### Débitmètre
| Constante | Valeur | Description |
|-----------|--------|-------------|
| `DEBITMETRE_K_FACTOR` | **variable** | Impulsions/litre — **constante de calibration** |
| `DEBITMETRE_GPIO` | 13 | GPIO interrupt |
| `DEBITMETRE_DEBOUNCE_US` | 400 | Filtre anti-rebond (µs) |

> ⚠️ **`DEBITMETRE_K_FACTOR` change en permanence, en test comme en production.**
> Une valeur différente de la référence n'est **pas** une anomalie — c'est le
> fonctionnement normal du réglage machine. Ne jamais « corriger » cette constante
> ni signaler son écart comme un bug.
> **Valeur de référence terrain à conserver en mémoire : `10.84` imp/L.**
> Valeur active au moment de la rédaction : `9.25`.

---

## Lancer un test / le programme

```bash
cd /home/bebl/Desktop/Clean-and-Protech/V5
python main.py                             # programme principal
python tests/test_i2c_scan.py             # scan I2C — vérifier MCP1/2 + LCD
python tests/test_lcd.py                  # afficheur LCD 20x4
python tests/test_mcp_inputs.py           # boutons PRG + sélecteurs VIC/AIR
python tests/test_homing.py               # homing VIC — séquence complète
python tests/test_vic.py                  # pilotage manuel VIC — saisie interactive
python tests/test_rodage_vic.py           # rodage VIC — cycles mécaniques
python tests/test_buzzer.py               # buzzer — 5 phases
python tests/test_debitmetre.py           # débitmètre — impulsions, débit, volume
python tests/test_relay_pompe.py          # relais POMPE
python tests/test_ev_air.py               # relais AIR (électrovanne)
python tests/test_vannes_us.py            # vannes — simulation des 5 programmes
python tests/test_vannes_aleatoire.py     # vannes — aléatoire simultané
python tests/test_main.py                 # test machine complet — JAMAIS LANCÉ
```

> Tous les scripts ajoutent `PROJECT_ROOT` au `sys.path` — pas besoin de `PYTHONPATH`.

---

## Règles d'architecture (identiques à V4)

1. **Aucune constante hardware en dur dans les modules.** Tout passe par `config.py`.
2. **Un seul handle lgpio** partagé via `gpio_handle` (singleton). Les modules appellent `gpio_handle.get()`, jamais `lgpio.gpiochip_open()` directement.
3. **`gpio_free()`** dans les `close()`, jamais `gpiochip_close()` (géré par `gpio_handle`).
4. **Injection de dépendance** : `VICController` et `Relays` reçoivent leur config depuis `config.py`, pas depuis les programmes.
5. **Cache OLAT** dans `IOBoard` pour les LEDs (évite RMW I2C à chaque écriture).
6. **Import des libs** : toujours `from libs.xxx import Yyy` depuis la racine du projet.

---

## Notes hardware

- **RPi 5** : chip GPIO est `gpiochip4` (pas `gpiochip0` comme RPi 4). Utiliser `lgpio`, pas `RPi.GPIO`.
- **DM860H ENA actif bas** : `ENA=0` active le driver, `ENA=1` le désactive (état sûr de défaut).
- **Vannes US Solid** : contact NO, actif haut. État sûr = relais OFF = GPIO LOW = vanne fermée.
- **Relais POMPE** : câblage "câble ON du variateur". Comportement potentiellement sujet à modification selon le variateur utilisé (voir commentaire dans `relays.py` et `config.py`).
- **Buzzer ×2 en parallèle** : piloté via transistor MOSFET N-CH YONGYUTAI AO3400A (30V / 5.8A / SOT-23). Résistance gate 100Ω en série, résistance pulldown 100kΩ gate-source. 2 diodes de roue libre Schottky 40V SMA (DO-214AC) au plus proche de chaque buzzer. GPIO RPi5 → 100Ω → gate MOSFET → drain → buzzers → VCC.
- **Adresses MCP1/MCP2** : à confirmer par `test_i2c_scan.py` après câblage PCB. Valeurs configurées : 0x24 (MCP1), 0x26 (MCP2).

---

## État du développement

### Modules — état initial V5

| Module          | État         | Notes                                         |
|-----------------|--------------|-----------------------------------------------|
| `gpio_handle`   | ✅ Stable    | Copie V4 — identique                          |
| `i2c_bus`       | ✅ Stable    | Copie V4 — identique                          |
| `mcp23017`      | ✅ Stable    | Copie V4 — identique                          |
| `lcd2004`       | ✅ Stable    | Copie V4 — identique                          |
| `buzzer`        | ✅ Stable    | Copie V4 — BUZZER_GPIO = 21 (×2 parallèle)   |
| `debitmetre`    | ✅ Stable    | Copie V4 — K_FACTOR = 10.84, GPIO = 13        |
| `logger`        | ✅ Stable    | Copie V4 — mention V5 dans docstring          |
| `io_board`      | ✅ Nouveau   | MCP3 supprimé, VIC 3 pos, méthode selector()  |
| `relays`        | ✅ Nouveau   | POMPE actif haut, + 4 vannes US Solid         |
| `vic`           | ✅ Nouveau   | VICController GPIO direct, homing 7 étapes    |
| `programs`      | ✅ Nouveau   | 4 vannes relais, sécurité débit, tick() bool  |
| `display`       | ✅ Nouveau   | SERENA 230V, VIC 3 positions                  |
| `main`          | ✅ Nouveau   | VICController, tick() bool, sécurité débit    |

### État des validations terrain

| Composant | État | Notes |
|---|---|---|
| Adresses MCP1/MCP2 | ✅ Validé | 0x24 / 0x26 confirmés |
| Vannes US Solid ×4 | ✅ Validé | Simultaneité OK avec nouvelle alim |
| Buzzer ×2 | ✅ **Validé** | Testé et validé terrain |
| Rodage VIC | ✅ **Validé** | `test_rodage_vic.py` testé et validé |
| Relais POMPE | ✅ Validé en usage | `main.py` tourne sans problème constaté |
| Relais AIR | ✅ Validé en usage | `main.py` tourne sans problème constaté |
| VIC homing + positions | ✅ Validé en usage | `main.py` tourne sans problème constaté |
| Boutons PRG (MCP1) | ✅ Validé en usage | `main.py` tourne sans problème constaté |
| Sélecteurs VIC + AIR (MCP2) | ✅ Validé en usage | `main.py` tourne sans problème constaté |
| Débitmètre K-factor | 🔄 **Calibration continue** | Constante de réglage — pas d'état « validé » |
| Sécurité débit | ⏳ À tester avec eau | PRG2/4/5 |
| `test_main.py` | ❌ **Jamais lancé** | Non utilisé — `main.py` valide directement en usage réel |

> **Méthode de validation retenue :** la validation se fait par l'usage réel de `main.py`
> sur machine, pas par `test_main.py`. Ce dernier existe mais n'a jamais servi.
> Les composants marqués « Validé en usage » le sont du point de vue opérateur :
> aucun dysfonctionnement constaté en fonctionnement normal.

### Historique des incidents connus

| Incident | Période | Statut |
|---|---|---|
| Sécurité débit — arrêts forcés PRG2/4/5 (débit 0.0 ou 27.7 L/min vs seuil 80) | 26–27 juin 2026 | Lié à la calibration en cours, seuil depuis abaissé |
| Horodatage logs qui saute (pas de RTC sur le RPi) | constaté 27/06 → 22/07 | Non traité — voir `BACKLOG.md` |

---

## Protocole buzzer — beeps machine

| Événement | Beeps | Moment | Fichier |
|-----------|-------|--------|---------|
| Bouton programme pressé | 1 | Immédiatement en IDLE (avant CONFIRM ou STARTING) | `main.py` |
| Écran avant-programme affiché | 2 bips × 8 salves | Pendant les 10 s, avant toute action machine | `main.py` |
| Initialisation terminée, timer démarré | 2 | Fin de `start()`, avant RUNNING | `main.py` |
| Sécurité débit déclenchée (PRG5) | 3 | Entrée dans `_pump_restart()` | `programs.py` |
| Sécurité cuve vide déclenchée (PRG2/PRG4) | 3 | Entrée dans `_cuve_vide_stop()` | `programs.py` |
| Programme arrêté (opérateur ou sécurité) | 1 | Fin de `stop()` en STOPPING | `main.py` |
| Arrêt machine (Ctrl+C ou erreur) | 3 longs | `finally` | `main.py` |

> Le 2e appui de confirmation cuve vide (état CONFIRM) ne produit **pas** de beep
> supplémentaire — seul le 1er appui en IDLE en génère un.

---

## Conventions de travail sur ce projet

1. **`DEBITMETRE_K_FACTOR` est une constante de calibration vivante.** Elle change
   constamment, en test comme en production. Ne pas la « corriger », ne pas signaler
   son écart avec la valeur de référence (10.84) comme une anomalie.
2. **Les seuils de sécurité débit sont des paramètres de réglage**, pas des valeurs figées.
3. **Le blocage de la boucle pendant `_pump_restart()` est volontaire** — objectif 100 % automatique.
4. **`BACKLOG.md`** contient les sujets identifiés et volontairement reportés.
   Ne rien y traiter sans validation explicite.
5. **La validation terrain passe par `main.py` en usage réel**, pas par `test_main.py`.
