"""
test_homing.py — Rodage : 10 cycles fermeture/ouverture sur 7 moteurs (VIC exclu)

Séquence :
    10 cycles identiques, dans l'ordre de MOTOR_NAME_TO_ID (ID 1→8, VIC ignoré) :
        1. Fermeture de chaque moteur (séquentielle)
        2. Ouverture de chaque moteur (séquentielle)

    Cycle 1 — première fermeture : +30 % de pas par rapport à MOTOR_FERMETURE_STEPS
              (garantit la butée fermeture quelle que soit la position initiale).
    Cycles 2-10 — fermeture standard : MOTOR_FERMETURE_STEPS.

    VIC (driver 3) est exclu du rodage.

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

# Nombre de cycles de rodage
RODAGE_CYCLES: int = 10

# Première fermeture : +30 % de pas (butée garantie)
FIRST_FERMETURE_STEPS: int = int(config.MOTOR_FERMETURE_STEPS * 1.15)

# Pause entre chaque mouvement (s)
PAUSE_BETWEEN_S: float = 0.5

# Moteurs exclus du rodage
RODAGE_EXCLUDED: set[str] = {"VIC"}

# Ordre d'exécution : ID driver 1 → 8, sans les exclus
MOTOR_ORDER = sorted(
    [(n, i) for n, i in config.MOTOR_NAME_TO_ID.items() if n not in RODAGE_EXCLUDED],
    key=lambda x: x[1],
)


def main() -> None:
    print("=" * 54)
    print("  TEST RODAGE — CYCLES FERMETURE / OUVERTURE")
    print("=" * 54)
    print(f"  Cycles        : {RODAGE_CYCLES}")
    print(f"  Fermeture #1  : {FIRST_FERMETURE_STEPS} steps "
          f"(+30 % vs {config.MOTOR_FERMETURE_STEPS})")
    print(f"  Fermeture x2+ : {config.MOTOR_FERMETURE_STEPS} steps "
          f"@ {config.MOTOR_FERMETURE_SPEED_SPS:.0f} sps")
    print(f"  Ouverture     : {config.MOTOR_OUVERTURE_STEPS} steps "
          f"@ {config.MOTOR_OUVERTURE_SPEED_SPS:.0f} sps")
    print(f"  Moteurs       : {len(MOTOR_ORDER)} (ordre ID 1→8, exclu : {', '.join(RODAGE_EXCLUDED)})")
    print("  Ctrl+C pour arrêter\n")

    gpio_handle.init()

    with I2CBus() as bus:
        io = IOBoard(bus)
        io.init()

        lcd = LCD2004(bus)
        lcd.init()
        lcd.clear()
        lcd.write_centered(1, "RODAGE")
        lcd.write_centered(2, f"{RODAGE_CYCLES} cycles")
        lcd.write_centered(3, "Démarrage...")
        time.sleep(1.5)

        with MotorController(io) as motors:
            try:
                for cycle in range(1, RODAGE_CYCLES + 1):
                    print()
                    print("─" * 54)
                    print(f"  CYCLE {cycle}/{RODAGE_CYCLES}")
                    print("─" * 54)

                    # ── FERMETURE ────────────────────────────────────────
                    first_cycle = (cycle == 1)
                    fermeture_steps = FIRST_FERMETURE_STEPS if first_cycle else config.MOTOR_FERMETURE_STEPS
                    extra_label = "  (+30 %)" if first_cycle else ""

                    print(f"\n  FERMETURE — {fermeture_steps} steps{extra_label}")
                    lcd.clear()
                    lcd.write(1, f"CYCLE {cycle}/{RODAGE_CYCLES}  FERMETURE")

                    for name, driver_id in MOTOR_ORDER:
                        print(f"    [{driver_id}/8] {name:<16} → fermeture")
                        lcd.write(2, f"[{driver_id}/8] {name:<18}")
                        lcd.write(3, "fermeture...        ")

                        t0 = time.monotonic()
                        motors.move_steps_ramp(
                            name,
                            fermeture_steps,
                            "fermeture",
                            config.MOTOR_FERMETURE_SPEED_SPS,
                            config.MOTOR_FERMETURE_ACCEL_SPS,
                            config.MOTOR_FERMETURE_DECEL_SPS,
                        )
                        dt = time.monotonic() - t0

                        print(f"         → {dt:.2f}s")
                        lcd.write(3, f"OK  {dt:.2f}s          ")
                        time.sleep(PAUSE_BETWEEN_S)

                    # ── OUVERTURE ─────────────────────────────────────────
                    print(f"\n  OUVERTURE — {config.MOTOR_OUVERTURE_STEPS} steps")
                    lcd.clear()
                    lcd.write(1, f"CYCLE {cycle}/{RODAGE_CYCLES}  OUVERTURE")

                    for name, driver_id in MOTOR_ORDER:
                        print(f"    [{driver_id}/8] {name:<16} → ouverture")
                        lcd.write(2, f"[{driver_id}/8] {name:<18}")
                        lcd.write(3, "ouverture...        ")

                        t0 = time.monotonic()
                        motors.ouverture(name)
                        dt = time.monotonic() - t0

                        print(f"         → {dt:.2f}s")
                        lcd.write(3, f"OK  {dt:.2f}s          ")
                        time.sleep(PAUSE_BETWEEN_S)

                # ── FIN ───────────────────────────────────────────────────
                print()
                print("=" * 54)
                print("  RODAGE TERMINÉ")
                print("=" * 54)
                lcd.clear()
                lcd.write_centered(1, "Rodage termine")
                lcd.write_centered(2, f"{RODAGE_CYCLES} cycles OK")

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
