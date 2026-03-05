"""
tests/test_moteur_multi_ouverture_fermeture.py

Test:
- MotorController.ouverture()
- MotorController.fermeture()
- MotorController.move_steps_multi() (avec et sans ramp)

Affichage console + LCD (si dispo).
Stop: Ctrl+C

Arborescence:
  /lib/moteur.py
  /lib/i2c.py
  /tests/test_moteur_multi_ouverture_fermeture.py
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
USE_LCD = True

# Test 1: ouverture/fermeture sur 1 moteur (FULL_TRAVEL_STEPS)
ONE_MOTOR = "EAU_PROPRE"
OPEN_SPEED = 9800
OPEN_ACCEL = 4000
OPEN_DECEL = 9800

CLOSE_SPEED = 9800
CLOSE_ACCEL = 4500
CLOSE_DECEL = 9800

# Test 2: multi moteurs
MULTI_MOTORS = ["DEPART", "RETOUR", "EGOUTS"]  # max 7
MULTI_STEPS = 6000
MULTI_SPEED = 1200

# Test 3: multi moteurs + ramp
MULTI_RAMP_STEPS = 12000
MULTI_RAMP_SPEED = 2500
MULTI_RAMP_ACCEL = 400
MULTI_RAMP_DECEL = 900


def _lcd_write(lcd: LCD2004 | None, row: int, text: str) -> None:
    if lcd is None:
        return
    try:
        lcd.write(row, text.ljust(20)[:20])
    except Exception:
        pass


def main() -> None:
    print("=== TEST ouverture/fermeture + move_steps_multi ===")
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
                _lcd_write(lcd, 1, "TEST MOTEURS")
            except Exception as e:
                print(f"LCD init failed (ignored): {e}")
                lcd = None

        with MotorController(io) as motors:
            motors.enable_all_drivers()
            time.sleep(0.3)

            try:
                # ------------------------------------------------------------
                # 1) Ouverture complète (1 moteur)
                # ------------------------------------------------------------
                print(f"[1] OUVERTURE {ONE_MOTOR}")
                _lcd_write(lcd, 2, f"OUV {ONE_MOTOR}")
                _lcd_write(lcd, 3, f"V={OPEN_SPEED}")
                _lcd_write(lcd, 4, f"A={OPEN_ACCEL} D={OPEN_DECEL}")

                motors.ouverture(
                    motor_name=ONE_MOTOR,
                    speed_sps=OPEN_SPEED,
                    accel=OPEN_ACCEL,
                    decel=OPEN_DECEL,
                )

                time.sleep(0.8)

                # ------------------------------------------------------------
                # 2) Fermeture complète (1 moteur)
                # ------------------------------------------------------------
                print(f"[2] FERMETURE {ONE_MOTOR}")
                _lcd_write(lcd, 2, f"FER {ONE_MOTOR}")
                _lcd_write(lcd, 3, f"V={CLOSE_SPEED}")
                _lcd_write(lcd, 4, f"A={CLOSE_ACCEL} D={CLOSE_DECEL}")

                motors.fermeture(
                    motor_name=ONE_MOTOR,
                    speed_sps=CLOSE_SPEED,
                    accel=CLOSE_ACCEL,
                    decel=CLOSE_DECEL,
                )

                time.sleep(0.8)

                # ------------------------------------------------------------
                # 3) Multi moteurs (vitesse constante)
                # ------------------------------------------------------------
                print(f"[3] MULTI CONST {MULTI_MOTORS} steps={MULTI_STEPS} v={MULTI_SPEED}")
                _lcd_write(lcd, 2, "MULTI CONST")
                _lcd_write(lcd, 3, f"{len(MULTI_MOTORS)} mot v={MULTI_SPEED}")
                _lcd_write(lcd, 4, f"steps={MULTI_STEPS}")

                motors.move_steps_multi(
                    motor_names=MULTI_MOTORS,
                    steps=MULTI_STEPS,
                    direction="ouverture",
                    speed_sps=MULTI_SPEED,
                )

                time.sleep(0.6)

                motors.move_steps_multi(
                    motor_names=MULTI_MOTORS,
                    steps=MULTI_STEPS,
                    direction="fermeture",
                    speed_sps=MULTI_SPEED,
                )

                time.sleep(0.8)

                # ------------------------------------------------------------
                # 4) Multi moteurs (avec ramp)
                # ------------------------------------------------------------
                print(
                    f"[4] MULTI RAMP {MULTI_MOTORS} steps={MULTI_RAMP_STEPS} "
                    f"v={MULTI_RAMP_SPEED} a={MULTI_RAMP_ACCEL} d={MULTI_RAMP_DECEL}"
                )
                _lcd_write(lcd, 2, "MULTI RAMP")
                _lcd_write(lcd, 3, f"v={MULTI_RAMP_SPEED}")
                _lcd_write(lcd, 4, f"a={MULTI_RAMP_ACCEL} d={MULTI_RAMP_DECEL}")

                motors.move_steps_multi(
                    motor_names=MULTI_MOTORS,
                    steps=MULTI_RAMP_STEPS,
                    direction="ouverture",
                    speed_sps=MULTI_RAMP_SPEED,
                    accel=MULTI_RAMP_ACCEL,
                    decel=MULTI_RAMP_DECEL,
                )

                time.sleep(0.6)

                motors.move_steps_multi(
                    motor_names=MULTI_MOTORS,
                    steps=MULTI_RAMP_STEPS,
                    direction="fermeture",
                    speed_sps=MULTI_RAMP_SPEED,
                    accel=MULTI_RAMP_ACCEL,
                    decel=MULTI_RAMP_DECEL,
                )

                time.sleep(0.5)

                print("Done.")
                _lcd_write(lcd, 2, "DONE")
                _lcd_write(lcd, 3, "")
                _lcd_write(lcd, 4, "")
                time.sleep(1.0)

            except KeyboardInterrupt:
                print("\nStopped by user.")
            finally:
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