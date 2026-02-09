#!/usr/bin/python3
# --------------------------------------
# Test LCD I2C 20x4
# Compatible avec lcd_i2c_20x4.py
# --------------------------------------

import os
import sys
import time

# Ajout du dossier libs au PYTHONPATH
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(BASE_DIR, "libs")
sys.path.append(LIB_DIR)

from lcd_i2c_20x4 import LCDI2C_backpack


def main():
    # L'adresse est déjà 0x27 par défaut dans la lib,
    # mais on la passe explicitement pour clarté.
    lcd = LCDI2C_backpack(I2C_ADDR=0x27)

    # -------- Test 1 : Backlight --------
    lcd.backlight_on()
    lcd.clear()
    lcd.lcd_string("BACKLIGHT ON", lcd.LCD_LINE_2)
    time.sleep(2)

    lcd.backlight_off()
    time.sleep(1)
    lcd.backlight_on()

    # -------- Test 2 : Ecriture lignes --------
    lcd.clear()
    lcd.lcd_string("TEST LCD 20x4", lcd.LCD_LINE_1)
    lcd.lcd_string("LIGNE 2 OK",   lcd.LCD_LINE_2)
    lcd.lcd_string("LIGNE 3 OK",   lcd.LCD_LINE_3)
    lcd.lcd_string("LIGNE 4 OK",   lcd.LCD_LINE_4)
    time.sleep(2)

    # -------- Test 3 : Compteur --------
    lcd.clear()
    lcd.lcd_string("COMPTEUR:", lcd.LCD_LINE_1)
    for i in range(10):
        lcd.lcd_string(f"Valeur: {i}".ljust(lcd.LCD_WIDTH),
                       lcd.LCD_LINE_2)
        time.sleep(0.5)

    # -------- Test 4 : message() --------
    lcd.clear()
    lcd.message("message()\nligne 2")
    time.sleep(2)

    # -------- Test 5 : Scroll --------
    lcd.clear()
    lcd.lcd_string("SCROLL TEST", lcd.LCD_LINE_1)
    lcd.lcd_string(">>>>>>>>>>>>>>>>>>>>", lcd.LCD_LINE_2)
    for _ in range(5):
        lcd.scrollDisplayRight()
        time.sleep(0.3)
    for _ in range(5):
        lcd.scrollDisplayLeft()
        time.sleep(0.3)

    # -------- Fin --------
    lcd.clear()
    lcd.lcd_string("FIN DU TEST", lcd.LCD_LINE_2)
    time.sleep(2)
    lcd.clear()
    lcd.backlight_off()


if __name__ == "__main__":
    main()
