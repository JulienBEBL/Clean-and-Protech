"""
test_vannes_us.py — Test des vannes US Solid 24VDC V1 et V2 — V5.

Sequence :
    1. Ouverture V1 POT_A_BOUE  -> attente VALVE_OPEN_CAPACITOR_CHARGE_S
    2. Ouverture V2 EGOUTS       -> attente VALVE_OPEN_CAPACITOR_CHARGE_S
    3. Fermeture V1 POT_A_BOUE  -> attente VALVE_CLOSE_TRAVEL_S
    4. Fermeture V2 EGOUTS       -> attente VALVE_CLOSE_TRAVEL_S

Les vannes US Solid ont une course mecanique lente (~10-20s a l'ouverture
comme a la fermeture). Ne jamais couper l'alimentation pendant les temporisations.

Materiel implique :
    GPIO  7 -> relais V1 -> vanne POT_A_BOUE  (US Solid 24VDC NO)
    GPIO  8 -> relais V2 -> vanne EGOUTS       (US Solid 24VDC NO)

Ctrl+C ferme les vannes actives et quitte proprement.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
import libs.gpio_handle as gpio_handle
from libs.i2c_bus import I2CBus
from libs.lcd2004 import LCD2004
from libs.relays import Relays

_COLS = config.LCD_COLS  # 20

_V1 = ("POT_A_BOUE", config.RELAY_POT_A_BOUE_GPIO)
_V2 = ("EGOUTS",     config.RELAY_EGOUTS_GPIO)


# ============================================================
# Helpers
# ============================================================

def _pad(s: str) -> str:
    return s[:_COLS].ljust(_COLS)


def _sep(title: str) -> None:
    print(f"\n{'=' * 54}")
    print(f"  {title}")
    print(f"{'=' * 54}")


def _countdown(lcd: LCD2004, valve_name: str, action: str, duration: float) -> None:
    t0 = time.monotonic()
    while True:
        elapsed   = time.monotonic() - t0
        remaining = max(0.0, duration - elapsed)
        lcd.write_centered(1, "TEST VANNES")
        lcd.write(2, _pad(valve_name))
        lcd.write(3, _pad(action))
        lcd.write(4, _pad(f"Attente : {remaining:5.1f}s"))
        print(f"  {action:<20} {remaining:5.1f}s\r", end="", flush=True)
        if elapsed >= duration:
            break
        time.sleep(0.1)
    print()


# ============================================================
# Etapes ouverture / fermeture
# ============================================================

def _open_step(lcd: LCD2004, relays: Relays, name: str, gpio: int) -> None:
    open_s = config.VALVE_OPEN_CAPACITOR_CHARGE_S
    _sep(f"OUVERTURE {name}  (GPIO {gpio})")
    print(f"  Relay ON -> ouverture mecanique + charge condensateur ({open_s:.0f}s)")
    print()
    print(f"  >>> Entree pour ouvrir {name}...", end="", flush=True)
    input()
    relays.open_valve(name)
    print(f"  Relay ON — ouverture + charge ({open_s:.0f}s)...")
    _countdown(lcd, name, "Relay ON  ouverture", open_s)
    print(f"  Vanne ouverte — condensateur charge")


def _close_step(lcd: LCD2004, relays: Relays, name: str, gpio: int) -> None:
    close_s = config.VALVE_CLOSE_TRAVEL_S
    _sep(f"FERMETURE {name}  (GPIO {gpio})")
    print(f"  Relay OFF -> course mecanique fermeture ({close_s:.0f}s)")
    print()
    print(f"  >>> Entree pour fermer {name}...", end="", flush=True)
    input()
    relays.close_valve(name)
    print(f"  Relay OFF — course fermeture ({close_s:.0f}s)...")
    _countdown(lcd, name, "Relay OFF fermeture", close_s)
    print(f"  Vanne en butee fermee")


# ============================================================
# Main
# ============================================================

def main() -> None:
    print("=" * 54)
    print("  TEST VANNES US SOLID — Clean & Protech V5")
    print("=" * 54)
    print()
    print(f"  {_V1[0]:<14}  GPIO {_V1[1]}")
    print(f"  {_V2[0]:<14}  GPIO {_V2[1]}")
    print()
    print(f"  Ouverture : VALVE_OPEN_CAPACITOR_CHARGE_S = {config.VALVE_OPEN_CAPACITOR_CHARGE_S:.0f}s")
    print(f"  Fermeture : VALVE_CLOSE_TRAVEL_S          = {config.VALVE_CLOSE_TRAVEL_S:.0f}s")
    print()
    print("  Sequence : ouv V1 -> ouv V2 -> ferm V1 -> ferm V2")
    print("  Ctrl+C pour quitter proprement\n")

    gpio_handle.init()

    with I2CBus() as bus:
        lcd = LCD2004(bus)
        lcd.init()
        lcd.clear()
        lcd.write_centered(1, "TEST VANNES US")
        lcd.write_centered(2, "Pret")

        relays = Relays()
        relays.open()

        try:
            _open_step(lcd,  relays, *_V1)
            _open_step(lcd,  relays, *_V2)
            _close_step(lcd, relays, *_V1)
            _close_step(lcd, relays, *_V2)

        except KeyboardInterrupt:
            print("\n\n  Arret (Ctrl+C)")

        finally:
            relays.close_all_valves()
            relays.close()
            lcd.clear()
            lcd.write_centered(1, "TEST VANNES US")
            lcd.write_centered(2, "Termine")
            lcd.write_centered(3, "Toutes fermees")

    gpio_handle.close()
    print("=== FIN TEST VANNES US SOLID ===")


if __name__ == "__main__":
    main()
