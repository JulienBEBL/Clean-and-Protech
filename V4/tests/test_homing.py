"""
test_homing.py — Homing + ouverture séquentielle de chaque moteur

Séquence :
    1. Homing — tous les moteurs en fermeture simultanée à haute vitesse
       (ramène chaque vanne en butée fermeture, quelle que soit la position initiale)
    2. Ouverture séquentielle — ouverture complète de chaque moteur l'un après l'autre
       avec une pause entre chaque, dans l'ordre de MOTOR_NAME_TO_ID

Ctrl+C pour arrêter proprement à n'importe quel moment.
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

# Pause entre chaque ouverture (s)
PAUSE_BETWEEN_S: float = 1.5

# Ordre d'ouverture : ID driver 1 → 8
MOTOR_ORDER = sorted(config.MOTOR_NAME_TO_ID.items(), key=lambda x: x[1])


def main() -> None:
    print("=" * 50)
    print("  TEST HOMING + OUVERTURE SÉQUENTIELLE")
    print("=" * 50)
    print(f"  Homing    : {config.MOTOR_HOMING_STEPS} steps "
          f"@ {config.MOTOR_HOMING_SPEED_SPS:.0f} sps "
          f"({config.MOTOR_HOMING_SPEED_SPS / config.DRIVER_MICROSTEP:.1f} tours/s)")
    print(f"  Ouverture : {config.MOTOR_OUVERTURE_STEPS} steps "
          f"@ {config.MOTOR_OUVERTURE_SPEED_SPS:.0f} sps "
          f"(accel={config.MOTOR_OUVERTURE_ACCEL_SPS:.0f} / decel={config.MOTOR_OUVERTURE_DECEL_SPS:.0f})")
    print(f"  Moteurs   : {len(MOTOR_ORDER)} (ordre ID 1→8)")
    print("  Ctrl+C pour arrêter\n")

    gpio_handle.init()

    with I2CBus() as bus:
        io = IOBoard(bus)
        io.init()

        lcd = LCD2004(bus)
        lcd.init()
        lcd.clear()
        lcd.write_centered(1, "HOMING + OUVERTURE")
        lcd.write_centered(3, "Démarrage...")
        time.sleep(1.5)

        with MotorController(io) as motors:
            try:
                # ── 1. HOMING ────────────────────────────────────────────────
                print("─" * 50)
                print("  ÉTAPE 1 — HOMING (tous moteurs → fermeture)")
                print("─" * 50)
                lcd.clear()
                lcd.write_centered(1, "HOMING")
                lcd.write_centered(2, "Tous moteurs")
                lcd.write_centered(3, "fermeture...")

                t0 = time.monotonic()
                motors.homing()
                dt = time.monotonic() - t0

                print(f"  Homing terminé en {dt:.2f}s")
                lcd.write_centered(3, f"OK  {dt:.2f}s")
                lcd.write_centered(4, "")
                time.sleep(PAUSE_BETWEEN_S)

                # ── 2. OUVERTURE SÉQUENTIELLE ─────────────────────────────────
                print()
                print("─" * 50)
                print("  ÉTAPE 2 — OUVERTURE SÉQUENTIELLE")
                print("─" * 50)

                for name, driver_id in MOTOR_ORDER:
                    print(f"\n  [{driver_id}/8] {name}")
                    lcd.clear()
                    lcd.write(1, f"OUVERTURE [{driver_id}/8]")
                    lcd.write(2, f"{name:<20}")
                    lcd.write(3, "En cours...         ")
                    lcd.write(4, "                    ")

                    t0 = time.monotonic()
                    motors.ouverture(name)
                    dt = time.monotonic() - t0

                    print(f"       → terminé en {dt:.2f}s")
                    lcd.write(3, f"OK  {dt:.2f}s          ")
                    time.sleep(PAUSE_BETWEEN_S)

                # ── FIN ───────────────────────────────────────────────────────
                print()
                print("=" * 50)
                print("  TEST TERMINÉ")
                print("=" * 50)
                lcd.clear()
                lcd.write_centered(1, "Test termine")
                lcd.write_centered(2, "OK")

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
