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

USE_LCD = True


def main() -> None:

    print("=== TEST MOTEUR V2 ===")
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

            if lcd:
                lcd.write(3, "CONST SPEED".ljust(20))
			
            # motors.move_steps(motor_name="POT_A_BOUE",steps=32000,direction="ouverture",speed_sps=400,)
            # print("\n POT A BOUE")
            # motors.move_steps(motor_name="POT_A_BOUE",steps=10000,direction="ouverture",speed_sps=400,)
            # print("\n EGOUTS")
            # motors.move_steps(motor_name="EGOUTS",steps=10000,direction="ouverture",speed_sps=400,)
            # print("\n VIC")
            # motors.move_steps(motor_name="VIC",steps=10000,direction="ouverture",speed_sps=400,)
            # print("\n RETOUR")
            # motors.move_steps(motor_name="RETOUR",steps=10000,direction="ouverture",speed_sps=400,)
            # print("\n POMPE")
            # motors.move_steps(motor_name="POMPE",steps=10000,direction="ouverture",speed_sps=400,)
            # print("\n DEPART")
            # motors.move_steps(motor_name="DEPART",steps=10000,direction="ouverture",speed_sps=400,)
            # print("\n CUVE_TRAVAIL")
            # motors.move_steps(motor_name="CUVE_TRAVAIL",steps=10000,direction="ouverture",speed_sps=400,)
            # print("\n EAU_PROPRE")
            # motors.move_steps(motor_name="CUVE_TRAVAIL",steps=32000,direction="ouverture",speed_sps=2500,)
            print("\n EAU_PROPRE RAMP")
            motors.move_steps_ramp(motor_name="CUVE_TRAVAIL",steps=32000,direction="ouverture",speed_sps=2000,accel=200, decel=400)
            
            
            
# MOTOR_NAME_TO_ID: Dict[str, int] = {
# "CUVE_TRAVAIL": 4,
# "EAU_PROPRE": 8,
# "POMPE": 2,
# "DEPART": 7,
# "RETOUR": 3,
# "POT_A_BOUE": 1,
# "EGOUTS": 5,
# "VIC": 6,
# }

            time.sleep(1.0)

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
