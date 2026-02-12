# Clean-and-Protech — Main unique

Pilotage d’une machine via un script unique : moteurs pas à pas (via 74HC595), vanne 4 voies (V4V), programmes automatiques sélectionnés par boutons (MCP3008), affichage LCD I²C.

Architecture actuelle :

- Un seul script principal : `main.py` (exécutable directement).
- Drivers matériels dans `libs_tests/` :
  - `MCP3008_0.py`, `MCP3008_1.py`
  - `LCDI2C_backpack.py`
- Un fichier `machine.yaml` (référence/config) pour centraliser les constantes (pas, positions, GPIO, etc.).

---

## Fonctionnement général

- Lecture des boutons programmes via **MCP3008_1**.
- Lancement d’un des 5 programmes (1..5) en fonction du bouton actif.
- Chaque programme :
  - Ouvre/ferme une liste de vannes motorisées (stepper) via `74HC595`.
  - Gère la V4V :
    - **Mode auto** : homing puis position cible en pas selon `POS_V4V_PRG`.
    - **Mode manuel** (programme 5) : fenêtre de 10 s pour choisir une position avec le sélecteur.
  - Affiche l’état sur le **LCD I²C 16x2**.
  - Peut être arrêté en rappuyant sur le bouton du programme en cours.
- Les actions et états importants sont loggés dans le dossier `logs/` avec horodatage.

---

## Matériel (résumé)

- **Raspberry Pi 4B** (64-bit).
- **74HC595** pour piloter les directions, blank et LEDs.
- **Drivers pas à pas** commandés par le Pi (une sortie PUL par moteur).
- **LCD I²C 16x2** à l’adresse `0x27`.
- **MCP3008 x2** :
  - Un pour les boutons de programmes.
  - Un pour le sélecteur de V4V.
- **Électrovanne air** : prévue (variables `AIR_ON/AIR_OFF`), GPIO dédié à définir dans la config.
- **Vanne 4 voies (V4V)** contrôlée en pas.

---

## GPIO utilisés (conformes au script actuel)

### 74HC595 (bit-bang)

| Signal      | GPIO |
|------------|:----:|
| DATA (DS)  |  21  |
| LATCH      |  20  |
| CLOCK      |  16  |

### Moteurs pas à pas (PUL)

Mappés dans `motor_map` :

| Moteur   | GPIO |
|----------|:----:|
| V4V      |  5   |
| clientG  |  27  |
| clientD  |  26  |
| egout    |  22  |
| boue     |  13  |
| pompeOUT |  17  |
| cuve     |  6   |
| eau      |  19  |

> La direction de tous les moteurs est gérée via les bits du 74HC595 (`bits_dir`) avec `DIR_OPEN` / `DIR_CLOSE`.

### Divers

- LCD I²C : adresse `0x27`, 16 colonnes.
- Seuils d’entrées analogiques (MCP3008) :
  - `SEUIL = 1010` pour détection boutons/sélecteur.
- V4V :
  - `STEP_HOME_V4V = 800`
  - Positions sélecteur : `0, 200, 400, 600, 800` pas.

---

## Installation (Raspberry Pi)

```bash
sudo apt update
sudo apt install -y python3-pip python3-dev i2c-tools
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
