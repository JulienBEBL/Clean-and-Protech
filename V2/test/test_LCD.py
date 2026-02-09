#!/usr/bin/python3
# test_lcd_i2c.py
# Test pour la lib LCDI2C_backpack (smbus) fournie.
#
# Arborescence attendue:
# project/
#   test_lcd_i2c.py
#   libs/
#     lcd_i2c.py   (contient la classe LCDI2C_backpack)

import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(BASE_DIR, "libs")
sys.path.append(LIB_DIR)

from lcd_i2c import LCDI2C_backpack


def main():
    # Mets ici l'adresse que tu vois dans: sudo i2cdetect -y 1
    # Ex: 0x27 ou 0x3F
    I2C_ADDR = 0x27

    # IMPORTANT: ta lib a LCD_WIDTH=16 par défaut.
    # Si ton écran est 20x4, change LCD_WIDTH = 20 DANS la lib (ou force ici):
    # LCDI2C_backpack.LCD_WIDTH = 20
    LCDI2C_backpack.LCD_WIDTH = 20  # commente si tu es en 16x2

    lcd = LCDI2C_backpack(I2C_ADDR)

    # ---- Test 1: clear + écriture lignes ----
    lcd.clear()
    lcd.lcd_string("TEST LCD I2C", lcd.LCD_LINE_1)
    lcd.lcd_string(f"ADDR: {hex(I2C_ADDR)}", lcd.LCD_LINE_2)
    lcd.lcd_string("LIGNE 3 OK", lcd.LCD_LINE_3)
    lcd.lcd_string("LIGNE 4 OK", lcd.LCD_LINE_4)
    time.sleep(2)

    # ---- Test 2: compteur sur ligne 2 ----
    lcd.clear()
    lcd.lcd_string("COMPTEUR:", lcd.LCD_LINE_1)
    for i in range(0, 21):
        lcd.lcd_string(f"i={i}".ljust(lcd.LCD_WIDTH), lcd.LCD_LINE_2)
        time.sleep(0.2)

    # ---- Test 3: test retour ligne via message() ----
    lcd.clear()
    lcd.message("message()\nligne 2")
    time.sleep(2)

    # ---- Test 4: scrolling ----
    lcd.clear()
    lcd.lcd_string("SCROLL TEST", lcd.LCD_LINE_1)
    lcd.lcd_string(">>>>>>>>>>>>>>>>>>>>", lcd.LCD_LINE_2)
    for _ in range(6):
        lcd.scrollDisplayRight()
        time.sleep(0.3)
    for _ in range(6):
        lcd.scrollDisplayLeft()
        time.sleep(0.3)

    # ---- Fin ----
    lcd.clear()
    lcd.lcd_string("FIN DU TEST", lcd.LCD_LINE_2)
    time.sleep(2)
    lcd.clear()


if __name__ == "__main__":
    main()
