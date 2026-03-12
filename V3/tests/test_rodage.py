"""
tests/test_rodage.py

Test "rodage" multi-moteurs:
- Utilise MotorController.move_steps_multi()
- Fait tourner un groupe de moteurs dans la même direction, même vitesse,
  sur N pas, puis retour.
- Affichage console + LCD.

Arborescence:
  /lib/moteur.py
  /lib/i2c.py
  /tests/test_rodage.py

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
# Paramètres rodage (à adapter)
# ----------------------------
USE_LCD = True

MOTORS = [
    "CUVE_TRAVAIL",
    "EAU_PROPRE",
    "POMPE",
    "DEPART",
    "RETOUR",
    "POT_A_BOUE",
    "EGOUTS",
]  # max 7


CYCLES = 20
PAUSE_S = 2


def _lcd_safe_write(lcd: LCD2004 | None, row: int, text: str) -> None:
    if lcd is None:
        return
    try:
        lcd.write(row, text.ljust(20)[:20])
    except Exception:
        pass


def main() -> None:
    print("=== TEST RODAGE (multi-moteurs) ===")
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
                _lcd_safe_write(lcd, 1, "TEST RODAGE")
                _lcd_safe_write(lcd, 2, f"{len(MOTORS)} moteurs")
            except Exception as e:
                print(f"LCD init failed (ignored): {e}")
                lcd = None

        with MotorController(io) as motors:
            motors.enable_all_drivers()
            time.sleep(0.2)

            try:
                for c in range(1, CYCLES + 1):
                    print(f"Cycle {c}/{CYCLES} -> fermeture")
                    _lcd_safe_write(lcd, 3, f"Cycle {c}/{CYCLES}")
                    _lcd_safe_write(lcd, 4, "FERMETURE")

                    print("EGOUTS")
                    motors.fermeture(motor_id="EGOUTS")
                    print("POT_A_BOUE")
                    motors.fermeture(motor_id="POT_A_BOUE")
                    print("POMPE")
                    motors.fermeture(motor_id="POMPE")
                    print("DEPART")
                    motors.fermeture(motor_id="DEPART")
                    print("RETOUR")
                    motors.fermeture(motor_id="RETOUR")
                    print("CUVE_TRAVAIL")
                    motors.fermeture(motor_id="CUVE_TRAVAIL")
                    print("EAU_PROPRE")
                    motors.fermeture(motor_id="EAU_PROPRE")

                    time.sleep(PAUSE_S)

                    print(f"Cycle {c}/{CYCLES} -> ouverture")
                    _lcd_safe_write(lcd, 4, "ouverture")

                    print("EGOUTS")
                    motors.ouverture(motor_id="EGOUTS")
                    print("POT_A_BOUE")
                    motors.ouverture(motor_id="POT_A_BOUE")
                    print("POMPE")
                    motors.ouverture(motor_id="POMPE")
                    print("DEPART")
                    motors.ouverture(motor_id="DEPART")
                    print("RETOUR")
                    motors.ouverture(motor_id="RETOUR")
                    print("CUVE_TRAVAIL")
                    motors.ouverture(motor_id="CUVE_TRAVAIL")
                    print("EAU_PROPRE")
                    motors.ouverture(motor_id="EAU_PROPRE")

                    time.sleep(PAUSE_S)

                print("\nRodage terminé.")
                _lcd_safe_write(lcd, 4, "Done")

            except KeyboardInterrupt:
                print("\nStopped by user.")
            finally:
                # sécurité
                try:
                    motors.disable_all_drivers()
                except Exception:
                    pass

                if lcd is not None:
                    try:
                        lcd.clear()
                        lcd.write(1, "Test stopped")
                    except Exception:
                        pass


if __name__ == "__main__":
    main()
