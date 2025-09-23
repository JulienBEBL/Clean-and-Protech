#!/usr/bin/python3
import time
from libs.LCDI2C_backpack import LCDI2C_backpack

LCD_W = 16

def write_line(lcd, line, text):
    lcd.lcd_string(str(text).ljust(LCD_W)[:LCD_W], line)

if __name__ == "__main__":
    lcd = LCDI2C_backpack(0x27)
    try:
        lcd.clear()
        write_line(lcd, lcd.LCD_LINE_1, "Test LCD")
        write_line(lcd, lcd.LCD_LINE_2, "Sans clear (1)")
        time.sleep(2)

        # Chaine plus courte -> padding nécessaire
        write_line(lcd, lcd.LCD_LINE_2, "OK")
        time.sleep(2)

        # Avec clear
        lcd.clear()
        write_line(lcd, lcd.LCD_LINE_1, "Avec clear")
        write_line(lcd, lcd.LCD_LINE_2, "Ligne propre")
        time.sleep(2)

        # Démo de plusieurs messages
        msgs = ["Initialisation", "Programme 1", "CONFIRME", "EN COURS", "FINI"]
        for m in msgs:
            write_line(lcd, lcd.LCD_LINE_1, m)
            write_line(lcd, lcd.LCD_LINE_2, f"len={len(m)}")
            time.sleep(1.2)

        print("[OK] Tests LCD terminés.")
    except KeyboardInterrupt:
        pass
