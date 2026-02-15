"""
tests/test_i2c.py

Test manuel simple (sans argparse) pour valider rapidement:
- Entrées utilisateur: PRG / VIC / AIR (actif bas => *_active() == 1 quand appuyé/sélectionné)
- Sorties: LEDs / ENA / DIR
- LCD (optionnel)

Arborescence:
  /lib/i2c.py
  /tests/test_i2c.py

Exécution:
- Lancer directement ce fichier depuis ton IDE/remote desktop.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# ------------------------------------------------------------
# Import lib/i2c.py (sans installation de package)
# ------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = PROJECT_ROOT / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from i2c import I2CBus, IOBoard, LCD2004, ON, OFF  # type: ignore


# ----------------------------
# Configuration test
# ----------------------------
BUS_ID = 1
FREQ_HZ = 100_000
RETRIES = 2
RETRY_DELAY_S = 0.01

USE_LCD = True          # mets False si tu ne veux pas toucher à l'écran
LOOP_DELAY_S = 0.20     # tempo globale pour les boucles


# ----------------------------
# Helpers simples
# ----------------------------
def print_inputs(io: IOBoard) -> None:
    prg = [io.read_btn_active(i) for i in range(1, 7)]
    vic = [io.read_vic_active(i) for i in range(1, 6)]
    air = [io.read_air_active(i) for i in range(1, 5)]
    print(f"PRG={prg} | VIC={vic} | AIR={air}")


def demo_outputs(io: IOBoard) -> None:
    # LEDs: chenillard 1..6
    for i in range(1, 7):
        for k in range(1, 7):
            io.set_led(k, OFF)
        io.set_led(i, ON)
        time.sleep(0.15)

    # ENA/DIR: pulse ENA1..ENA8 + alternance DIR ouverture/fermeture
    for m in range(1, 9):
        io.set_ena(m, OFF)

    for m in range(1, 9):
        io.set_dir(m, "ouverture" if (m % 2 == 1) else "fermeture")
        io.set_ena(m, ON)
        time.sleep(0.20)
        io.set_ena(m, OFF)
        time.sleep(0.05)


def all_off(io: IOBoard) -> None:
    for i in range(1, 7):
        io.set_led(i, OFF)
    for m in range(1, 9):
        io.set_ena(m, OFF)
        io.set_dir(m, "fermeture")  # valeur par défaut arbitraire


# ----------------------------
# MAIN (test)
# ----------------------------
def main() -> None:
    bus = I2CBus(bus_id=BUS_ID, freq_hz=FREQ_HZ, retries=RETRIES, retry_delay_s=RETRY_DELAY_S)

    with bus:
        # Scan rapide (optionnel mais utile)
        addrs = bus.scan()
        print("I2C scan:", [f"0x{x:02X}" for x in addrs])

        io = IOBoard(bus)
        io.init(force=True)

        lcd = None
        if USE_LCD:
            try:
                lcd = LCD2004(bus, address=0x27, cols=20, rows=4)
                lcd.init()
                lcd.clear()
                lcd.write(1, "I2C TEST OK")
                lcd.write(2, "Inputs + outputs")
            except Exception as e:
                print(f"LCD init failed (ignored): {e}")
                lcd = None

        print("\n--- INPUTS (actif bas) ---")
        print("Appuie sur PRG/VIC/AIR et observe PRG/VIC/AIR passer a 1.")
        print("Stop: Ctrl+C\n")

        try:
            # Lecture entrées en continu
            while True:
                print_inputs(io)

                if lcd is not None:
                    # Affiche une synthèse rapide (ex: PRG1..PRG6)
                    prg = "".join(str(io.read_btn_active(i)) for i in range(1, 7))
                    vic = "".join(str(io.read_vic_active(i)) for i in range(1, 6))
                    air = "".join(str(io.read_air_active(i)) for i in range(1, 5))
                    lcd.write(3, f"PRG:{prg} VIC:{vic}".ljust(20))
                    lcd.write(4, f"AIR:{air}".ljust(20))

                # Démo outputs ponctuelle si PRG1 est appuyé
                if io.read_btn_active(1) == 1:
                    print("\nPRG1 detecte -> DEMO OUTPUTS\n")
                    if lcd is not None:
                        lcd.write(2, "DEMO OUTPUTS...".ljust(20))
                    demo_outputs(io)
                    if lcd is not None:
                        lcd.write(2, "Inputs + outputs".ljust(20))

                time.sleep(LOOP_DELAY_S)

        except KeyboardInterrupt:
            print("\nStopped by user.")
        finally:
            try:
                all_off(io)
                if lcd is not None:
                    lcd.clear()
                    lcd.write(1, "Test stopped")
            except Exception:
                pass


if __name__ == "__main__":
    main()
