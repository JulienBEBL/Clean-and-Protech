"""
Tests de base pour vérifier le câblage.

Ces fonctions sont appelées depuis main.py quand MODE_TEST est actif.
Tu peux en ajouter / modifier librement.
"""

import time
from typing import Dict

import RPi.GPIO as GPIO

from libs.i2c_devices import MCP23017, LCD20x4
from libs.motors import MotorManager


def test_i2c_scan(bus) -> None:
    print("=== Test I2C scan ===")
    found = []
    for addr in range(0x03, 0x78):
        try:
            bus.write_byte(addr, 0x00)
            found.append(addr)
        except OSError:
            continue
    if not found:
        print("Aucun périphérique I2C détecté.")
    else:
        print("Adresses I2C détectées :",
              ", ".join(f"0x{a:02X}" for a in found))
    time.sleep(1)


def test_program_leds_buttons(
    mcp1: MCP23017,
    buttons_bank: str,
    leds_bank: str,
    buttons_bits: list[int],
    leds_bits: list[int],
) -> None:
    print("=== Test LEDs + boutons programmes ===")
    print("Appuie sur les boutons, observe les bits et LEDs...")
    print("CTRL+C pour sortir.")

    try:
        while True:
            btn_val = mcp1.read_bank(buttons_bank)
            states = []
            for i, bit in enumerate(buttons_bits, start=1):
                pressed = 1 if (btn_val & (1 << bit)) == 0 else 0  # actif bas
                states.append(f"P{i}={pressed}")
                # LED = état bouton pour visualiser
                led_bit = leds_bits[i - 1]
                mcp1.write_bit(leds_bank, led_bit, 1 if pressed else 0)

            print("Boutons :", ", ".join(states), end="\r", flush=True)
            time.sleep(0.1)
    except KeyboardInterrupt:
        # Eteint les LEDs en sortie
        for bit in leds_bits:
            mcp1.write_bit(leds_bank, bit, 0)
        print("\nRetour au menu tests.")


def test_relays(relay_pins: Dict[str, int]) -> None:
    print("=== Test relais ===")
    for name, pin in relay_pins.items():
        print(f"  - Test relais {name} sur GPIO{pin}")
        GPIO.output(pin, GPIO.HIGH)
        time.sleep(1)
        GPIO.output(pin, GPIO.LOW)
        time.sleep(0.5)
    print("Relais testés.")


def test_buzzer(pin: int) -> None:
    print("=== Test buzzer ===")
    for _ in range(3):
        GPIO.output(pin, GPIO.HIGH)
        time.sleep(0.2)
        GPIO.output(pin, GPIO.LOW)
        time.sleep(0.1)
    print("Buzzer OK (si audible).")


def test_single_motor(motors: MotorManager, name: str, steps: int = 800) -> None:
    print(f"=== Test moteur {name} ===")
    print("Ouverture (DIR=1)...")
    motors.move_relative([name], steps, direction_open=True)
    time.sleep(0.5)
    print("Fermeture (DIR=0)...")
    motors.move_relative([name], steps, direction_open=False)
    print("Terminé.")


def test_dual_motors(motors: MotorManager, name1: str, name2: str, steps: int = 800) -> None:
    print(f"=== Test moteurs {name1} + {name2} synchrones ===")
    motors.move_relative([name1, name2], steps, direction_open=True)
    time.sleep(0.5)
    motors.move_relative([name1, name2], steps, direction_open=False)
    print("Terminé.")


def test_lcd(lcd: LCD20x4) -> None:
    print("=== Test LCD ===")
    lcd.clear()
    lcd.write_line(1, "Test LCD")
    lcd.write_line(2, "Ligne 2")
    lcd.write_line(3, "Ligne 3")
    lcd.write_line(4, "Ligne 4")
    time.sleep(3)
    lcd.clear()

