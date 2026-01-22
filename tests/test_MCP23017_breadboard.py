#!/usr/bin/env python3
import time
import RPi.GPIO as GPIO
from smbus2 import SMBus

# --------- Réglages ---------
I2C_BUS = 1
MCP23017_ADDR = 0x20

# MCP23017 registers (BANK=0)
IODIRA = 0x00
GPPUA  = 0x0C
GPIOA  = 0x12

PIN_A7_MASK = 1 << 7

# Relais Raspberry Pi
RELAY_GPIO = 20   # BCM numbering

# --------- Init GPIO RPi ---------
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(RELAY_GPIO, GPIO.OUT)
GPIO.output(RELAY_GPIO, GPIO.LOW)  # relais OFF au démarrage

with SMBus(I2C_BUS) as bus:
    # A7 en entrée
    iodira = bus.read_byte_data(MCP23017_ADDR, IODIRA)
    iodira |= PIN_A7_MASK
    bus.write_byte_data(MCP23017_ADDR, IODIRA, iodira)

    # Pull-up interne sur A7 (optionnel)
    gppua = bus.read_byte_data(MCP23017_ADDR, GPPUA)
    gppua |= PIN_A7_MASK
    bus.write_byte_data(MCP23017_ADDR, GPPUA, gppua)

    print("Lecture A7 → commande relais GPIO20")

    try:
        while True:
            gpioa = bus.read_byte_data(MCP23017_ADDR, GPIOA)
            a7 = 1 if (gpioa & PIN_A7_MASK) else 0

            if a7:
                GPIO.output(RELAY_GPIO, GPIO.HIGH)
            else:
                GPIO.output(RELAY_GPIO, GPIO.LOW)

            time.sleep(0.02)  # 20 ms

    except KeyboardInterrupt:
        pass
    finally:
        GPIO.output(RELAY_GPIO, GPIO.LOW)
        GPIO.cleanup()
