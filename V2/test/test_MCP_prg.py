#!/usr/bin/env python3
"""
Test MCP23017 @ 0x24 : relais LEDs sur GPA2..GPA7 (LED1..LED6)

- Test uniquement OUTPUT (pas d'inputs)
- Séquence: une LED à la fois, puis chenillard, puis tout ON/OFF
- Arrêt propre: remet toutes les sorties à OFF
"""

import time
import sys
import signal
from smbus2 import SMBus

I2C_BUS = 1
MCP_ADDR = 0x24

# Registres MCP23017 (bank=0 par défaut)
IODIRA = 0x00
IODIRB = 0x01
GPIOA  = 0x12
GPIOB  = 0x13
OLATA  = 0x14
OLATB  = 0x15

# Relais sur GPA2..GPA7 => bits 2..7
LED_PINS_A = [2, 3, 4, 5, 6, 7]  # LED1..LED6

# Inversion éventuelle (selon carte relais/transistor):
# False => 1 = ON, 0 = OFF
# True  => 0 = ON, 1 = OFF
ACTIVE_LOW = False


class MCP23017:
    def __init__(self, bus: SMBus, addr: int):
        self.bus = bus
        self.addr = addr

    def write_u8(self, reg: int, val: int) -> None:
        self.bus.write_byte_data(self.addr, reg, val & 0xFF)

    def read_u8(self, reg: int) -> int:
        return self.bus.read_byte_data(self.addr, reg) & 0xFF

    def set_bits_a(self, mask: int, value_bits: int) -> None:
        """Met à jour OLATA en ne modifiant que 'mask'."""
        cur = self.read_u8(OLATA)
        new = (cur & ~mask) | (value_bits & mask)
        self.write_u8(OLATA, new)

    def all_off(self) -> None:
        mask = sum(1 << p for p in LED_PINS_A)
        if ACTIVE_LOW:
            # OFF = 1
            self.set_bits_a(mask, mask)
        else:
            # OFF = 0
            self.set_bits_a(mask, 0)

    def led_on(self, idx: int) -> None:
        pin = LED_PINS_A[idx]
        mask = 1 << pin
        if ACTIVE_LOW:
            # ON = 0
            self.set_bits_a(mask, 0)
        else:
            # ON = 1
            self.set_bits_a(mask, mask)

    def led_off(self, idx: int) -> None:
        pin = LED_PINS_A[idx]
        mask = 1 << pin
        if ACTIVE_LOW:
            # OFF = 1
            self.set_bits_a(mask, mask)
        else:
            # OFF = 0
            self.set_bits_a(mask, 0)

    def all_on(self) -> None:
        mask = sum(1 << p for p in LED_PINS_A)
        if ACTIVE_LOW:
            # ON = 0
            self.set_bits_a(mask, 0)
        else:
            # ON = 1
            self.set_bits_a(mask, mask)


def main():
    with SMBus(I2C_BUS) as bus:
        mcp = MCP23017(bus, MCP_ADDR)

        # Met seulement GPA2..GPA7 en OUTPUT (0). Le reste inchangé.
        iodira = mcp.read_u8(IODIRA)
        out_mask = sum(1 << p for p in LED_PINS_A)  # bits 2..7
        iodira_new = iodira & ~out_mask
        mcp.write_u8(IODIRA, iodira_new)

        # Initialisation: tout OFF
        mcp.all_off()

        def cleanup(*_):
            try:
                mcp.all_off()
            finally:
                sys.exit(0)

        signal.signal(signal.SIGINT, cleanup)
        signal.signal(signal.SIGTERM, cleanup)

        print("MCP23017 test @0x24: relais LEDs sur GPA2..GPA7")
        print(f"ACTIVE_LOW={ACTIVE_LOW} (modifie si tes relais sont inversés)")
        print("Ctrl+C pour quitter.\n")

        # 1) Une LED à la fois
        print("Test 1: une LED à la fois...")
        for _ in range(2):
            for i in range(len(LED_PINS_A)):
                mcp.all_off()
                mcp.led_on(i)
                print(f"  LED{i+1} ON")
                time.sleep(0.5)
        mcp.all_off()

        # 2) Chenillard
        print("Test 2: chenillard...")
        for _ in range(3):
            for i in range(len(LED_PINS_A)):
                mcp.all_off()
                mcp.led_on(i)
                time.sleep(0.15)
        mcp.all_off()

        # 3) Tout ON / OFF
        print("Test 3: tout ON/OFF...")
        for _ in range(5):
            mcp.all_on()
            time.sleep(0.3)
            mcp.all_off()
            time.sleep(0.3)

        # Boucle continue (optionnelle) : blink global lent
        print("Boucle: blink global (Ctrl+C pour quitter)...")
        while True:
            mcp.all_on()
            time.sleep(1.0)
            mcp.all_off()
            time.sleep(1.0)


if __name__ == "__main__":
    main()
