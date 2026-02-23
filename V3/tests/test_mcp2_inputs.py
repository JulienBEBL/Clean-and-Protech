"""
tests/test_mcp2_inputs.py

Test manuel dédié MCP2 (0x25):
- Lecture des entrées VIC sur port B: B0..B4
- Lecture des entrées AIR sur port A: A7..A4
Affichage:
- Console (stdout)
- LCD 20x4 (0x27)

Arborescence:
  /lib/i2c.py
  /tests/test_mcp2_inputs.py

Exécution:
- Lance ce fichier depuis ton IDE/remote desktop (pas besoin de CLI).
Stop:
- Ctrl+C
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# ------------------------------------------------------------
# Import lib/i2c.py (sans installation)
# ------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = PROJECT_ROOT / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from i2c import I2CBus, MCP23017, LCD2004  # type: ignore


# ----------------------------
# Config test
# ----------------------------
BUS_ID = 1
FREQ_HZ = 100_000
RETRIES = 2
RETRY_DELAY_S = 0.01

MCP2_ADDR = 0x25  # A2=1, A1=0, A0=1 => 0b0100101 = 0x25 (attention: rappel)
LCD_ADDR = 0x27

LOOP_DELAY_S = 0.20


# ----------------------------
# Helpers mapping MCP2
# ----------------------------
def read_vic_bits(port_b: int) -> list[int]:
    # VIC1..VIC5 = B0..B4 (actif bas en général)
    return [1 if (port_b & (1 << i)) else 0 for i in range(0, 5)]


def read_air_bits(port_a: int) -> list[int]:
    # AIR1..AIR4 = A7..A4
    pins = [7, 6, 5, 4]
    return [1 if (port_a & (1 << p)) else 0 for p in pins]


def bits_to_str(bits: list[int]) -> str:
    return "".join(str(b) for b in bits)


def main() -> None:
    bus = I2CBus(bus_id=BUS_ID, freq_hz=FREQ_HZ, retries=RETRIES, retry_delay_s=RETRY_DELAY_S)

    with bus:
        # Init MCP2
        mcp2 = MCP23017(bus, MCP2_ADDR)
        mcp2.init(force=True)

        # Force directions: A input, B input
        mcp2.set_port_direction("A", 0xFF)
        mcp2.set_port_direction("B", 0xFF)

        # Pull-ups sur entrées (utile si câblé vers GND)
        mcp2.set_pullup("A", 0x00)  # pas de pull-up sur A (AIR) car câblé vers GND
        mcp2.set_pullup("B", 0x00)  # pas de pull-up sur B (VIC) car câblé vers GND

        # Init LCD (optionnel mais demandé)
        lcd = None
        try:
            lcd = LCD2004(bus, address=LCD_ADDR, cols=20, rows=4)
            lcd.init()
            lcd.clear()
            lcd.write(1, "MCP2 INPUTS TEST")
            lcd.write(2, f"ADDR=0x{MCP2_ADDR:02X}".ljust(20))
        except Exception as e:
            print(f"LCD init failed (ignored): {e}")
            lcd = None

        print("MCP2 INPUTS TEST")
        print(f"- MCP2 addr: 0x{MCP2_ADDR:02X}")
        print("- VIC: B0..B4  (VIC1..VIC5)")
        print("- AIR: A7..A4  (AIR1..AIR4)")
        print("Stop: Ctrl+C\n")

        try:
            while True:
                port_b = mcp2.read_port("B")
                port_a = mcp2.read_port("A")

                vic_raw = read_vic_bits(port_b)  # 1=HIGH, 0=LOW
                air_raw = read_air_bits(port_a)

                # Actif bas (câblé vers GND): actif = 1 si niveau == 0
                vic_active = [1 if b == 0 else 0 for b in vic_raw]
                air_active = [1 if b == 0 else 0 for b in air_raw]

                # Console
                print(
                    f"GPIOB=0x{port_b:02X} VIC raw={vic_raw} act={vic_active} | "
                    f"GPIOA=0x{port_a:02X} AIR raw={air_raw} act={air_active}"
                )

                # LCD (2 lignes utiles)
                if lcd is not None:
                    lcd.write(3, f"VIC:{bits_to_str(vic_active)}".ljust(20))
                    lcd.write(4, f"AIR:{bits_to_str(air_active)}".ljust(20))

                time.sleep(LOOP_DELAY_S)

        except KeyboardInterrupt:
            print("\nStopped by user.")
        finally:
            if lcd is not None:
                try:
                    lcd.clear()
                    lcd.write(1, "Test stopped")
                except Exception:
                    pass


if __name__ == "__main__":
    main()