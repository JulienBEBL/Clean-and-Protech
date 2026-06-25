"""
test_vannes_aleatoire.py — Test simultane aleatoire des 4 vannes US Solid — V5.

Valide la capacite de l'alimentation a piloter plusieurs vannes simultanement.

A chaque cycle :
    1. Selection aleatoire d'une combinaison de vannes a ouvrir (0 a 4)
    2. Application simultanee (toutes les ouvertures/fermetures d'un coup)
    3. Attente CYCLE_WAIT_S secondes avec countdown LCD
    4. Nouveau tirage aleatoire

GPIO :
    GPIO  7 -> V1 POT_A_BOUE   (US Solid 24VDC NO)
    GPIO  8 -> V2 EGOUTS        (US Solid 24VDC NO)
    GPIO 25 -> V3 CUVE_TRAVAIL  (US Solid 24VDC NO)
    GPIO 24 -> V4 EAU_PROPRE    (US Solid 24VDC NO)

Ctrl+C ferme toutes les vannes et quitte proprement.
"""

from __future__ import annotations

import random
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

# ============================================================
# Constantes
# ============================================================

CYCLE_WAIT_S: float = 15.0  # duree entre chaque changement d'etat

_COLS = config.LCD_COLS

_ALL_VALVES: tuple[str, ...] = ("POT_A_BOUE", "EGOUTS", "CUVE_TRAVAIL", "EAU_PROPRE")

_SHORT: dict[str, str] = {
    "POT_A_BOUE":   "PAB",
    "EGOUTS":       "EGO",
    "CUVE_TRAVAIL": "CUV",
    "EAU_PROPRE":   "EAU",
}

_GPIO: dict[str, int] = {
    "POT_A_BOUE":   config.RELAY_POT_A_BOUE_GPIO,
    "EGOUTS":       config.RELAY_EGOUTS_GPIO,
    "CUVE_TRAVAIL": config.RELAY_CUVE_TRAVAIL_GPIO,
    "EAU_PROPRE":   config.RELAY_EAU_PROPRE_GPIO,
}


# ============================================================
# Helpers
# ============================================================

def _pad(s: str) -> str:
    return s[:_COLS].ljust(_COLS)


def _state_line(v1: str, v2: str, open_set: set[str]) -> str:
    s1 = f"{_SHORT[v1]}:{'ON ' if v1 in open_set else 'OFF'}"
    s2 = f"{_SHORT[v2]}:{'ON ' if v2 in open_set else 'OFF'}"
    return f"{s1}   {s2}"


def _apply_state(relays: Relays, open_set: set[str]) -> None:
    """Applique l'etat simultanement sur les 4 vannes."""
    for name in _ALL_VALVES:
        if name in open_set:
            relays.open_valve(name)
        else:
            relays.close_valve(name)


def _countdown(lcd: LCD2004, cycle: int, open_set: set[str], duration: float) -> None:
    n_open = len(open_set)
    t0 = time.monotonic()
    while True:
        elapsed   = time.monotonic() - t0
        remaining = max(0.0, duration - elapsed)
        lcd.write_centered(1, f"CYCLE {cycle:03d}  [{n_open}/4]")
        lcd.write(2, _pad(_state_line("POT_A_BOUE",   "EGOUTS",       open_set)))
        lcd.write(3, _pad(_state_line("CUVE_TRAVAIL", "EAU_PROPRE",   open_set)))
        lcd.write(4, _pad(f"Prochain dans {remaining:5.1f}s"))
        print(f"  Cycle {cycle:03d}  {remaining:5.1f}s\r", end="", flush=True)
        if elapsed >= duration:
            break
        time.sleep(0.1)
    print()


# ============================================================
# Main
# ============================================================

def main() -> None:
    print("=" * 54)
    print("  TEST VANNES ALEATOIRE SIMULTANE — Clean & Protech V5")
    print("=" * 54)
    print()
    print("  Vannes :")
    for name, gpio in _GPIO.items():
        print(f"    {_SHORT[name]}  {name:<14}  GPIO {gpio}")
    print()
    print(f"  Attente entre cycles : {CYCLE_WAIT_S:.0f}s")
    print("  Tirage aleatoire a chaque cycle (0 a 4 vannes ouvertes)")
    print("  Ouverture / fermeture SIMULTANEE (test alim)")
    print()
    print("  Ctrl+C pour quitter proprement")
    print()
    print("  >>> Entree pour demarrer...", end="", flush=True)
    input()

    gpio_handle.init()

    with I2CBus() as bus:
        lcd = LCD2004(bus)
        lcd.init()
        lcd.clear()
        lcd.write_centered(1, "TEST ALEATOIRE")
        lcd.write_centered(2, "SIMULTANE")
        lcd.write_centered(3, "Demarrage...")

        relays = Relays()
        relays.open()

        current_open: set[str] = set()
        cycle = 0

        try:
            while True:
                cycle += 1

                # Tirage aleatoire
                n_open    = random.randint(0, 4)
                new_open  = set(random.sample(_ALL_VALVES, n_open))

                # Calcul des changements
                to_open  = new_open - current_open
                to_close = current_open - new_open

                print(f"\n{'─' * 54}")
                print(f"  Cycle {cycle:03d}")
                if to_open:
                    print(f"  Ouverture : {' + '.join(_SHORT[v] for v in to_open)}")
                if to_close:
                    print(f"  Fermeture : {' + '.join(_SHORT[v] for v in to_close)}")
                if not to_open and not to_close:
                    print(f"  Etat inchange")

                open_str = " ".join(f"{_SHORT[v]}:ON " for v in _ALL_VALVES if v in new_open)
                off_str  = " ".join(f"{_SHORT[v]}:OFF" for v in _ALL_VALVES if v not in new_open)
                print(f"  Etat : {open_str}  {off_str}".strip())

                # Application simultanee
                _apply_state(relays, new_open)
                current_open = new_open

                # Countdown
                _countdown(lcd, cycle, current_open, CYCLE_WAIT_S)

        except KeyboardInterrupt:
            print("\n\n  Arret (Ctrl+C) — fermeture toutes vannes")

        finally:
            relays.close_all_valves()
            relays.close()
            lcd.clear()
            lcd.write_centered(1, "TEST ALEATOIRE")
            lcd.write_centered(2, f"Arret cycle {cycle}")
            lcd.write_centered(3, "Toutes fermees")

    gpio_handle.close()
    print(f"=== FIN TEST ALEATOIRE ({cycle} cycles) ===")


if __name__ == "__main__":
    main()
