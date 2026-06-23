"""
test_vic.py — Pilotage manuel de la VIC pas à pas.

À chaque invite, entrer un nombre de pas signé :
    +N  ou  N   → ouverture (N pas vers RETOUR)
    -N          → fermeture (N pas vers DEPART)
    h           → homing complet (DEPART→RETOUR×3→NEUTRE)
    0   ou rien → aucun mouvement (affiche la position courante)
    q           → quitter

Exemple :
    > 10      →  10 pas ouverture
    > -10     →  10 pas fermeture
    > 50      →  50 pas ouverture
    > h       →  homing
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
from libs.vic import VICController

# ── Paramètre modifiable ──────────────────────────────────────────────────────
VIC_SPEED_SPS: float = config.VIC_SPEED_SPS   # vitesse (sps)
# ─────────────────────────────────────────────────────────────────────────────


def _prompt(pos: int) -> str:
    return f"  pos={pos:4d} pas | +ouv / -fer / h=homing / q=quitter : "


def main() -> None:
    print("=" * 56)
    print("  TEST VIC V5 — pilotage manuel")
    print("=" * 56)
    print(f"  Vitesse : {VIC_SPEED_SPS} sps")
    print(f"  DEPART={config.VIC_DEPART_STEPS}p  NEUTRE={config.VIC_NEUTRE_STEPS}p  RETOUR={config.VIC_RETOUR_STEPS}p")
    print("  +N = ouverture   -N = fermeture   h = homing   q = quitter\n")

    gpio_handle.init()

    with I2CBus() as bus:
        io = IOBoard(bus)
        io.init()

        lcd = LCD2004(bus)
        lcd.init()
        lcd.clear()
        lcd.write_centered(1, "TEST VIC MANUEL")
        lcd.write_centered(2, f"{VIC_SPEED_SPS:.0f} sps")

        vic = VICController()
        vic.open()

        try:
            while True:
                pos = vic.position
                try:
                    raw = input(_prompt(pos)).strip()
                except EOFError:
                    break

                if raw.lower() == "q":
                    break

                if raw.lower() == "h":
                    print("  → homing...", end="", flush=True)
                    lcd.write(3, "Homing...           ")
                    t0 = time.monotonic()
                    vic.homing()
                    dt = time.monotonic() - t0
                    print(f"  OK ({dt:.1f}s)  pos={vic.position} pas")
                    lcd.write(3, f"Homing OK {dt:.1f}s       ")
                    lcd.write(4, f"pos : {vic.position:4d} pas       ")
                    continue

                if raw == "" or raw == "0":
                    print(f"  → position actuelle : {pos} pas")
                    continue

                try:
                    delta = int(raw)
                except ValueError:
                    print("  ✗ valeur invalide — entrer un entier signé, h ou q")
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
                vic.move_relative(delta)
                dt = time.monotonic() - t0

                print(f"  OK ({dt:.1f}s)  pos={vic.position} pas")
                lcd.write(3, f"OK {dt:.1f}s               ")
                lcd.write(4, f"pos : {vic.position:4d} pas         ")

        except KeyboardInterrupt:
            print("\n  Arrêté par l'utilisateur.")
        finally:
            vic.disable()
            vic.close()

        lcd.clear()
        lcd.write_centered(1, "TEST VIC")
        lcd.write_centered(2, "Termine")
        lcd.write_centered(3, f"pos : {vic.position} pas")

    gpio_handle.close()
    print(f"\n  Position finale (RAM) : {vic.position} pas")
    print("=== FIN TEST ===")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  Arrêté par l'utilisateur.")
        gpio_handle.close()
