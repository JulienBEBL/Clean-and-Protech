"""
test_moteur.py — Test ouverture / fermeture d'un moteur (rampe)

Exécute une ouverture complète puis une fermeture complète
sur le moteur choisi via motors.ouverture() et motors.fermeture().
Les paramètres de rampe et de course viennent de config.py.

Modifier MOTOR_NAME pour tester un autre moteur.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import libs.gpio_handle as gpio_handle
from libs.i2c_bus import I2CBus
from libs.io_board import IOBoard
from libs.lcd2004 import LCD2004
from libs.moteur import MotorController

# ── Paramètre à modifier ──────────────────────────────────────────────────────
MOTOR_NAME = "CUVE_TRAVAIL"
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    print(f"=== TEST MOTEUR — {MOTOR_NAME} ===")
    print("Ouverture puis fermeture avec rampe (config.py)")
    print("Ctrl+C pour arrêter\n")

    gpio_handle.init()

    with I2CBus() as bus:
        io = IOBoard(bus)
        io.init()

        lcd = LCD2004(bus)
        lcd.init()
        lcd.clear()
        lcd.write_centered(1, "TEST MOTEUR")
        lcd.write_centered(2, MOTOR_NAME)

        with MotorController(io) as motors:

            # --- OUVERTURE ---
            print("OUVERTURE...")
            lcd.write(3, "OUVERTURE...        ")
            lcd.write(4, "                    ")
            t0 = time.monotonic()

            motors.ouverture(MOTOR_NAME)

            dt = time.monotonic() - t0
            print(f"Ouverture terminée en {dt:.2f}s")
            lcd.write(3, "Ouverture OK        ")
            lcd.write(4, f"t = {dt:.2f}s          ")
            time.sleep(2.0)



            # --- FERMETURE ---
            print("FERMETURE...")
            lcd.write(3, "FERMETURE...        ")
            lcd.write(4, "                    ")
            t0 = time.monotonic()

            motors.fermeture(MOTOR_NAME)

            dt = time.monotonic() - t0
            print(f"Fermeture terminée en {dt:.2f}s")
            lcd.write(3, "Fermeture OK        ")
            lcd.write(4, f"t = {dt:.2f}s          ")
            time.sleep(2.0)

        lcd.clear()
        lcd.write_centered(1, "Test termine")
        lcd.write_centered(2, MOTOR_NAME)

    gpio_handle.close()
    print("\n=== FIN TEST ===")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nArrêté par l'utilisateur.")
        gpio_handle.close()
