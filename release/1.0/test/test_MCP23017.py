#!/usr/bin/python3
# -*- coding: utf-8 -*-

import time
from smbus2 import SMBus

I2C_ADDR = 0x20   # adresse par défaut du MCP23017
IODIRA = 0x00     # registre direction port A
IODIRB = 0x01     # registre direction port B
GPIOA  = 0x12     # registre données sortie/input port A
GPIOB  = 0x13     # registre données sortie/input port B

# Ouvrir bus I2C
bus = SMBus(1)

# ------------------------------------------------------------
# CONFIG MCP23017
# ------------------------------------------------------------
# Mettre tout le PORT A en sortie (0 = output)
bus.write_byte_data(I2C_ADDR, IODIRA, 0x00)

# On lit l'état actuel du port A pour ne pas écraser les autres pins
current_state = bus.read_byte_data(I2C_ADDR, GPIOA)

print("Test LED MCP23017 (A0) démarré. CTRL+C pour quitter.\n")

try:
    state = False

    while True:
        if state:
            print("LED ON (A0)")
            new_state = current_state | 0b00000001   # bit 0 = 1
        else:
            print("LED OFF (A0)")
            new_state = current_state & 0b11111110   # bit 0 = 0

        bus.write_byte_data(I2C_ADDR, GPIOA, new_state)

        state = not state
        time.sleep(1)

except KeyboardInterrupt:
    pass

print("Test MCP terminé.")
bus.close()
