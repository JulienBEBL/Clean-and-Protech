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
├── logs/                # Logs générés au runtime (un fichier par démarrage)
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
    ├── test_homing.py            # Homing VIC — séquence complète, résultat NEUTRE
    ├── test_vic.py               # Pilotage manuel VIC — saisie interactive
    ├── test_buzzer.py            # Buzzer — 5 phases : beep, repeat, sweep, puissance, ringtone
    ├── test_vannes_us.py         # Vannes — simulation séquentielle des 5 programmes
    ├── test_vannes_aleatoire.py  # Vannes — ouverture/fermeture simultanée aléatoire
    └── test_main.py              # Test machine complet — simulation opérateur
```

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
  - VIC1 (B0) → DEPART (0 pas)
  - VIC2 (B1) → NEUTRE (50 pas)
  - VIC3 (B2) → RETOUR (100 pas)
- **Port A INPUT** (pull-up) : A7..A5 = AIR1..AIR3 (actif bas)
  - AIR1 (faible)→A7, AIR2 (moyen)→A6, AIR3 (continu)→A5
  - Position 0 (aucun actif) = pas d'injection

---

## VIC — Driver JK-DM860H

**DIP switch :** courant et microstep réglés physiquement sur le driver.
- `DRIVER_MICROSTEP = 400` pas/tour (SW5..SW8 = ON)
- ENA actif bas : `VIC_ENA_ACTIVE_LEVEL = 0` (driver ON), `VIC_ENA_INACTIVE_LEVEL = 1` (sécurisé)

### Positions VIC

| Position | Pas | Étiquette | Sélecteur |
|----------|-----|-----------|-----------|
| DEPART   | 0   | DEP       | VIC1 (B0) |
| NEUTRE   | 50  | NEU       | VIC2 (B1) |
| RETOUR   | 100 | RET       | VIC3 (B2) |

### Séquence de homing (VIC_HOMING_CYCLES = 5)

```
1. Fermeture overcourse → butée DEPART
2. Ouverture overcourse → butée RETOUR
3. Fermeture overcourse → butée DEPART
4. Ouverture overcourse → butée RETOUR
5. Fermeture overcourse → butée DEPART
6. Ouverture overcourse → butée RETOUR
7. Fermeture 50 pas → NEUTRE
```

Overcourse = `VIC_TOTAL_STEPS × MOTOR_HOMING_FIRST_CLOSE_FACTOR` = 100 × 1.06 = **106 pas**.
Position finale : `vic_steps = 50` (NEUTRE).

---

## Programmes V5

| PRG | Nom            | Vannes ouvertes              | VIC    | Pompe | AIR              | Débit |
|-----|----------------|------------------------------|--------|-------|------------------|-------|
| 1   | PREM.VIDANGE   | POT_A_BOUE                   | DEPART | OFF   | AUTO 4s ON/3s OFF | Non  |
| 2   | VIDANGE CUVE   | CUVE_TRAVAIL, EGOUTS         | NEUTRE | ON    | OFF              | Oui   |
| 3   | SECHAGE        | — (EGOUTS: cycle relay 15s open/18s closed)| DEPART | OFF   | AUTO 6s ON/3s OFF | Non  |
| 4   | REMPLISSAGE    | EAU_PROPRE, POT_A_BOUE       | NEUTRE | ON    | OFF              | Oui   |
| 5   | DESEMBOUAGE    | POT_A_BOUE, CUVE_TRAVAIL     | MANU   | ON    | MANU (sélecteur) | Oui   |

### Comportement vannes et VIC au démarrage d'un programme
- `start()` : vannes séquentielles → puis **mini-homing VIC** (overcourse DEPART → recalage → move_to cible). Garantit la position physique réelle avant chaque programme.
- `stop()` : coupe relais POMPE + AIR uniquement. Vannes et VIC **laissées en place**.
- `start()` suivant : repositionne uniquement les vannes qui changent + mini-homing VIC.

### Sécurité débit (PRG2, PRG4, PRG5)
1. Si `flow_lpm() < FLOW_SAFETY_MIN_LPM (30 L/min)` en continu pendant `FLOW_SAFETY_TIMEOUT_S (10s)` :
2. Lance `FLOW_SAFETY_RESTART_COUNT (3)` tentatives : pompe OFF → `RESTART_PAUSE_S (10s)` → pompe ON → `RESTART_PAUSE_S (10s)` → vérif débit.
3. Si débit OK après relance → `tick()` retourne `True` → programme continue (vannes/VIC inchangés).
4. Si toutes les tentatives échouent → `tick()` retourne `False` → FSM → STOPPING → IDLE.

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
vic.homing()                    # ancrage + positionnement NEUTRE (50 pas)
vic.move_to(target_steps)       # déplacement absolu — no-op si déjà en place
vic.move_relative(delta)        # déplacement relatif (test/diagnostic)
vic.disable()                   # désactive driver (état sûr)
vic.position -> int             # position courante (fiable après homing)
vic.close()
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
| `VIC_HOMING_CYCLES` | 5 | Cycles homing |
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

### Sécurité débit
| Constante | Valeur | Description |
|-----------|--------|-------------|
| `FLOW_SAFETY_ENABLED_PROGRAMS` | (2, 4, 5) | Programmes concernés |
| `FLOW_SAFETY_MIN_LPM` | 30.0 | Seuil débit minimal (L/min) |
| `FLOW_SAFETY_TIMEOUT_S` | 10.0 | Durée avant déclenchement |
| `FLOW_SAFETY_RESTART_COUNT` | 3 | Tentatives de relance |
| `FLOW_SAFETY_RESTART_PAUSE_S` | 10.0 | Durée pause OFF/ON relance |

### Débitmètre
| Constante | Valeur | Description |
|-----------|--------|-------------|
| `DEBITMETRE_K_FACTOR` | 10.84 | Impulsions/litre (valeur terrain) |
| `DEBITMETRE_GPIO` | 13 | GPIO interrupt |

---

## Lancer un test / le programme

```bash
cd /home/bebl/Desktop/Clean-and-Protech/V5
python main.py                             # programme principal
python tests/test_i2c_scan.py             # scan I2C — vérifier MCP1/2 + LCD
python tests/test_homing.py               # homing VIC — séquence complète
python tests/test_vic.py                  # pilotage manuel VIC — saisie interactive
python tests/test_buzzer.py               # buzzer — 5 phases
python tests/test_vannes_us.py            # vannes — simulation des 5 programmes
python tests/test_vannes_aleatoire.py     # vannes — aléatoire simultané
python tests/test_main.py                 # test machine complet — simulation opérateur
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
| Débitmètre K-factor | ✅ Validé | 10.84 imp/L confirmé terrain |
| Vannes US Solid ×4 | ✅ Validé | Simultaneité OK avec nouvelle alim |
| Relais POMPE | ✅ OK sous réserve test user | À confirmer via `test_main.py` |
| Relais AIR | ✅ OK sous réserve test user | À confirmer via `test_main.py` |
| VIC homing + positions | ✅ OK sous réserve test user | À confirmer via `test_main.py` |
| Boutons PRG (MCP1) | ✅ OK sous réserve test user | À confirmer via `test_main.py` |
| Sélecteurs VIC + AIR (MCP2) | ✅ OK sous réserve test user | À confirmer via `test_main.py` |
| Buzzer ×2 | ⏳ À tester | `test_buzzer.py` |
| Sécurité débit | ⏳ À tester avec eau | Seuil 30 L/min PRG2/4/5 |

---

## Protocole buzzer — beeps machine

| Événement | Beeps | Moment | Fichier |
|-----------|-------|--------|---------|
| Bouton programme pressé | 1 | Immédiatement en IDLE → STARTING | `main.py` |
| Initialisation terminée, timer démarré | 2 | Fin de `start()`, avant RUNNING | `main.py` |
| Procédure sécurité débit déclenchée | 3 | Entrée dans `_pump_restart()` | `programs.py` |
| Programme arrêté (opérateur ou sécurité) | 1 | Fin de `stop()` en STOPPING | `main.py` |
| Arrêt machine (Ctrl+C ou erreur) | 3 longs | `finally` | `main.py` |
