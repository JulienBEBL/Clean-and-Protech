#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Test des sorties :
- LEDs de programmes sur MCP1.
- Relais (air / pump) sur GPIO.

Utilisation :
    python tests/test_mcp_outputs.py
"""

import time
from pathlib import Path

import RPi.GPIO as GPIO
import yaml  # type: ignore

from libs.i2c_devices import MCP23017, LCD20x4, SMBus


def main() -> None:
    # Charge la config sans dépendre de main.py
    config_path = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
    with config_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # GPIO pour relais
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)

    gpio_cfg = cfg["gpio"]
    relay_pins = {name: int(pin) for name, pin in gpio_cfg["relays"].items()}
    for pin in relay_pins.values():
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

    # MCP1 + LCD via I2C
    i2c_cfg = cfg["i2c"]
    bus = SMBus(int(i2c_cfg.get("bus", 1)))
    mcp1 = MCP23017(bus, int(i2c_cfg["mcp1"]), name="MCP1_programs")
    lcd = LCD20x4(bus, int(i2c_cfg["lcd"]), width=20)

    m1_cfg = cfg["mcp23017"]["mcp1_programs"]
    leds_bank = m1_cfg["leds_bank"]
    leds_bits = m1_cfg["leds_bits"]

    lcd.clear()
    lcd.write_line(1, "Test sorties")
    lcd.write_line(2, "Relais + LEDs")
    lcd.write_line(3, "CTRL+C pr stop")
    lcd.write_line(4, "")

    print("=== Test sorties MCP / relais ===")
    print("CTRL+C pour quitter.")

    try:
        while True:
            # Séquence LEDs : chenillard
            for idx, bit in enumerate(leds_bits):
                # Eteint tout
                for b in leds_bits:
                    mcp1.write_bit(leds_bank, b, 0)
                # Allume une LED
                mcp1.write_bit(leds_bank, bit, 1)
                print(f"LED PRG index {idx} (bit {bit}) ON   ", end="\r", flush=True)
                time.sleep(0.2)

            # Test relais : air puis pump
            for name, pin in relay_pins.items():
                print(f"Relais {name} ON (GPIO{pin})    ", end="\r", flush=True)
                GPIO.output(pin, GPIO.HIGH)
                time.sleep(0.5)
                GPIO.output(pin, GPIO.LOW)
                time.sleep(0.2)

    except KeyboardInterrupt:
        print("\nArrêt du test sorties.")
        # Tout éteindre
        for b in leds_bits:
            mcp1.write_bit(leds_bank, b, 0)
        for pin in relay_pins.values():
            GPIO.output(pin, GPIO.LOW)

        lcd.clear()
        lcd.write_line(1, "Test sorties")
        lcd.write_line(2, "STOP")
        time.sleep(1)


if __name__ == "__main__":
    main()

