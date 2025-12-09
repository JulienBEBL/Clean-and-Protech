#!/usr/bin/env python3
import smbus2
from time import sleep

I2C_ADDR = 0x20  # adresse par défaut si A0, A1, A2 à GND
bus = smbus2.SMBus(1)

# registres pour les ports A et B
IODIRA = 0x00
IODIRB = 0x01
GPIOA  = 0x12
GPIOB  = 0x13

# configurer GPA0 (par ex) en sortie
bus.write_byte_data(I2C_ADDR, IODIRA, 0x00)  # tout Port A en sortie
# pour plus fin : bus.write_byte_data(I2C_ADDR, IODIRA, 0b11111110) si GPA0 sortie, autres en entrée

# allumer GPA0
bus.write_byte_data(I2C_ADDR, GPIOA, 0x01)
sleep(2)

# éteindre GPA0
bus.write_byte_data(I2C_ADDR, GPIOA, 0x00)
