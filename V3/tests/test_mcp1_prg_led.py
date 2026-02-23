"""
tests/test_mcp1_prg_led.py

Test manuel dédié MCP1 (0x24):
- Lecture des boutons PRG1..PRG6 sur port B (B0..B5) — actif bas (contact vers GND)
- Pilotage des LEDs LED1..LED6 sur port A (A2..A7) — actif haut
- Affichage double:
  - Console
  - LCD 20x4 (0x27)

Comportement:
- Si PRGx est appuyé (niveau 0), alors LEDx = ON.

Arborescence:
  /lib/i2c.py
  /tests/test_mcp1_prg_led.py

Stop: Ctrl+C
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
# Config
# ----------------------------
BUS_ID = 1
FREQ_HZ = 100_000
RETRIES = 2
RETRY_DELAY_S = 0.01

MCP1_ADDR = 0x24
LCD_ADDR = 0x27

# Tu as des pull-ups externes: pull-ups internes MCP OFF par défaut
ENABLE_INTERNAL_PULLUPS = False

LOOP_DELAY_S = 0.05  # 50 ms


# ----------------------------
# Mapping MCP1
# ----------------------------
# PRG1..PRG6 = B0..B5
PRG_PINS = [0, 1, 2, 3, 4, 5]

# LED1..LED6 = A2..A7
LED_PINS = [2, 3, 4, 5, 6, 7]


def read_prg_raw(gpio_b: int) -> list[int]:
    """Return raw levels for PRG1..PRG6 (1=HIGH, 0=LOW)."""
    return [1 if (gpio_b & (1 << p)) else 0 for p in PRG_PINS]


def prg_active_from_raw(raw: list[int]) -> list[int]:
    """Active-low semantic: 1 if pressed/active (raw==0)."""
    return [1 if v == 0 else 0 for v in raw]


def apply_leds_from_prg(mcp1: MCP23017, prg_active: list[int]) -> int:
    """
    Build OLAT(A) value for LEDs based on prg_active list.
    LEDx is ON when PRGx active.
    Returns value written to port A (full byte).
    """
    val_a = 0x00
    for idx, active in enumerate(prg_active):
        if active:
            val_a |= (1 << LED_PINS[idx])
    mcp1.write_port("A", val_a)
    return val_a


def bits_to_str(bits: list[int]) -> str:
    return "".join(str(b) for b in bits)


def main() -> None:
    bus = I2CBus(bus_id=BUS_ID, freq_hz=FREQ_HZ, retries=RETRIES, retry_delay_s=RETRY_DELAY_S)

    with bus:
        # Init MCP1
        mcp1 = MCP23017(bus, MCP1_ADDR)
        mcp1.init(force=True)

        # Directions: B=INPUT, A=OUTPUT
        mcp1.set_port_direction("B", 0xFF)
        mcp1.set_port_direction("A", 0x00)

        # Pull-ups sur entrées PRG (B0..B5)
        if ENABLE_INTERNAL_PULLUPS:
            mcp1.set_pullup("B", 0xFF)
        else:
            mcp1.set_pullup("B", 0x00)

        # Safe: LEDs off
        mcp1.write_port("A", 0x00)

        # LCD
        lcd = None
        try:
            lcd = LCD2004(bus, address=LCD_ADDR, cols=20, rows=4)
            lcd.init()
            lcd.clear()
            lcd.write(1, "MCP1 PRG->LED")
            lcd.write(2, f"MCP1=0x{MCP1_ADDR:02X}".ljust(20))
        except Exception as e:
            print(f"LCD init failed (ignored): {e}")
            lcd = None

        print("\nMCP1 TEST: PRG buttons -> LEDs")
        print("PRG1..PRG6 on B0..B5 (active low)")
        print("LED1..LED6 on A2..A7 (active high)")
        print("Stop: Ctrl+C\n")

        prev_b = None
        prev_a_written = None

        try:
            while True:
                gpio_b = mcp1.read_port("B")
                prg_raw = read_prg_raw(gpio_b)
                prg_active = prg_active_from_raw(prg_raw)

                a_written = apply_leds_from_prg(mcp1, prg_active)

                changed = (prev_b != gpio_b) or (prev_a_written != a_written)
                prev_b, prev_a_written = gpio_b, a_written

                mark = " *" if changed else ""
                print(
                    f"GPIOB=0x{gpio_b:02X} PRG raw={prg_raw} act={prg_active} | "
                    f"LEDA=0x{a_written:02X}{mark}"
                )

                if lcd is not None:
                    # Ligne 3: boutons (actifs)
                    lcd.write(3, f"PRG:{bits_to_str(prg_active)}".ljust(20))
                    # Ligne 4: LEDs (même pattern)
                    lcd.write(4, f"LED:{bits_to_str(prg_active)}".ljust(20))

                time.sleep(LOOP_DELAY_S)

        except KeyboardInterrupt:
            print("\nStopped by user.")
        finally:
            try:
                mcp1.write_port("A", 0x00)
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