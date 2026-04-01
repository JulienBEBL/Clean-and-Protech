"""
test_io_board.py — Test hardware IOBoard (MCP23017 x3)

Affiche en temps réel sur le LCD et la console :
    - État des 6 boutons PRG  (actif bas → 1 si appuyé)
    - État des 6 LEDs         (miroir des boutons PRG)
    - Sélecteur VIC (1..5)
    - Sélecteur AIR (1..4)

Comportement :
    - Chaque LED suit son bouton PRG correspondant (PRG1 → LED1, etc.)
    - L'affichage LCD se met à jour à ~10 Hz

Layout LCD (20 colonnes) :
    Ligne 1 : PRG: -  -  3  -  -  -
    Ligne 2 : LED: -  -  *  -  -  -
    Ligne 3 : VIC: -  2  -  -  -
    Ligne 4 : AIR: -  -  -  4

Ctrl+C pour quitter proprement.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from libs.i2c_bus import I2CBus
from libs.io_board import IOBoard
from libs.lcd2004 import LCD2004

LOOP_HZ   = 10          # fréquence de rafraîchissement
LOOP_S    = 1 / LOOP_HZ


# ── helpers affichage ─────────────────────────────────────────────────────────

def fmt_prg(io: IOBoard) -> str:
    """Ligne PRG : affiche le numéro si appuyé, '-' sinon. Ex: '-  -  3  -  -  -'"""
    parts = [str(i) if io.read_btn_active(i) else "-" for i in range(1, 7)]
    return "PRG: " + "  ".join(parts)


def fmt_led(io: IOBoard) -> str:
    """Ligne LED : affiche '*' si allumée, '-' sinon."""
    # on relit OLAT via l'état interne du cache mcp1_olat_a
    parts = []
    for i in range(1, 7):
        pin = IOBoard._led_pin(i)
        state = (io._mcp1_olat_a >> pin) & 1
        parts.append("*" if state else "-")
    return "LED: " + "  ".join(parts)


def fmt_vic(io: IOBoard) -> str:
    """Ligne VIC : affiche le numéro si sélectionné, '-' sinon."""
    parts = [str(i) if io.read_vic_active(i) else "-" for i in range(1, 6)]
    return "VIC: " + "  ".join(parts)


def fmt_air(io: IOBoard) -> str:
    """
    Ligne AIR : affiche le mode actif.
        0 = pas d'injection
        1 = faible
        2 = moyen
        3 = continu
    """
    labels = {0: "0:aucun", 1: "1:faible", 2: "2:moyen", 3: "3:continu"}
    mode = io.read_air_mode()
    return f"AIR: {labels[mode]}"


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    with I2CBus() as bus:
        io = IOBoard(bus)
        io.init()

        lcd = LCD2004(bus)
        lcd.init()
        lcd.clear()
        lcd.write_centered(1, "IOBoard TEST")
        lcd.write_centered(2, "Appuie sur PRG")
        time.sleep(1.5)
        lcd.clear()

        print("IOBoard TEST — Ctrl+C pour arrêter\n")

        try:
            while True:
                # --- lecture boutons et mise à jour LEDs ---
                for i in range(1, 7):
                    state = io.read_btn_active(i)
                    io.set_led(i, state)

                # --- formatage lignes ---
                l1 = fmt_prg(io)
                l2 = fmt_led(io)
                l3 = fmt_vic(io)
                l4 = fmt_air(io)

                # --- LCD ---
                lcd.write(1, l1)
                lcd.write(2, l2)
                lcd.write(3, l3)
                lcd.write(4, l4)

                # --- console ---
                print(f"\r{l1} | {l3} | {l4}", end="", flush=True)

                time.sleep(LOOP_S)

        except KeyboardInterrupt:
            print("\nArrêté par l'utilisateur.")
        finally:
            # état sûr
            for i in range(1, 7):
                io.set_led(i, 0)
            lcd.clear()
            lcd.write_centered(1, "Test termine")


if __name__ == "__main__":
    main()
