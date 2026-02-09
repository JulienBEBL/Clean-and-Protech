#!/usr/bin/python3
import time
import sys
import os

# Ajout du dossier /libs au PYTHONPATH
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(BASE_DIR, "libs")
sys.path.append(LIB_DIR)

from lcd_i2c_20x4 import LCDI2CBackpack


def main():
    # Paramètres LCD (à adapter si besoin)
    I2C_ADDR = 0x3F      # ou 0x27
    WIDTH = 20
    ROWS = 4
    BUS = 1

    lcd = LCDI2CBackpack(
        i2c_addr=I2C_ADDR,
        width=WIDTH,
        rows=ROWS,
        bus_id=BUS
    )

    # ===== TEST BACKLIGHT =====
    lcd.backlight_on()
    lcd.clear()
    lcd.write_centered(1, "TEST LCD I2C")
    lcd.write_centered(2, "Backlight ON")
    time.sleep(2)

    lcd.backlight_off()
    time.sleep(1)
    lcd.backlight_on()

    # ===== TEST ECRITURE LIGNES =====
    lcd.clear()
    lcd.write_line(1, "Ligne 1: OK")
    lcd.write_line(2, "Ligne 2: OK")
    lcd.write_line(3, "Ligne 3: OK")
    lcd.write_line(4, "Ligne 4: OK")
    time.sleep(2)

    # ===== TEST CENTRAGE =====
    lcd.clear()
    lcd.write_centered(1, "CENTRAGE")
    lcd.write_centered(2, "20x4 LCD")
    lcd.write_centered(3, "I2C BACKPACK")
    lcd.write_centered(4, "OK")
    time.sleep(2)

    # ===== TEST EFFACEMENT LIGNE =====
    lcd.clear()
    lcd.write_line(1, "Effacement ligne")
    lcd.write_line(2, "Cette ligne va")
    lcd.write_line(3, "disparaitre...")
    time.sleep(2)

    lcd.clear_line(3)
    lcd.write_line(4, "Ligne 3 effacee")
    time.sleep(2)

    # ===== TEST COMPTEUR =====
    lcd.clear()
    lcd.write_centered(1, "COMPTEUR")
    for i in range(10):
        lcd.write_line(3, f"Valeur: {i}".ljust(WIDTH))
        time.sleep(0.5)

    # ===== FIN =====
    lcd.clear()
    lcd.write_centered(2, "FIN DU TEST")
    time.sleep(2)

    lcd.backlight_off()
    lcd.clear()


if __name__ == "__main__":
    main()
