#!/usr/bin/python3
# --------------------------------------
# Test complet pour lcd_i2c_20x4.py
# --------------------------------------

import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(BASE_DIR, "libs")
sys.path.append(LIB_DIR)

from lcd_i2c_20x4 import LCDI2C_backpack


def pause(t):
    time.sleep(t)


def main():
    lcd = LCDI2C_backpack()

    # ----- TEST 1: init / clear -----
    lcd.clear()
    lcd.backlight_on()
    lcd.write_centered("INIT OK", lcd.LCD_LINE_2)
    pause(1.5)

    # ----- TEST 2: backlight -----
    lcd.clear()
    lcd.write_centered("BACKLIGHT OFF", lcd.LCD_LINE_2)
    lcd.backlight_off()
    pause(1.0)

    lcd.backlight_on()
    lcd.write_centered("BACKLIGHT ON", lcd.LCD_LINE_3)
    pause(1.0)

    # ----- TEST 3: lcd_string 4 lignes -----
    lcd.clear()
    lcd.lcd_string("LCD STRING L1", lcd.LCD_LINE_1)
    lcd.lcd_string("LCD STRING L2", lcd.LCD_LINE_2)
    lcd.lcd_string("LCD STRING L3", lcd.LCD_LINE_3)
    lcd.lcd_string("LCD STRING L4", lcd.LCD_LINE_4)
    pause(2.0)

    # ----- TEST 4: overwrite propre -----
    lcd.clear()
    lcd.lcd_string("12345678901234567890", lcd.LCD_LINE_2)
    pause(1.0)
    lcd.lcd_string("SHORT", lcd.LCD_LINE_2)
    pause(1.5)

    # ----- TEST 5: write_centered -----
    lcd.clear()
    lcd.write_centered("CENTRAGE", lcd.LCD_LINE_1)
    lcd.write_centered("CLEAN & PROTECH", lcd.LCD_LINE_2)
    lcd.write_centered("LCD I2C 20x4", lcd.LCD_LINE_3)
    lcd.write_centered("OK", lcd.LCD_LINE_4)
    pause(2.5)

    # ----- TEST 6: truncation -----
    lcd.clear()
    lcd.write_centered("TEXTE TROP LONG POUR 20 CARACTERES", lcd.LCD_LINE_2)
    pause(2.5)

    # ----- FIN -----
    lcd.clear()
    lcd.write_centered("FIN DU TEST", lcd.LCD_LINE_2)
    pause(2.0)

    lcd.clear()
    lcd.backlight_off()


if __name__ == "__main__":
    main()
