"""
test_moteur_identification.py — Identification physique des moteurs

Pour chaque driver (ID 1 → 8) :
    1. Active le driver (ENA)
    2. Tourne ~5s en ouverture
    3. Pause 0.5s
    4. Retourne à la position initiale (~5s en fermeture)
    5. Désactive le driver (ENA)
    6. Attend que l'utilisateur note quel moteur physique a bougé
       puis appuie sur Entrée pour passer au suivant

Durée totale par moteur : ~10 secondes de mouvement.

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

STEPS      = 400   # 5 tours (400 microsteps/tour × 5) — ~5s par sens à SPEED_SPS
SPEED_SPS  = 800    # 1 tour/seconde — assez lent pour identifier visuellement
PAUSE_S    = 1    # pause entre ouverture et retour

# Nom actuel dans config (pour affichage seulement)
ID_TO_NAME = {v: k for k, v in config.MOTOR_NAME_TO_ID.items()}


def main() -> None:
    print("=" * 50)
    print("  IDENTIFICATION MOTEURS")
    print("=" * 50)
    print(f"  {STEPS} pas par sens ({STEPS // 400} tours) à {SPEED_SPS} sps ≈ 10s par moteur")
    print(f"  Séquence : ouverture {STEPS} pas → pause → retour {STEPS} pas")
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

                    # --- active le driver (ENA) ---
                    motors.enable_driver(name)
                    print("  ENA : ON")
                    time.sleep(0.2)

                    # --- ouverture ~5s ---
                    lcd.write(4, f"Ouverture {STEPS} pas  ")
                    print(f"  Ouverture : {STEPS} pas (~{STEPS // SPEED_SPS}s)...")
                    motors.move_steps(
                        motor_name=name,
                        steps=STEPS,
                        direction="ouverture",
                        speed_sps=SPEED_SPS,
                    )
                    print("  Ouverture terminée.")
                    time.sleep(PAUSE_S)

                    # --- retour fermeture ~5s ---
                    lcd.write(4, f"Retour   {STEPS} pas  ")
                    print(f"  Retour   : {STEPS} pas (~{STEPS // SPEED_SPS}s)...")
                    motors.move_steps(
                        motor_name=name,
                        steps=STEPS,
                        direction="fermeture",
                        speed_sps=SPEED_SPS,
                    )
                    print("  Retour terminé.")

                    # --- désactive le driver ---
                    motors.disable_driver(name)
                    print("  ENA : OFF")
                    time.sleep(PAUSE_S)

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
