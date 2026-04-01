# Clean & Protech V4 — Documentation projet

## Vue d'ensemble

Système embarqué industriel sur **Raspberry Pi 5** pour le pilotage d'une machine de nettoyage et protection.
Contrôle 8 moteurs pas-à-pas (vannes), 2 relais, un buzzer, un débitmètre et un HMI (LCD + boutons + sélecteurs).

**Stack technique :**
- Python 3.11+
- `lgpio` — GPIO et PWM (RPi 5 uniquement, gpiochip4)
- `smbus2` — I2C
- MCP23017 — 3 expandeurs I/O 16 bits via I2C

---

## Structure du projet

```
V4/
├── config.py            # Source de vérité unique — toutes les constantes hardware
├── CLAUDE.md            # Ce fichier
├── libs/
│   ├── __init__.py
│   ├── gpio_handle.py   # Handle lgpio singleton (partagé par tous les drivers)
│   ├── i2c_bus.py       # Bus I2C avec retry engine
│   ├── mcp23017.py      # Driver bas niveau MCP23017
│   ├── lcd2004.py       # Driver LCD 20x4 I2C
│   ├── io_board.py      # Couche métier : LEDs, boutons, sélecteurs, ENA, DIR
│   ├── moteur.py        # Contrôleur moteurs pas-à-pas (DM860H)
│   ├── buzzer.py        # Driver buzzer piézo passif (PWM)
│   ├── debitmetre.py    # Driver débitmètre à impulsions (interrupt GPIO)
│   └── relays.py        # Driver relais POMPE et AIR
└── tests/
    ├── test_i2c_scan.py            # Scan bus I2C, vérification des 4 périphériques
    ├── test_lcd.py                 # Tests LCD (init, write, centrage, ticker)
    ├── test_io_board.py            # IOBoard temps réel : boutons, LEDs, VIC, AIR
    ├── test_buzzer.py              # Buzzer : bips, fréquences, sonnerie
    ├── test_relays.py              # Relais POMPE et AIR
    ├── test_debitmetre.py          # Débitmètre : débit instantané, volume cumulé
    ├── test_moteur_identification.py  # Identification physique des drivers (ENA blink)
    ├── test_moteur.py              # Ouverture/fermeture d'un moteur avec rampe
    └── test_homing.py              # Homing + ouverture séquentielle des 8 moteurs
```

---

## Règles d'architecture

1. **Aucune constante hardware en dur dans les modules.** Tout passe par `config.py`.
2. **Un seul handle lgpio** partagé via `gpio_handle` (singleton). Les modules appellent `gpio_handle.get()`, jamais `lgpio.gpiochip_open()` directement.
3. **Injection de dépendance** : `IOBoard` est passé au constructeur de `MotorController`. Jamais instancié en interne.
4. **`gpio_free()`** dans les `close()`, jamais `gpiochip_close()` (le chip est géré par `gpio_handle`).
5. **Cache OLAT** dans `IOBoard` pour éviter les transactions I2C read-modify-write sur chaque écriture de pin.
6. **Import des libs** : toujours `from libs.xxx import Yyy` depuis la racine du projet.

### Pattern d'initialisation standard

```python
import libs.gpio_handle as gpio_handle
from libs.i2c_bus import I2CBus
from libs.io_board import IOBoard
from libs.moteur import MotorController

gpio_handle.init()                  # ouvre gpiochip4 (idempotent)

with I2CBus() as bus:
    io = IOBoard(bus)
    io.init()
    with MotorController(io) as motors:
        motors.homing()
        motors.ouverture("CUVE_TRAVAIL")

gpio_handle.close()                 # ferme le chip en dernier
```

---

## Hardware — GPIO BCM (Raspberry Pi 5)

| Signal          | GPIO BCM | Composant          |
|-----------------|----------|--------------------|
| PUL moteur 1    | 17       | Driver RETOUR      |
| PUL moteur 2    | 27       | Driver POT_A_BOUE  |
| PUL moteur 3    | 22       | Driver VIC         |
| PUL moteur 4    | 5        | Driver CUVE_TRAVAIL|
| PUL moteur 5    | 18       | Driver EGOUTS      |
| PUL moteur 6    | 23       | Driver DEPART      |
| PUL moteur 7    | 24       | Driver EAU_PROPRE  |
| PUL moteur 8    | 25       | Driver POMPE       |
| Buzzer          | 26       | Buzzer piézo       |
| Débitmètre      | 21       | Capteur à impulsions |
| Relay POMPE OFF | 16       | Relais POMPE       |
| Relay AIR       | 20       | Relais AIR         |

> Chip lgpio : `gpiochip4` (index 4) — spécifique Raspberry Pi 5.

---

## Hardware — I2C (bus 1, 100 kHz)

| Composant | Adresse | Rôle                                      |
|-----------|---------|-------------------------------------------|
| MCP1      | 0x24    | Port A : LEDs 1..6 — Port B : boutons PRG 1..6 |
| MCP2      | 0x26    | Port A : sélecteur AIR — Port B : sélecteur VIC |
| MCP3      | 0x25    | Port A : DIR moteurs — Port B : ENA moteurs |
| LCD 20x4  | 0x27    | Afficheur HMI                             |

---

## Moteurs — Mapping

**Drivers DM860H** — DIP switch `10111111` :
- SW1=ON SW2=OFF SW3=ON → Courant crête : **3.78 A**
- SW4=ON → courant plein en pause (pas de réduction)
- SW5..SW8=ON → Résolution : **400 pas/tour** (microstep)
- ENA actif bas (câblage inversé) : `ENA=0` → driver ON

| Nom métier    | ID driver | GPIO PUL (BCM) |
|---------------|-----------|----------------|
| RETOUR        | 1         | 17             |
| POT_A_BOUE    | 2         | 27             |
| VIC           | 3         | 22             |
| CUVE_TRAVAIL  | 4         | 5              |
| EGOUTS        | 5         | 18             |
| DEPART        | 6         | 23             |
| EAU_PROPRE    | 7         | 24             |
| POMPE         | 8         | 25             |

**ENA / DIR** : contrôlés via MCP3 (I2C), pas via GPIO direct.
- MCP3 Port B : ENA1..ENA8 → pins B0..B7
- MCP3 Port A : DIR1..DIR8 → pins A7..A0 (inversé — moteur 1 sur A7)
- OUVERTURE = niveau haut (1), FERMETURE = niveau bas (0)

---

## IOBoard — PCB

### MCP1 (0x24) — Programmes
- **Port B INPUT** (pull-up) : B0..B5 = PRG1..PRG6 (actif bas)
- **Port A OUTPUT** : A2..A7 = LED1..LED6 (actif haut)
  - LED1→A2, LED2→A3, ..., LED6→A7

### MCP2 (0x26) — Sélecteurs
- **Port B INPUT** (pull-up) : B0..B4 = VIC1..VIC5 (actif bas)
- **Port A INPUT** (pull-up) : A7..A5 = AIR1..AIR3 (actif bas)
  - AIR1 (faible)→A7, AIR2 (moyen)→A6, AIR3 (continu)→A5
  - Position 0 (aucun actif) = pas d'injection

### MCP3 (0x25) — Drivers moteurs
- **Port B OUTPUT** : B0..B7 = ENA1..ENA8 (actif bas)
- **Port A OUTPUT** : A7..A0 = DIR1..DIR8

---

## API des librairies

### `gpio_handle`
```python
gpio_handle.init(chip_index=4)   # ouvre gpiochip — idempotent
gpio_handle.get()                # retourne le handle (ou raise si non init)
gpio_handle.is_open() -> bool
gpio_handle.close()              # ferme le chip — idempotent
```

### `I2CBus`
```python
with I2CBus() as bus:            # bus_id=1, freq=100kHz, retries=2
    bus.write_u8(addr, reg, val)
    bus.read_u8(addr, reg)
    bus.write_block(addr, reg, data)
    bus.read_block(addr, reg, length)
    bus.scan() -> list[int]      # adresses détectées
```
Exceptions : `I2CError`, `I2CNotOpenError`, `I2CNackError`, `I2CIOError`

### `MCP23017`
```python
mcp = MCP23017(bus, address)
mcp.init(force=True)
mcp.set_port_direction(port, mask)   # port = "A" ou "B"
mcp.set_pullup(port, mask)
mcp.write_port(port, value)
mcp.write_pin(port, pin, value)
mcp.read_port(port) -> int
mcp.read_pin(port, pin) -> int
```

### `LCD2004`
```python
lcd = LCD2004(bus)               # adresse 0x27, 20 cols, 4 rows
lcd.init()
lcd.clear()
lcd.clear_line(line)             # line 1..4
lcd.write(line, text)            # écrit sur la ligne (tronqué/padé à 20 chars)
lcd.write_centered(line, text)   # centré sur 20 chars
lcd.backlight(on=True)
```

### `IOBoard`
```python
io = IOBoard(bus)
io.init()

# LEDs (1..6)
io.set_led(index, state)         # state = 0/1
io.set_all_leds(state)

# Boutons PRG (1..6) — actif bas
io.read_btn(index) -> int        # niveau brut
io.read_btn_active(index) -> int # 1 si appuyé

# Sélecteur VIC (1..5) — actif bas
io.read_vic_active(index) -> int # 1 si sélectionné

# Sélecteur AIR — actif bas
io.read_air_mode() -> int        # 0=aucun, 1=faible, 2=moyen, 3=continu
io.read_air_active(index) -> int # 1 si position active (1..3)

# Drivers moteurs
io.set_ena(motor_id, level)      # ENA_ACTIVE_LEVEL=0 / ENA_INACTIVE_LEVEL=1
io.set_dir(motor_id, direction)  # 'ouverture' ou 'fermeture'
io.disable_all_drivers()         # état sûr
```

### `MotorController`
```python
with MotorController(io) as motors:

    # --- ENA ---
    motors.enable_driver(name)
    motors.disable_driver(name)
    motors.enable_all_drivers()
    motors.disable_all_drivers()

    # --- Mouvements (1 moteur) ---
    motors.move_steps(name, steps, direction, speed_sps=config.MOTOR_DEFAULT_CONST_SPEED_SPS)
    motors.move_steps_ramp(name, steps, direction, speed_sps, accel, decel)
    #   → accel doit être < decel, speed_sps >= decel

    # --- Mouvements métier ---
    motors.ouverture(name)        # course complète avec rampe — paramètres OUVERTURE de config.py
    motors.fermeture(name)        # course complète avec rampe — paramètres FERMETURE de config.py
    motors.homing()               # fermeture synchrone TOUS les moteurs — reset position au démarrage
```

Noms acceptés (insensible à la casse, tirets/espaces tolérés) :
`POT_A_BOUE`, `POMPE`, `CUVE_TRAVAIL`, `RETOUR`, `EGOUTS`, `VIC`, `DEPART`, `EAU_PROPRE`

> **Note** : `move_steps_multi()` a été retiré (à refaire ultérieurement). Pour déplacer plusieurs moteurs simultanément, utiliser `homing()` comme référence d'implémentation.

### `Buzzer`
```python
bz = Buzzer()
bz.open()
bz.beep(time_ms=100, power_pct=50, repeat=1, freq_hz=2000, gap_ms=60)
bz.on(freq_hz=2000, duty_pct=50)
bz.off()
bz.play(notes)                   # séquence [(freq, duty, ms), ...]
bz.ringtone_startup()
bz.close()
```

### `FlowMeter`
```python
fm = FlowMeter()                 # gpio=21, k_factor=11.15 imp/L
fm.open()
fm.flow_lpm(window_s=1.0) -> float   # débit instantané L/min
fm.total_liters() -> float           # volume cumulé
fm.total_pulses() -> int
fm.reset_total()
fm.close()
```

### `Relays`
```python
relays = Relays()
relays.open()
relays.set_pompe_on()
relays.set_pompe_off()
relays.set_air_on(time_s=None)   # time_s=None → ON indéfini
relays.set_air_off()
relays.tick()                    # à appeler dans la boucle principale (timer AIR)
relays.pompe_is_on -> bool
relays.air_is_on -> bool
relays.close()
```

---

## config.py — Constantes clés

### Moteurs
| Constante                      | Valeur   | Description                          |
|-------------------------------|----------|--------------------------------------|
| `DRIVER_MICROSTEP`            | 400      | Pas par tour                         |
| `MOTOR_MIN_SPEED_SPS`         | 50.0     | Vitesse minimale validée (sps)        |
| `MOTOR_MAX_SPEED_SPS`         | 8000.0   | Vitesse maximale validée (sps)        |
| `MOTOR_OUVERTURE_STEPS`       | 3000     | Course ouverture complète             |
| `MOTOR_FERMETURE_STEPS`       | 3900     | Course fermeture complète             |
| `MOTOR_OUVERTURE_SPEED_SPS`   | 1000.0   | Vitesse croisière ouverture           |
| `MOTOR_OUVERTURE_ACCEL_SPS`   | 200.0    | Vitesse départ rampe ouverture        |
| `MOTOR_OUVERTURE_DECEL_SPS`   | 800.0    | Vitesse fin rampe ouverture           |
| `MOTOR_FERMETURE_SPEED_SPS`   | 1000.0   | Vitesse croisière fermeture           |
| `MOTOR_FERMETURE_ACCEL_SPS`   | 600.0    | Vitesse départ rampe fermeture        |
| `MOTOR_FERMETURE_DECEL_SPS`   | 800.0    | Vitesse fin rampe fermeture           |
| `MOTOR_DEFAULT_CONST_SPEED_SPS` | 1200.0 | Vitesse pour `move_steps()`           |
| `MOTOR_HOMING_STEPS`          | 4200     | Course homing (10.5 tours)            |
| `MOTOR_HOMING_SPEED_SPS`      | 2000.0   | Vitesse homing                        |
| `MOTOR_RAMP_ACCEL_TIME_S`     | 1.5      | Durée nominale phase accélération     |
| `MOTOR_RAMP_DECEL_TIME_S`     | 1.5      | Durée nominale phase décélération     |
| `MOTOR_MIN_PULSE_US`          | 50       | Demi-impulsion minimale (µs)          |
| `MOTOR_ENA_SETTLE_MS`         | 5        | Délai ENA → premier pas               |

### Buzzer
| Constante                  | Valeur | Description                      |
|---------------------------|--------|----------------------------------|
| `BUZZER_DEFAULT_FREQ_HZ`  | 2000   | Fréquence de résonance           |
| `BUZZER_FREQ_MIN_HZ`      | 500    | Limite basse (−60 dB en dessous) |
| `BUZZER_FREQ_MAX_HZ`      | 4500   | Limite haute (chute au-delà)     |
| `BUZZER_BEEP_TIME_MS`     | 100    | Durée bip par défaut             |
| `BUZZER_BEEP_POWER_PCT`   | 50     | Puissance bip par défaut         |
| `BUZZER_BEEP_REPEAT`      | 1      | Répétitions par défaut           |
| `BUZZER_BEEP_GAP_MS`      | 60     | Pause entre répétitions          |

### Débitmètre
| Constante                  | Valeur | Description                     |
|---------------------------|--------|---------------------------------|
| `DEBITMETRE_K_FACTOR`     | 11.15  | Impulsions par litre            |
| `DEBITMETRE_DEBOUNCE_US`  | 400    | Filtre anti-rebond (µs)         |

---

## Tests disponibles

| Fichier                        | Objectif                                                  | Statut |
|-------------------------------|-----------------------------------------------------------|--------|
| `test_i2c_scan.py`            | Scan I2C, vérifie 4 adresses (MCP1/2/3 + LCD)            | ✅ OK  |
| `test_lcd.py`                 | Init, write, centrage, backlight, ticker temps réel       | ✅ OK  |
| `test_io_board.py`            | LEDs miroir PRG, VIC, AIR — affichage LCD 10 Hz           | ✅ OK  |
| `test_buzzer.py`              | Bips, balayage fréquentiel, sonnerie startup              | ✅ OK  |
| `test_relays.py`              | POMPE ON/OFF, AIR ON/OFF, AIR timer                       | ✅ OK  |
| `test_debitmetre.py`          | Débit L/min + volume cumulé en continu                    | ⏳ non testé |
| `test_moteur_identification.py` | ENA blink 10× par driver — identification physique      | ✅ OK  |
| `test_moteur.py`              | Ouverture + fermeture avec rampe sur un moteur            | ✅ OK  |
| `test_homing.py`              | Homing tous moteurs + ouverture séquentielle 1→8         | ⏳ non testé |

---

## Lancer un test

```bash
cd /home/julien/Clean-and-Protech/V4
python tests/test_moteur.py
python tests/test_homing.py
```

> Tous les scripts ajoutent `PROJECT_ROOT` au `sys.path` — pas besoin de `PYTHONPATH`.

---

## Notes hardware

- **RPi 5** : chip GPIO est `gpiochip4` (pas `gpiochip0` comme RPi 4). Utiliser `lgpio`, pas `RPi.GPIO`.
- **DM860H DIP switch** : la configuration physique `10111111` est documentée dans `config.py` (`DRIVER_DIP_SWITCH`).
- **ENA câblage inversé** : `ENA=0` active le driver, `ENA=1` le coupe. Constantes `ENA_ACTIVE_LEVEL=0` / `ENA_INACTIVE_LEVEL=1`.
- **Active-low** : boutons PRG, sélecteurs VIC et AIR ont tous des pull-ups internes MCP23017 et sont lus en logique inversée.
- **LCD ligne 4** : bug `_norm_line()` appelé deux fois (double conversion de ligne) — **corrigé** dans `lcd2004.py`. L'adresse DDRAM ligne 4 est `0xD4` (0x80 + 0x54).
- **AIR sélecteur 3 modes** : câblage A7/A6/A5 sur MCP2. Le mode 0 (aucun actif) correspond à la position physique 0 du sélecteur rotatif.

---

## État du développement

### Librairies — terminées ✅
| Module          | État     | Notes                                    |
|-----------------|----------|------------------------------------------|
| `gpio_handle`   | ✅ Stable | Singleton, testé en production           |
| `i2c_bus`       | ✅ Stable | Retry engine, 4 exceptions typées        |
| `mcp23017`      | ✅ Stable | BANK=0, force init                       |
| `lcd2004`       | ✅ Stable | Bug ligne 4 corrigé                      |
| `io_board`      | ✅ Stable | AIR 3 modes (câble rebranché)            |
| `buzzer`        | ✅ Stable | PWM lgpio, beep/play/ringtone            |
| `relays`        | ✅ Stable | POMPE + AIR, timer non-bloquant          |
| `debitmetre`    | ✅ Écrit  | Interrupt lgpio, thread-safe — non testé |
| `moteur`        | ✅ Stable | Rampe, homing, enable/disable all        |

### Travaux réalisés aujourd'hui (2026-04-01)
- **`moteur.py`** : ajout `enable_all_drivers()`, paramètre `speed_sps` avec valeur par défaut dans `move_steps()`, suppression de `move_steps_multi()` et `_run_ramp_multi()`, réorganisation en sections (Lifecycle / API ENA / API Mouvements / Internals)
- **`moteur.py`** : ajout `homing()` — fermeture synchrone de tous les moteurs à haute vitesse, utilisée au démarrage pour resetter la position
- **`config.py`** : séparation des profils ouverture/fermeture (`MOTOR_OUVERTURE_*` / `MOTOR_FERMETURE_*`), ajout `MOTOR_DEFAULT_CONST_SPEED_SPS`, `MOTOR_HOMING_STEPS`, `MOTOR_HOMING_SPEED_SPS`
- **`test_homing.py`** : nouveau test — homing + ouverture séquentielle des 8 moteurs dans l'ordre ID 1→8
- **`CLAUDE.md`** : création de ce fichier de documentation

### À faire
- [ ] Tester `test_homing.py` sur la machine
- [ ] Tester `test_debitmetre.py`
- [ ] Implémenter `move_steps_multi()` (synchronisation multi-moteurs, à refaire)
- [ ] Implémenter le programme principal (`main.py`)
- [ ] Tests d'endurance (rodage cycles ouverture/fermeture)
