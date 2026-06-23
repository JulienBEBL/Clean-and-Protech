"""
test_i2c_scan.py — Scan du bus I2C V5.

Scanne le bus I2C et vérifie la présence des 3 périphériques attendus :
    MCP1 (0x24) — boutons PRG + LEDs
    MCP2 (0x26) — sélecteur VIC + AIR
    LCD  (0x27) — afficheur 20x4

Note : MCP3 (0x25) n'existe plus en V5. Si détecté, c'est une erreur de câblage.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from libs.i2c_bus import I2CBus


_EXPECTED: dict[int, str] = {
    config.MCP1_ADDR: "MCP1 — boutons PRG + LEDs",
    config.MCP2_ADDR: "MCP2 — sélecteur VIC + AIR",
    config.LCD_ADDR:  "LCD 20x4",
}

_UNEXPECTED_V4 = 0x25  # MCP3 — présent en V4, absent en V5


def main() -> None:
    print("=" * 54)
    print("  SCAN I2C — Clean & Protech V5")
    print("=" * 54)
    print(f"  Bus : /dev/i2c-{config.I2C_BUS_ID}")
    print(f"  Attendus : {[hex(a) for a in _EXPECTED]}\n")

    with I2CBus() as bus:
        found = bus.scan()

    print(f"  Adresses détectées ({len(found)}) :")
    for addr in found:
        label = _EXPECTED.get(addr, "")
        warn  = " ← INATTENDU (MCP3 V4 ?)" if addr == _UNEXPECTED_V4 else ""
        print(f"    0x{addr:02X}  {label}{warn}")

    print()
    ok = True
    for addr, name in _EXPECTED.items():
        present = addr in found
        status  = "OK" if present else "MANQUANT"
        print(f"  {name:<30} 0x{addr:02X}  {status}")
        if not present:
            ok = False

    if _UNEXPECTED_V4 in found:
        print(f"\n  ATTENTION : 0x25 (MCP3) détecté — absent en V5 (vérifier câblage)")
        ok = False

    print()
    print("  Résultat global :", "OK" if ok else "ERREUR — vérifier câblage et adresses")
    print("=" * 54)


if __name__ == "__main__":
    main()
