"""
test_vic.py — Test sens de rotation VIC (100 pas ouverture, 100 pas fermeture).

Séquence :
    1. 100 pas direction OUVERTURE  — pause 3s
    2. 100 pas direction FERMETURE  — pause 3s
    3. Répète REPEAT_CYCLES fois

Objectif : vérifier visuellement que la VIC change bien de sens entre
les deux mouvements. Si elle tourne toujours dans le même sens,
le câblage DIR ou la logique de direction est à revoir.

Paramètres modifiables en tête de fichier.
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

# ── Paramètres modifiables ────────────────────────────────────────────────────
STEPS: int           = 200             # nombre de pas par mouvement
VIC_SPEED_SPS: float = config.VIC_SPEED_SPS  # vitesse (sps)
PAUSE_S: float       = 3.0            # pause entre chaque mouvement (s)
REPEAT_CYCLES: int   = 3              # nombre de cycles aller-retour
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    print("=" * 54)
    print("  TEST VIC — sens de rotation")
    print("=" * 54)
    print(f"  Pas        : {STEPS} steps")
    print(f"  Vitesse    : {VIC_SPEED_SPS} sps")
    print(f"  Pause      : {PAUSE_S}s")
    print(f"  Cycles     : {REPEAT_CYCLES}")
    print("  Ctrl+C pour arrêter\n")

    gpio_handle.init()

    with I2CBus() as bus:
        io = IOBoard(bus)
        io.init()

        lcd = LCD2004(bus)
        lcd.init()
        lcd.clear()
        lcd.write_centered(1, "TEST VIC")
        lcd.write_centered(2, f"{STEPS} pas @ {VIC_SPEED_SPS:.0f} sps")

        with MotorController(io) as motors:
            try:
                for cycle in range(1, REPEAT_CYCLES + 1):
                    print(f"\n  ── Cycle {cycle}/{REPEAT_CYCLES}")

                    # ── OUVERTURE ────────────────────────────────────────────
                    print(f"  OUVERTURE — {STEPS} pas")
                    lcd.write(3, f"Cycle {cycle}/{REPEAT_CYCLES}            ")
                    lcd.write(4, f"OUVERTURE {STEPS} pas      ")

                    t0 = time.monotonic()
                    motors.move_steps("VIC", STEPS, "ouverture", VIC_SPEED_SPS)
                    dt = time.monotonic() - t0

                    print(f"    → OK  {dt:.1f}s")
                    lcd.write(4, f"OK ouv  {dt:.1f}s          ")
                    time.sleep(PAUSE_S)

                    # ── FERMETURE ────────────────────────────────────────────
                    print(f"  FERMETURE — {STEPS} pas")
                    lcd.write(4, f"FERMETURE {STEPS} pas      ")

                    t0 = time.monotonic()
                    motors.move_steps("VIC", STEPS, "fermeture", VIC_SPEED_SPS)
                    dt = time.monotonic() - t0

                    print(f"    → OK  {dt:.1f}s")
                    lcd.write(4, f"OK fer  {dt:.1f}s          ")
                    time.sleep(PAUSE_S)

                print()
                print("=" * 54)
                print("  TEST TERMINÉ")
                print("=" * 54)
                lcd.clear()
                lcd.write_centered(1, "TEST VIC")
                lcd.write_centered(2, "Termine")

            except KeyboardInterrupt:
                print("\n  Arrêté par l'utilisateur.")
                lcd.clear()
                lcd.write_centered(1, "Arret utilisateur")
            finally:
                motors.disable_all_drivers()

    gpio_handle.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  Arrêté par l'utilisateur.")
        gpio_handle.close()
