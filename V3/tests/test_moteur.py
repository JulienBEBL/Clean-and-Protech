"""
tests/test_moteur.py

Test manuel MotorController.
- Déplacement d'un moteur par nom
- Vitesse paramétrable
- Affichage console + LCD

Stop: Ctrl+C
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# ------------------------------------------------------------
# Import /lib
# ------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = PROJECT_ROOT / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from i2c import I2CBus, IOBoard, LCD2004  # type: ignore
from moteur import MotorController  # type: ignore


# ----------------------------
# Paramètres test
# ----------------------------
MOTOR_NAME = "VIC"        # à modifier si besoin
STEPS = 3200*5               # petit déplacement test
SPEED_SPS = 600           # pas/seconde
USE_LCD = True


def main() -> None:
    print("=== TEST MOTEUR ===")
    print(f"Moteur: {MOTOR_NAME}")
    print(f"Steps : {STEPS}")
    print(f"Speed : {SPEED_SPS} steps/s")
    print("Ctrl+C pour arrêter\n")

    bus = I2CBus(bus_id=1, freq_hz=100000, retries=2, retry_delay_s=0.01)

    with bus:
        io = IOBoard(bus)
        io.init(force=True)

        lcd = None
        if USE_LCD:
            try:
                lcd = LCD2004(bus, address=0x27, cols=20, rows=4)
                lcd.init()
                lcd.clear()
                lcd.write(1, "TEST MOTEUR")
                lcd.write(2, MOTOR_NAME.ljust(20))
            except Exception as e:
                print(f"LCD init failed (ignored): {e}")
                lcd = None

        with MotorController(io) as motors:

            # Activer tous les drivers
            print("Enable all drivers")
            motors.enable_all_drivers()
            time.sleep(0.5)

            # ----------- OUVERTURE -----------
            print("Move ouverture")
            if lcd:
                lcd.write(3, "OUVERTURE".ljust(20))

            motors.move_steps(
                motor_name=MOTOR_NAME,
                steps=STEPS,
                direction="ouverture",
                speed_sps=SPEED_SPS,
            )

            time.sleep(1.0)

            # ----------- FERMETURE -----------
            print("Move fermeture")
            if lcd:
                lcd.write(3, "FERMETURE".ljust(20))

            motors.move_steps(
                motor_name=MOTOR_NAME,
                steps=STEPS,
                direction="fermeture",
                speed_sps=SPEED_SPS,
            )

            time.sleep(0.5)

            # Désactiver tous les drivers
            print("Disable all drivers")
            motors.disable_all_drivers()

            if lcd:
                lcd.write(4, "Done".ljust(20))
                time.sleep(1.0)

    print("=== FIN TEST ===")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped by user.")