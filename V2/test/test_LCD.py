#!/usr/bin/python3
# --------------------------------------
# test_lcd_i2c_20x4.py
# Test complet pour libs/lcd_i2c_20x4.py
#
# Arborescence:
# project/
#   test_lcd_i2c_20x4.py
#   libs/
#     lcd_i2c_20x4.py
# --------------------------------------

import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(BASE_DIR, "libs")
sys.path.append(LIB_DIR)

from lcd_i2c_20x4 import LCDI2C_backpack


def pause(sec: float):
    time.sleep(sec)


def main():
    lcd = LCDI2C_backpack(I2C_ADDR=0x27)

    # ---------- TEST 0: init + clear ----------
    lcd.clear()
    lcd.backlight_on()
    lcd.write_centered("INIT OK", lcd.LCD_LINE_2)
    pause(1.5)

    # ---------- TEST 1: backlight ON/OFF ----------
    lcd.clear()
    lcd.write_centered("BACKLIGHT TEST", lcd.LCD_LINE_1)
    lcd.lcd_string("OFF 1s", lcd.LCD_LINE_3)
    lcd.backlight_off()
    pause(1.0)

    lcd.backlight_on()
    lcd.lcd_string("ON  1s", lcd.LCD_LINE_4)
    pause(1.0)

    # ---------- TEST 2: lcd_string (4 lignes) ----------
    lcd.clear()
    lcd.lcd_string("lcd_string L1 OK", lcd.LCD_LINE_1)
    lcd.lcd_string("lcd_string L2 OK", lcd.LCD_LINE_2)
    lcd.lcd_string("lcd_string L3 OK", lcd.LCD_LINE_3)
    lcd.lcd_string("lcd_string L4 OK", lcd.LCD_LINE_4)
    pause(2.0)

    # ---------- TEST 3: overwrite (vérifie effacement par padding) ----------
    lcd.clear()
    lcd.lcd_string("12345678901234567890", lcd.LCD_LINE_2)
    pause(1.2)
    # Doit effacer les caractères restants (car lcd_string pad à 20)
    lcd.lcd_string("SHORT", lcd.LCD_LINE_2)
    pause(1.5)

    # ---------- TEST 4: write_centered ----------
    lcd.clear()
    lcd.write_centered("CENTRAGE", lcd.LCD_LINE_1)
    lcd.write_centered("CLEAN & PROTECH", lcd.LCD_LINE_2)
    lcd.write_centered("20x4 I2C", lcd.LCD_LINE_3)
    lcd.write_centered("OK", lcd.LCD_LINE_4)
    pause(2.5)

    # ---------- TEST 5: write_centered truncation (texte > 20) ----------
    lcd.clear()
    lcd.write_centered("TRUNCATION TEST", lcd.LCD_LINE_1)
    lcd.write_centered("0123456789ABCDEFGHIJKL", lcd.LCD_LINE_3)  # >20
    lcd.write_centered("doit etre coupe", lcd.LCD_LINE_4)
    pause(2.5)

    # ---------- TEST 6: message() + newline ----------
    lcd.clear()
    lcd.lcd_string("message() test:", lcd.LCD_LINE_1)
    # NOTE: message() ne gère que '\n' -> line 2 (comme dans ta lib)
    lcd.message("L2 via newline\nL2 suite")
    pause(2.5)

    # ---------- TEST 7: clear final + fin ----------
    lcd.clear()
    lcd.write_centered("FIN DU TEST", lcd.LCD_LINE_2)
    pause(2.0)

    lcd.clear()
    lcd.backlight_off()


if __name__ == "__main__":
    main()
