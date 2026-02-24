"""
tests/test_moteur.py

Test MotorController V2:
- move_steps()
- move_steps_ramp()
- enable_all_drivers()
- disable_all_drivers()

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
STEPS_SMALL = 1000        # petit déplacement test
STEPS_RAMP = 16000         # déplacement avec rampe

SPEED_CONST = 400         # pas/s (constant speed)
SPEED_CRUISE = 800       # pas/s (vitesse de croisière)

ACCEL_SPEED = 70          # pas/s (vitesse départ)
DECEL_SPEED = 150         # pas/s (vitesse arrivée)

USE_LCD = True


def main() -> None:

    print("=== TEST MOTEUR V2 ===")
    print(f"Moteur: {MOTOR_NAME}")
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
                lcd.write(1, "TEST MOTEUR V2")
                lcd.write(2, MOTOR_NAME.ljust(20))
            except Exception as e:
                print(f"LCD init failed (ignored): {e}")
                lcd = None

        with MotorController(io) as motors:

            # ---------------------------
            # Enable all drivers
            # ---------------------------
            print("Enable all drivers")
            motors.enable_all_drivers()
            time.sleep(0.5)

            # ==========================================================
            # 1) Test vitesse constante
            # ==========================================================
            print("\n--- TEST CONSTANT SPEED ---")
            print(f"Move {STEPS_SMALL} steps @ {SPEED_CONST} sps")

            if lcd:
                lcd.write(3, "CONST SPEED".ljust(20))
                lcd.write(4, f"{SPEED_CONST} sps".ljust(20))

            motors.move_steps(
                motor_name=MOTOR_NAME,
                steps=STEPS_SMALL,
                direction="ouverture",
                speed_sps=SPEED_CONST,
            )

            time.sleep(1.0)

            motors.move_steps(
                motor_name=MOTOR_NAME,
                steps=STEPS_SMALL,
                direction="fermeture",
                speed_sps=SPEED_CONST,
            )

            time.sleep(1.0)

            # ==========================================================
            # 2) Test rampe accel/decel
            # ==========================================================
            print("\n--- TEST RAMP ---")
            print(f"Move {STEPS_RAMP} steps with ramp")
            print(f"Accel={ACCEL_SPEED} -> Cruise={SPEED_CRUISE} -> Decel={DECEL_SPEED}")

            if lcd:
                lcd.write(3, "RAMP MODE".ljust(20))
                lcd.write(4, f"{SPEED_CRUISE} sps".ljust(20))

            motors.move_steps_ramp(
                motor_name=MOTOR_NAME,
                steps=STEPS_RAMP,
                direction="ouverture",
                speed_sps=SPEED_CRUISE,
                accel=ACCEL_SPEED,
                decel=DECEL_SPEED,
            )

            time.sleep(1.0)

            motors.move_steps_ramp(
                motor_name=MOTOR_NAME,
                steps=STEPS_RAMP,
                direction="fermeture",
                speed_sps=SPEED_CRUISE,
                accel=ACCEL_SPEED,
                decel=DECEL_SPEED,
            )

            time.sleep(0.5)

            # ---------------------------
            # Disable all drivers
            # ---------------------------
            print("\nDisable all drivers")
            motors.disable_all_drivers()

            if lcd:
                lcd.write(3, "Drivers OFF".ljust(20))
                lcd.write(4, "Done".ljust(20))
                time.sleep(1.0)

    print("\n=== FIN TEST ===")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped by user.")