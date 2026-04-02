"""
test_vic.py — Test manuel de la VIC par move_steps().

Permet de déplacer la VIC pas à pas entre ses 5 positions (0, 30, 50, 70, 100)
et de valider le sens ouverture / fermeture sur le terrain.

Séquence automatique :
    1. Fermeture butée (position 0 — DEPART)
    2. Déplacement vers chaque position VIC_POSITIONS (1 → 5) avec pause
    3. Retour position 0 (DEPART)

Paramètres modifiables en tête de fichier :
    VIC_SPEED_SPS   — vitesse en steps/sec (défaut : config.VIC_SPEED_SPS)
    PAUSE_S         — pause entre chaque position (secondes)

Ctrl+C pour arrêter proprement à tout moment.
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
VIC_SPEED_SPS: float = config.VIC_SPEED_SPS   # vitesse (sps) — défaut config.py
PAUSE_S: float       = 3.0                     # pause entre chaque position (s)
# ─────────────────────────────────────────────────────────────────────────────

# Positions à tester dans l'ordre (clé sélecteur → steps)
VIC_SEQUENCE = sorted(config.VIC_POSITIONS.items())  # [(1,0),(2,30),(3,50),(4,70),(5,100)]


def _move_vic(motors: MotorController, current: int, target: int, lcd: LCD2004) -> int:
    """Déplace la VIC de current vers target. Retourne target."""
    delta = target - current
    if delta == 0:
        print(f"    VIC déjà à {target} pas — aucun mouvement")
        return target

    direction = "ouverture" if delta > 0 else "fermeture"
    steps     = abs(delta)

    print(f"    VIC {current} → {target} pas  ({direction}, {steps} pas @ {VIC_SPEED_SPS} sps)")
    lcd.write(3, f"VIC {current:3d} -> {target:3d} pas   ")
    lcd.write(4, f"{direction:<20}")

    t0 = time.monotonic()
    motors.move_steps("VIC", steps, direction, VIC_SPEED_SPS)
    dt = time.monotonic() - t0

    print(f"    → OK  {dt:.1f}s")
    lcd.write(4, f"OK  {dt:.1f}s              ")
    return target


def main() -> None:
    print("=" * 54)
    print("  TEST VIC — move_steps()")
    print("=" * 54)
    print(f"  Vitesse    : {VIC_SPEED_SPS} sps")
    print(f"  Pause      : {PAUSE_S}s entre positions")
    print(f"  Positions  : {[v for _, v in VIC_SEQUENCE]}")
    print("  Ctrl+C pour arrêter\n")

    gpio_handle.init()

    with I2CBus() as bus:
        io = IOBoard(bus)
        io.init()

        lcd = LCD2004(bus)
        lcd.init()
        lcd.clear()
        lcd.write_centered(1, "TEST VIC")
        lcd.write_centered(2, f"{VIC_SPEED_SPS:.0f} sps")

        with MotorController(io) as motors:
            try:
                vic_pos = 0   # position courante en pas (inconnue au départ)

                # ── 1. Fermeture butée → position 0
                print("\n  ── Homing VIC → position 0 (fermeture butée)")
                lcd.write(2, "Homing VIC...       ")
                homing_steps = int(config.VIC_TOTAL_STEPS * config.MOTOR_HOMING_FIRST_CLOSE_FACTOR)
                print(f"    fermeture {homing_steps} pas (butée +{int((config.MOTOR_HOMING_FIRST_CLOSE_FACTOR-1)*100)}%)")
                lcd.write(3, f"fermeture {homing_steps} pas    ")
                lcd.write(4, "                    ")

                t0 = time.monotonic()
                motors.move_steps("VIC", homing_steps, "fermeture", VIC_SPEED_SPS)
                dt = time.monotonic() - t0
                vic_pos = 0

                print(f"    → OK  {dt:.1f}s — VIC @ 0 pas (DEPART)")
                lcd.write(3, f"OK  {dt:.1f}s              ")
                lcd.write(4, "VIC @ 0 (DEPART)    ")
                time.sleep(PAUSE_S)

                # ── 2. Déplacement vers chaque position
                print("\n  ── Séquence positions 1 → 5")
                for sel, target_steps in VIC_SEQUENCE:
                    label = {
                        config.VIC_DEPART_STEPS: "DEPART",
                        config.VIC_NEUTRE_STEPS: "NEUTRE",
                        config.VIC_RETOUR_STEPS: "RETOUR",
                    }.get(target_steps, f"{target_steps}p")

                    print(f"\n  Position {sel} — {target_steps} pas ({label})")
                    lcd.write(2, f"Position {sel} — {label:<11}")

                    vic_pos = _move_vic(motors, vic_pos, target_steps, lcd)
                    time.sleep(PAUSE_S)

                # ── 3. Retour position 0
                print("\n  ── Retour position 0 (DEPART)")
                lcd.write(2, "Retour DEPART       ")
                vic_pos = _move_vic(motors, vic_pos, 0, lcd)
                time.sleep(PAUSE_S)

                # ── Fin
                print()
                print("=" * 54)
                print("  TEST VIC TERMINÉ")
                print("=" * 54)
                lcd.clear()
                lcd.write_centered(1, "TEST VIC")
                lcd.write_centered(2, "Termine")
                lcd.write_centered(3, f"Pos finale : {vic_pos} pas")

            except KeyboardInterrupt:
                print("\n  Arrêté par l'utilisateur.")
                lcd.clear()
                lcd.write_centered(1, "Arret utilisateur")
                lcd.write_centered(2, f"VIC ~ {vic_pos} pas")
            finally:
                motors.disable_all_drivers()

    gpio_handle.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  Arrêté par l'utilisateur.")
        gpio_handle.close()
