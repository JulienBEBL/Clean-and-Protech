#!/usr/bin/python3
# -*- coding: utf-8 -*-

import time
from smbus2 import SMBus

I2C_ADDR = 0x20   # adresse du MCP23017

# Registres Port A
IODIRA = 0x00     # direction I/O
GPPUA  = 0x0C     # pull-up interne
GPIOA  = 0x12     # registre lecture des pins

# Ouvrir bus I2C n°1
bus = SMBus(1)

# ------------------------------------------------------------
# CONFIGURATION MCP23017 (PORT A)
# ------------------------------------------------------------

# 1) Mettre GPA4 en entrée
# Lire l'état actuel du registre IODIRA (pour ne pas écraser A0..A7)
iodir_state = bus.read_byte_data(I2C_ADDR, IODIRA)
# Mettre le bit 4 à 1 => entrée
iodir_state |= (1 << 4)
bus.write_byte_data(I2C_ADDR, IODIRA, iodir_state)

# 2) Activer le pull-up interne sur GPA4
# Lire l'état actuel du registre GPPUA
gppu_state = bus.read_byte_data(I2C_ADDR, GPPUA)
# Mettre bit 4 à 1 => pull-up ON
gppu_state |= (1 << 4)
bus.write_byte_data(I2C_ADDR, GPPUA, gppu_state)

print("Lecture continue du bouton sur A4 (GPA4). CTRL+C pour arrêter.\n")

try:
    while True:
        raw = bus.read_byte_data(I2C_ADDR, GPIOA)
        value = (raw >> 4) & 1   # extraire le bit A4

        print(f"A4 = {value}")   # 1 = bouton relâché (pull-up), 0 = appuyé
        time.sleep(0.1)

except KeyboardInterrupt:
    pass

bus.close()
print("Fin du test.")
