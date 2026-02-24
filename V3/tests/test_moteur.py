from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = PROJECT_ROOT / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from i2c import I2CBus, IOBoard, LCD2004  # type: ignore
from moteur import MotorController, MotorConfig  # type: ignore


USE_LCD = True


def main() -> None:
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
            except Exception:
                lcd = None

        with MotorController(io, MotorConfig(step_high_us=200, step_low_us=200)) as mc:
            motor_id = 1
            steps = 200  # petit test

            print(f"Move M{motor_id} {steps} steps ouverture")
            if lcd:
                lcd.write(2, f"M{motor_id} +{steps} pas".ljust(20))
                lcd.write(3, "DIR=ouverture".ljust(20))

            mc.move_steps(motor_id, steps, "ouverture")
            time.sleep(0.5)

            print(f"Move M{motor_id} {steps} steps fermeture")
            if lcd:
                lcd.write(2, f"M{motor_id} -{steps} pas".ljust(20))
                lcd.write(3, "DIR=fermeture".ljust(20))

            mc.move_steps(motor_id, steps, "fermeture")

            print("Done.")
            if lcd:
                lcd.write(4, "Done".ljust(20))
                time.sleep(1.0)


if __name__ == "__main__":
    main()