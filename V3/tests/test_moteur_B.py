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
                lcd.write(1, "PROGRAMME MOTEUR".ljust(20))
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
                lcd.write(3, "TEST RAMP MULTIMOTOR".ljust(20))
			
            # motors.move_steps(motor_name="POT_A_BOUE",steps=32000,direction="ouverture",speed_sps=3200)
            # print("\n POT A BOUE")
            # motors.move_steps(motor_name="EAU_PROPRE",steps=32000,direction="ouverture",speed_sps=3200)
            # print("\n EGOUTS")
            # motors.move_steps(motor_name="EGOUTS",steps=10000,direction="ouverture",speed_sps=3200)
            # print("\n VIC")
            # motors.move_steps(motor_name="VIC",steps=10000,direction="ouverture",speed_sps=3200)
            # print("\n RETOUR")
            # motors.move_steps(motor_name="RETOUR",steps=10000,direction="ouverture",speed_sps=3200)
            # print("\n POMPE")
            # motors.move_steps(motor_name="POMPE",steps=10000,direction="ouverture",speed_sps=3200)
            # print("\n DEPART")
            # motors.move_steps(motor_name="DEPART",steps=10000,direction="ouverture",speed_sps=3200)
            # print("\n CUVE_TRAVAIL")
            # motors.move_steps(motor_name="CUVE_TRAVAIL",steps=10000,direction="ouverture",speed_sps=3200)
            # print("\n EAU_PROPRE")
            # motors.move_steps(motor_name="CUVE_TRAVAIL",steps=32000,direction="ouverture",speed_sps=3200)
            
            
            # print("\n RAMP HYPER IMPORTANT SETTINGS A GARDER")
            # EAU_PROPRE, CUVE_TRAVAIL, DEPART, RETOUR, EGOUTS, POT_A_BOUE => OK avec rampe


            #MOTEUR_NAME_TEST="POMPE"
            # print(MOTEUR_NAME_TEST)
            # print("fermeture")
            # motors.move_steps_ramp(motor_name=MOTEUR_NAME_TEST,steps=32000,direction="fermeture", speed_sps=9800, accel=4500, decel=9800)
            # print("ouverture")
            # motors.move_steps_ramp(motor_name=MOTEUR_NAME_TEST,steps=30000,direction="ouverture", speed_sps=9800, accel=4000, decel=9800)
            # print("fermeture")
            # motors.move_steps_ramp(motor_name=MOTEUR_NAME_TEST,steps=32000,direction="fermeture", speed_sps=9800, accel=4500, decel=9800)
            # print("ouverture")
            # motors.move_steps_ramp(motor_name=MOTEUR_NAME_TEST,steps=30000,direction="ouverture", speed_sps=9800, accel=4000, decel=9800)
            # print("fermeture")
            # motors.move_steps_ramp(motor_name=MOTEUR_NAME_TEST,steps=32000,direction="fermeture", speed_sps=9800, accel=4500, decel=9800)
            # print("ouverture")
            # motors.move_steps_ramp(motor_name=MOTEUR_NAME_TEST,steps=30000,direction="ouverture", speed_sps=9800, accel=4000, decel=9800)
            
            # print("== GO LANCEMENT TEST ==")
            # NOM_TEST="TEST SANS RADIATEUR AVEC BYPASS, CYCLE FERME, CUVE A CUVE"
            # print(NOM_TEST)
            # MOTEUR_NAME_TEST="EGOUTS"
            # print("fermeture")
            # motors.move_steps_ramp(motor_name=MOTEUR_NAME_TEST,steps=32000,direction="fermeture", speed_sps=9800, accel=4500, decel=9800)
            # print("ouverture")
            # motors.move_steps_ramp(motor_name=MOTEUR_NAME_TEST,steps=30000,direction="ouverture", speed_sps=9800, accel=4000, decel=9800)

            #print("\n manuel \n")
            
            #motors.move_steps_ramp(motor_name="VIC", steps=950, direction="ouverture", speed_sps=800, accel=500, decel=600)
            #time.sleep(20)
            
            #MOTOR_N="CUVE_TRAVAIL"
            #print("fermeture")
            #motors.fermeture(MOTOR_N)
            #print("ouverture")
            #motors.ouverture(MOTOR_N)
            #motors.move_steps_ramp(motor_name="VIC", steps=400, direction="fermeture", speed_sps=800, accel=500, decel=600)
            #motors.move_steps_ramp(motor_name=MOTOR_N,steps=32000,direction="fermeture", speed_sps=9800, accel=4000, decel=9000)
            #motors.move_steps_ramp(motor_name=MOTOR_N,steps=30000,direction="ouverture", speed_sps=9800, accel=3200, decel=9800)
            #print("OK")
            #time.sleep(1000000)
            
            print("POSITIONNEMENT PROGRAMME")
            time.sleep(1)
            print("EGOUTS")
            motors.fermeture(motor_name="EGOUTS")
            #motors.ouverture(motor_name="EGOUTS")
            print("POT_A_BOUE")
            motors.fermeture(motor_name="POT_A_BOUE")
            motors.ouverture(motor_name="POT_A_BOUE")
            
            print("DEPART")
            motors.fermeture(motor_name="DEPART")
            motors.ouverture(motor_name="DEPART")
            print("POMPE")
            motors.fermeture(motor_name="POMPE")
            motors.ouverture(motor_name="POMPE")
            print("RETOUR")
            motors.fermeture(motor_name="RETOUR")
            motors.ouverture(motor_name="RETOUR")
            
            print("CUVE_TRAVAIL")
            motors.fermeture(motor_name="CUVE_TRAVAIL")
            motors.ouverture(motor_name="CUVE_TRAVAIL")
            print("EAU_PROPRE")
            motors.fermeture(motor_name="EAU_PROPRE")
            #motors.ouverture(motor_name="EAU_PROPRE")
            
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
