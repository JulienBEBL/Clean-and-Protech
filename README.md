# Clean-and-Protech — Main unique

Projet de pilotage d’une machine (vannes pas à pas via 74HC595, V4V, air comprimé, débitmètre, LCD I²C, MCP3008).

> Architecture voulue : **un seul `main.py`** pour l’exécution.  
> Les drivers LCD + MCP3008 sont dans `_lib/` (non modifiés).

---

## Matériel (résumé)

- **Raspberry Pi 4B (4 Go)** — OS 64-bit.
- **74HC595 ×2** (bit-bang sur GPIO, pas de SPI matériel).
- **Drivers pas à pas (ex. DM542T)** pilotés via 2N2222 sur sorties Q0..Q7 des 74HC595.
- **Débitmètre** sur GPIO **26** (pull-up interne).
- **LCD I²C 16x2** (0x27).
- **MCP3008 ×2** sur SPI (pour boutons/programmes/sélecteur/air).
- **Électrovanne air**: relais sur GPIO **23**.

Pins utilisés par défaut (à adapter dans `machine.yaml`) :

| Rôle                   | GPIO |
|------------------------|:----:|
| 74HC595 DATA           |  21  |
| 74HC595 LATCH          |  20  |
| 74HC595 CLOCK          |  16  |
| Électrovanne air       |  23  |
| Débitmètre             |  26  |
| Moteurs (step)         | 5,6,12,13,14,15,18,19 |

---

## Installation

```bash
sudo apt update
sudo apt install -y python3-pip python3-dev i2c-tools
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
