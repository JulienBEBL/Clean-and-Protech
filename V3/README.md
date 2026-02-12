## Clean-and-Protech – Version V3 (simple)

Pilotage d’une machine de nettoyage via un **Raspberry Pi** :

- 8 moteurs pas à pas via drivers **DM860H** (STEP sur GPIO, DIR/ENA via MCP23017).
- 3 **MCP23017** I²C (boutons/LEDs programmes, sélecteurs VIC/AIR, drivers moteurs).
- Écran **LCD I²C 20x4**.
- Relais **AIR** et **POMPE**, débitmètre, buzzer.
- Logique de **programmes simples = chrono + pompe** (pas de séquences complexes pour l’instant).

L’objectif de V3 est d’avoir **un code lisible, modifiable, sans sur-architecture**.

---

## Structure du projet

- `main.py` : point d’entrée principal.
- `config/`
  - `config.yaml` : **toute la configuration** (GPIO, I²C, moteurs, programmes, sécurité).
- `libs/`
  - `i2c_devices.py` : drivers simples pour `MCP23017` et `LCD20x4`.
  - `motors.py` : gestion de base des moteurs pas à pas (classe `MotorManager`).
- `tests/`
  - `test_basic.py` : tests de câblage utilisés par le **MODE_TEST** de `main.py`.
  - `test_lcd.py` : test dédié de l’écran LCD (affiche la config programmes/sécurité).
  - `test_mcp_inputs.py` : lecture des entrées (boutons PRG, sélecteur VIC, AIR).
  - `test_mcp_outputs.py` : test des sorties (LEDs programmes, relais AIR/POMPE).
- `logs/` : fichiers journaux horodatés (créé automatiquement ou manuellement).
- `.gitignore` : ignore `logs/`, `__pycache__/`, environnements virtuels, etc.
- `requirements.txt` : dépendances Python minimales.

---

## Fonctionnement général

- Au démarrage, `main.py` :
  - lit `config/config.yaml`,
  - initialise GPIO, I²C, MCP23017, LCD, moteurs et relais,
  - configure le logging dans le dossier `logs/`.
- Si `mode.test: true` dans `config.yaml` :
  - exécute une série de tests : I²C, LCD, relais, buzzer, moteurs, boutons/LEDs.
- Sinon (mode "production") :
  - lit les **boutons programmes** sur MCP1,
  - lance le programme `n` correspondant (si `enabled: true`),
  - pour chaque programme :
    - applique la logique de sécurité définie dans `programs.[n].safety` (AIR/VIC/POMPE),
    - démarre un **chrono**,
    - met en route la **pompe** (si `pump.mode: auto` et `start_on_program: true`),
    - mesure le **débit** et calcule un volume approximatif via le débitmètre,
    - affiche sur le LCD : temps, débit, volume, états de sécurité (AIR/POMPE),
    - s’arrête si on rappuie sur le bouton du programme (`PRGx`) ou si un `default_duration_sec` > 0 est atteint.

Tous les événements importants sont loggés dans `logs/*.log` avec horodatage.

---

## Matériel (résumé)

- **Raspberry Pi 5** (BCM / Python 3).
- **8 moteurs pas à pas** via drivers DM860H :
  - STEP (PUL) directement sur les GPIO (configurés dans `config.yaml`).
  - DIR / ENA regroupés sur le **MCP23017 #3**.
- **MCP23017** :
  - `0x24` : boutons + LEDs programmes.
  - `0x25` : sélecteurs VIC / AIR.
  - `0x26` : DIR + ENA des drivers moteurs.
- **LCD I²C 20x4** à l’adresse `0x27`.
- **Relais** : AIR + POMPE (sur GPIO, actifs HIGH).
- **Débitmètre YF-DN50** (front descendant, GPIO déclaré dans `config.yaml`).
- **Buzzer** (GPIO déclaré dans `config.yaml`).

Tous les numéros de GPIO, adresses I²C et paramètres sont centralisés dans `config/config.yaml`.

---

## Configuration (config/config.yaml)

Les principales sections :

- `mode` : choix du **MODE_TEST**.
- `i2c` : bus I²C + adresses des 3 MCP23017 + LCD.
- `gpio` : mapping des GPIO (STEP moteurs, relais, débitmètre, buzzer).
- `motors` : pas par tour, vitesses min/max, moteur VIC dédié.
- `mcp23017` :
  - `mcp1_programs` : banques/bits pour boutons et LEDs des programmes.
  - `mcp2_selectors` : bits pour sélecteur VIC et entrée AIR.
  - `mcp3_drivers` : banque DIR/ENA + bit par moteur, ENA actif bas.
- `programs` :
  - pour chaque programme (1..N) :
    - `name`, `enabled`, `default_duration_sec`,
    - `safety.air.mode` (`manual` ou `blocked`),
    - `safety.vic.mode` (`manual` ou `auto` + `auto_position_index` pour plus tard),
    - `safety.pump.mode` (`manual` ou `auto`, `start_on_program`, `stop_on_program_end`).

Tu modifies **uniquement ce fichier** pour adapter la machine (câblage, timings, sécurité).

---

## Installation et exécution (Raspberry Pi)

sudo apt update
sudo apt install -y python3-pip python3-dev i2c-tools

cd V3
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Lancer le programme principal
python main.py

# Lancer un test dédié, par exemple LCD
python tests/test_lcd.py