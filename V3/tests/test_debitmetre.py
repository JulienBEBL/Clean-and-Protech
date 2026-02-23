from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = PROJECT_ROOT / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from debitmetre import FlowMeter, FlowMeterConfig  # type: ignore
from i2c import I2CBus, LCD2004  # type: ignore


K_PULSES_PER_LITER = 450.0
WINDOW_S = 1.0
LOOP_S = 0.25

LCD_ADDR = 0x27
USE_LCD = True


def main() -> None:
    bus = I2CBus(bus_id=1, freq_hz=100000, retries=2, retry_delay_s=0.01)

    fm = FlowMeter(
        FlowMeterConfig(
            gpiochip_index=0,
            gpio=21,
            pulses_per_liter=K_PULSES_PER_LITER,
            edge=__import__("lgpio").FALLING_EDGE,
            filter_us=1000,           # mets 0 pour désactiver si besoin
            window_s_default=WINDOW_S,
        )
    )

    with bus:
        lcd = None
        if USE_LCD:
            try:
                lcd = LCD2004(bus, address=LCD_ADDR, cols=20, rows=4)
                lcd.init()
                lcd.clear()
                lcd.write(1, "Debitmetre TEST")
                lcd.write(2, f"K={K_PULSES_PER_LITER:g} p/L".ljust(20))
            except Exception as e:
                print(f"LCD init failed (ignored): {e}")
                lcd = None

        fm.open()

        print("Debitmetre TEST (Ctrl+C)")
        t0 = time.monotonic()

        try:
            while True:
                flow = fm.flow_lpm(WINDOW_S)
                total = fm.total_liters()
                pulses = fm.total_pulses()
                dt = time.monotonic() - t0

                print(f"t={dt:6.1f}s | flow={flow:7.2f} L/min | total={total:8.3f} L | pulses={pulses}")

                if lcd is not None:
                    lcd.write(3, f"Q={flow:6.1f} L/min".ljust(20))
                    lcd.write(4, f"V={total:7.3f} L".ljust(20))

                time.sleep(LOOP_S)

        except KeyboardInterrupt:
            print("\nStopped by user.")
        finally:
            fm.close()
            if lcd is not None:
                try:
                    lcd.clear()
                    lcd.write(1, "Test stopped")
                except Exception:
                    pass


if __name__ == "__main__":
    main()