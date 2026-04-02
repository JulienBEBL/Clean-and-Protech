"""
test_vic.py — Pilotage manuel de la VIC pas à pas.

À chaque invite, entrer un nombre de pas signé :
    +N  ou  N   → ouverture (N pas vers RETOUR)
    -N          → fermeture (N pas vers DEPART)
    0   ou rien → aucun mouvement (affiche juste la position)
    q           → quitter

Exemple :
    > 10      →  10 pas ouverture
    > -10     →  10 pas fermeture
    > 50      →  50 pas ouverture
    > q       →  quitte

La position courante est affichée à chaque étape.
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

# ── Paramètre modifiable ──────────────────────────────────────────────────────
VIC_SPEED_SPS: float = config.VIC_SPEED_SPS   # vitesse (sps)
# ─────────────────────────────────────────────────────────────────────────────


def _prompt(pos: int) -> str:
    return f"  pos={pos:4d} pas | entrer steps (+ouv / -fer) ou q : "


def main() -> None:
    print("=" * 54)
    print("  TEST VIC — pilotage manuel")
    print("=" * 54)
    print(f"  Vitesse : {VIC_SPEED_SPS} sps")
    print("  +N = ouverture   -N = fermeture   q = quitter\n")

    gpio_handle.init()

    with I2CBus() as bus:
        io = IOBoard(bus)
        io.init()

        lcd = LCD2004(bus)
        lcd.init()
        lcd.clear()
        lcd.write_centered(1, "TEST VIC MANUEL")
        lcd.write_centered(2, f"{VIC_SPEED_SPS:.0f} sps")

        with MotorController(io) as motors:
            pos = 0   # position courante (inconnue, supposée 0)

            try:
                while True:
                    try:
                        raw = input(_prompt(pos)).strip()
                    except EOFError:
                        break

                    if raw.lower() == "q":
                        break

                    if raw == "" or raw == "0":
                        print(f"  → position actuelle : {pos} pas")
                        continue

                    try:
                        delta = int(raw)
                    except ValueError:
                        print("  ✗ valeur invalide — entrer un entier signé ou q")
                        continue

                    if delta == 0:
                        print(f"  → position actuelle : {pos} pas")
                        continue

                    direction = "ouverture" if delta > 0 else "fermeture"
                    steps     = abs(delta)

                    print(f"  → {direction}  {steps} pas...", end="", flush=True)
                    lcd.write(3, f"{direction:<12} {steps:4d} pas  ")
                    lcd.write(4, f"pos avant : {pos:4d} pas  ")

                    t0 = time.monotonic()
                    motors.move_steps("VIC", steps, direction, VIC_SPEED_SPS)
                    dt = time.monotonic() - t0

                    pos += delta
                    print(f"  OK ({dt:.1f}s)  pos={pos} pas")
                    lcd.write(3, f"OK {dt:.1f}s               ")
                    lcd.write(4, f"pos : {pos:4d} pas         ")

            except KeyboardInterrupt:
                print("\n  Arrêté par l'utilisateur.")
            finally:
                motors.disable_all_drivers()

        lcd.clear()
        lcd.write_centered(1, "TEST VIC")
        lcd.write_centered(2, "Termine")
        lcd.write_centered(3, f"pos finale : {pos} pas")

    gpio_handle.close()
    print(f"\n  Position finale : {pos} pas")
    print("=== FIN TEST ===")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  Arrêté par l'utilisateur.")
        gpio_handle.close()
