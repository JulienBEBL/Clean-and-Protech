"""
test_moteur_identification.py — Identification physique des moteurs

Pour chaque driver (ID 1 → 8) :
    1. Clignote l'ENA 10 fois (ON 0.75s / OFF 0.75s)
       → le driver émet un clic ou un bruit caractéristique à chaque activation
    2. Attend que l'utilisateur note quel driver a réagi
       puis appuie sur Entrée pour passer au suivant

Aucun mouvement moteur — identification par activation ENA uniquement.

Résultat attendu : un tableau de correspondance
    ID driver | GPIO PUL | Nom actuel config | Nom physique réel

Met à jour MOTOR_NAME_TO_ID et MOTOR_PUL_PINS dans config.py
en fonction de tes observations.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
import libs.gpio_handle as gpio_handle
from libs.i2c_bus import I2CBus
from libs.io_board import IOBoard
from libs.lcd2004 import LCD2004
from libs.moteur import MotorController

ENA_BLINK_COUNT = 10    # nombre d'activations ENA
ENA_BLINK_ON_S  = 0.75  # durée ENA actif (s)
ENA_BLINK_OFF_S = 0.75  # durée ENA inactif (s)

# Nom actuel dans config (pour affichage seulement)
ID_TO_NAME = {v: k for k, v in config.MOTOR_NAME_TO_ID.items()}


def main() -> None:
    print("=" * 50)
    print("  IDENTIFICATION MOTEURS")
    print("=" * 50)
    print(f"  Séquence ENA : {ENA_BLINK_COUNT}x (ON {ENA_BLINK_ON_S}s / OFF {ENA_BLINK_OFF_S}s)")
    print(f"  Durée totale par driver : ~{ENA_BLINK_COUNT * (ENA_BLINK_ON_S + ENA_BLINK_OFF_S):.0f}s")
    print("  Aucun mouvement moteur — identification par activation ENA uniquement")
    print("  Appuie sur Entrée pour passer au suivant")
    print("  Ctrl+C pour arrêter\n")

    gpio_handle.init()

    with I2CBus() as bus:
        io = IOBoard(bus)
        io.init()

        lcd = LCD2004(bus)
        lcd.init()
        lcd.clear()
        lcd.write_centered(1, "IDENTIFICATION")
        lcd.write_centered(2, "MOTEURS")
        time.sleep(1.5)

        with MotorController(io) as motors:
            try:
                for driver_id in range(1, 9):
                    name    = ID_TO_NAME.get(driver_id, "???")
                    pul_gpio = config.MOTOR_PUL_PINS[driver_id]

                    print(f"\n{'─' * 40}")
                    print(f"  Driver ID  : {driver_id}")
                    print(f"  Nom config : {name}")
                    print(f"  GPIO PUL   : BCM {pul_gpio}")
                    print(f"{'─' * 40}")

                    lcd.write(1, f"Driver ID : {driver_id}         ")
                    lcd.write(2, f"{name:<20}")
                    lcd.write(3, f"GPIO PUL  : {pul_gpio}         ")
                    lcd.write(4, "Activation...       ")

                    # --- clignotement ENA 10x ---
                    print(f"  Clignotement ENA ({ENA_BLINK_COUNT}x)...")
                    for blink in range(1, ENA_BLINK_COUNT + 1):
                        lcd.write(4, f"ENA {blink:02d}/{ENA_BLINK_COUNT} ON          ")
                        motors.enable_driver(name)
                        time.sleep(ENA_BLINK_ON_S)

                        lcd.write(4, f"ENA {blink:02d}/{ENA_BLINK_COUNT} OFF         ")
                        motors.disable_driver(name)
                        time.sleep(ENA_BLINK_OFF_S)

                    print("  Clignotement terminé.")

                    lcd.write(4, "Entrée = suivant    ")
                    input("  → Quel moteur physique a bougé ? Note-le puis appuie sur Entrée : ")

            except KeyboardInterrupt:
                print("\nArrêté par l'utilisateur.")
            finally:
                motors.disable_all_drivers()
                lcd.clear()
                lcd.write_centered(1, "Test termine")

    gpio_handle.close()

    print("\n" + "=" * 50)
    print("  RÉCAPITULATIF À NOTER :")
    print("=" * 50)
    print(f"  {'ID':<4} {'GPIO PUL':<10} {'Nom config actuel':<20} {'Moteur physique'}")
    print(f"  {'──':<4} {'────────':<10} {'─────────────────':<20} {'───────────────'}")
    for driver_id in range(1, 9):
        name     = ID_TO_NAME.get(driver_id, "???")
        pul_gpio = config.MOTOR_PUL_PINS[driver_id]
        print(f"  {driver_id:<4} BCM {pul_gpio:<6} {name:<20} ???")
    print()
    print("  Remplis la colonne 'Moteur physique' et")
    print("  mets à jour MOTOR_NAME_TO_ID dans config.py.")
    print("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nArrêté par l'utilisateur.")
        gpio_handle.close()
