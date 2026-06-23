"""
test_homing.py — Test de la séquence de homing VIC V5.

Exécute la séquence de homing complète :
    DEPART → RETOUR → DEPART → RETOUR → DEPART → RETOUR → NEUTRE
    (VIC_HOMING_CYCLES = 3 cycles, overcourse +10%)

Affiche le temps total et la position finale (doit être NEUTRE = 50 pas).
Ctrl+C pour arrêter proprement à n'importe quel moment.
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
from libs.io_board import IOBoard
from libs.lcd2004 import LCD2004
from libs.vic import VICController


def main() -> None:
    overcourse = int(config.VIC_TOTAL_STEPS * config.MOTOR_HOMING_FIRST_CLOSE_FACTOR)
    n = config.VIC_HOMING_CYCLES

    print("=" * 54)
    print("  TEST HOMING VIC V5")
    print("=" * 54)
    print(f"  Cycles        : {n}")
    print(f"  Overcourse    : {overcourse} pas ({config.MOTOR_HOMING_FIRST_CLOSE_FACTOR:.0%})")
    print(f"  Vitesse VIC   : {config.VIC_SPEED_SPS} sps")
    print(f"  Position finale attendue : NEUTRE = {config.VIC_NEUTRE_STEPS} pas")
    print("  Ctrl+C pour arrêter\n")

    gpio_handle.init()

    with I2CBus() as bus:
        io = IOBoard(bus)
        io.init()

        lcd = LCD2004(bus)
        lcd.init()
        lcd.clear()
        lcd.write_centered(1, "TEST HOMING VIC")
        lcd.write_centered(2, f"{n} cycles")
        lcd.write_centered(3, "Démarrage...")
        time.sleep(1.0)

        vic = VICController()
        vic.open()

        try:
            lcd.clear()
            lcd.write_centered(1, "HOMING VIC")
            lcd.write_centered(2, "En cours...")

            print("  Homing en cours...")
            t0 = time.monotonic()
            vic.homing()
            dt = time.monotonic() - t0

            pos = vic.position
            ok  = pos == config.VIC_NEUTRE_STEPS

            print(f"  Homing terminé en {dt:.1f}s")
            print(f"  Position finale : {pos} pas (attendu : {config.VIC_NEUTRE_STEPS})")
            print(f"  Résultat : {'OK' if ok else 'ERREUR'}")

            lcd.clear()
            lcd.write_centered(1, "HOMING TERMINE")
            lcd.write_centered(2, f"{dt:.1f}s")
            lcd.write_centered(3, f"pos={pos} pas")
            lcd.write_centered(4, "OK" if ok else "ERREUR pos")

        except KeyboardInterrupt:
            print("\n  Arrêté par l'utilisateur.")
            lcd.clear()
            lcd.write_centered(1, "Arret utilisateur")
        finally:
            vic.disable()
            vic.close()

    gpio_handle.close()
    print("=== FIN TEST ===")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  Arrêté par l'utilisateur.")
        gpio_handle.close()
