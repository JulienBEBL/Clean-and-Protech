"""
test_lcd.py — Test hardware écran LCD2004 (HD44780 via I2C)

Séquence :
    1. Init + message de bienvenue
    2. Écriture sur les 4 lignes
    3. Texte centré
    4. Défilement ligne par ligne (clear_line)
    5. Backlight ON / OFF
    6. Affichage ticker (compteur temps réel)

Ctrl+C pour arrêter le ticker et quitter proprement.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from libs.i2c_bus import I2CBus
from libs.lcd2004 import LCD2004


def main() -> None:
    with I2CBus() as bus:
        lcd = LCD2004(bus)
        lcd.init()

        # --- 1. Message de bienvenue ---
        print("Test 1 : message de bienvenue")
        lcd.write(1, "Clean & Protech")
        lcd.write(2, "V4 - LCD TEST")
        lcd.write(3, "SEA-1295 / RPi5")
        lcd.write(4, "Demarrage OK")
        time.sleep(2.0)

        # --- 2. Écriture sur les 4 lignes (texte pleine largeur) ---
        print("Test 2 : 4 lignes remplies")
        lcd.clear()
        lcd.write(1, "Ligne 1 xxxxxxxxxxxxxxx")   # tronqué à 20 car.
        lcd.write(2, "Ligne 2 ---------------")
        lcd.write(3, "Ligne 3 ***************")
        lcd.write(4, "Ligne 4 ===============")
        time.sleep(2.0)

        # --- 3. Texte centré ---
        print("Test 3 : texte centré")
        lcd.clear()
        lcd.write_centered(1, "V4")
        lcd.write_centered(2, "Test centre")
        lcd.write_centered(3, "Clean & Protech")
        lcd.write_centered(4, "OK")
        time.sleep(2.0)

        # --- 4. clear_line ligne par ligne ---
        print("Test 4 : effacement ligne par ligne")
        for line in range(1, 5):
            lcd.clear_line(line)
            time.sleep(0.4)

        # --- 5. Backlight ON / OFF ---
        print("Test 5 : backlight OFF (2s) puis ON")
        lcd.write(1, "Backlight OFF...")
        time.sleep(0.5)
        lcd.backlight(False)
        time.sleep(2.0)
        lcd.backlight(True)
        lcd.write(1, "Backlight ON    ")
        time.sleep(1.0)

        # --- 6. Ticker temps réel ---
        print("Test 6 : ticker temps réel (Ctrl+C pour arrêter)")
        lcd.clear()
        lcd.write(1, "  Ticker actif  ")
        t0 = time.monotonic()

        try:
            while True:
                dt = time.monotonic() - t0
                minutes = int(dt) // 60
                seconds = int(dt) % 60
                millis  = int((dt % 1) * 10)

                lcd.write(2, f"  {minutes:02d}:{seconds:02d}.{millis}  ")
                lcd.write(3, f"t = {dt:8.1f} s")
                time.sleep(0.1)

        except KeyboardInterrupt:
            print("\nArrêté par l'utilisateur.")
        finally:
            lcd.clear()
            lcd.write(1, "Test LCD termine")


if __name__ == "__main__":
    main()
