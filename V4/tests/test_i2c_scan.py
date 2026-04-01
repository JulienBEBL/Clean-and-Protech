"""
test_i2c_scan.py — Scan du bus I2C et vérification des périphériques attendus

Vérifie que les 4 périphériques obligatoires répondent :
    0x24  MCP1 — Programmes (LEDs + boutons PRG)
    0x25  MCP3 — Drivers moteurs (ENA + DIR)
    0x26  MCP2 — Sélecteurs (VIC + AIR)
    0x27  LCD  — Écran HD44780 via PCF8574

Affiche clairement les périphériques trouvés, manquants et inattendus.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from libs.i2c_bus import I2CBus

# Périphériques attendus sur le bus
EXPECTED: dict[int, str] = {
    config.MCP1_ADDR: "MCP1  — Programmes  (LEDs + PRG)",
    config.MCP3_ADDR: "MCP3  — Drivers     (ENA + DIR)",
    config.MCP2_ADDR: "MCP2  — Sélecteurs  (VIC + AIR)",
    config.LCD_ADDR:  "LCD   — Écran HD44780 / PCF8574",
}


def main() -> None:
    print(f"Scan I2C — bus {config.I2C_BUS_ID} @ {config.I2C_FREQ_HZ // 1000} kHz\n")

    with I2CBus() as bus:
        found = bus.scan()

    # Résultats bruts
    print(f"Adresses détectées ({len(found)}) :")
    for addr in found:
        label = EXPECTED.get(addr, "??? inconnu")
        print(f"  0x{addr:02X}  {label}")

    # Vérification périphériques attendus
    print()
    all_ok = True
    for addr, label in EXPECTED.items():
        if addr in found:
            print(f"  [OK]      0x{addr:02X}  {label}")
        else:
            print(f"  [ABSENT]  0x{addr:02X}  {label}")
            all_ok = False

    # Périphériques inattendus
    unexpected = [a for a in found if a not in EXPECTED]
    if unexpected:
        print()
        print("Périphériques inattendus :")
        for addr in unexpected:
            print(f"  [?]       0x{addr:02X}")

    print()
    if all_ok:
        print("Résultat : OK — tous les périphériques répondent.")
    else:
        print("Résultat : ÉCHEC — un ou plusieurs périphériques sont absents.")


if __name__ == "__main__":
    main()
