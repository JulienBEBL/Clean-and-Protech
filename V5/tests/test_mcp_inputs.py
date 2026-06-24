"""
test_mcp_inputs.py — Lecture en temps reel des entrees MCP V5.

Affiche en continu a 10 Hz :
    Boutons PRG 1..5  — MCP1 Port B (B0..B4), actif bas, pull-up interne
    Selecteur VIC     — MCP2 Port B (B0..B2), 3 positions (DEPART/NEUTRE/RETOUR)
    Selecteur AIR     — MCP2 Port A (A7..A5), 4 modes (OFF/faible/moyen/continu)

Le terminal est mis a jour en place (pas de defilement).
Les LEDs PRG s'allument en miroir du bouton enfonce.
Ctrl+C pour quitter.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from libs.i2c_bus import I2CBus
from libs.io_board import IOBoard

_VIC_LABELS: dict[int, str] = {
    0: "aucune",
    1: "DEPART  (0 pas)",
    2: "NEUTRE  (50 pas)",
    3: "RETOUR  (100 pas)",
}
_AIR_LABELS: dict[int, str] = {
    0: "OFF",
    1: "Faible  (2s/2s)",
    2: "Moyen   (4s/2s)",
    3: "Continu (ON permanent)",
}

_LOOP_S      = 0.1   # 10 Hz
_DISPLAY_LINES = 14  # nombre de lignes du bloc d'affichage (pour le retour curseur)


def _btn_bar(btns: list[int]) -> str:
    """Ligne graphique des 5 boutons — bouton enfonce entre crochets."""
    parts = []
    for i, active in enumerate(btns, start=1):
        parts.append(f"[PRG{i}]" if active else f" PRG{i} ")
    return "  " + "  ".join(parts)


def main() -> None:
    print("=" * 54)
    print("  TEST ENTREES MCP — Clean & Protech V5")
    print("=" * 54)
    print(f"  MCP1 : 0x{config.MCP1_ADDR:02X}  (boutons PRG + LEDs)")
    print(f"  MCP2 : 0x{config.MCP2_ADDR:02X}  (selecteur VIC + AIR)")
    print("  Ctrl+C pour quitter\n")
    time.sleep(1.0)

    with I2CBus() as bus:
        io = IOBoard(bus)
        io.init()
        io.set_all_leds(0)

        first = True
        try:
            while True:
                t0 = time.monotonic()

                # ── Lectures MCP ──────────────────────────────────────────
                btns     = [io.read_btn_active(i) for i in range(1, 6)]
                vic_pos  = io.read_vic_selector()
                air_mode = io.read_air_mode()

                btn_pressed = next((i + 1 for i, v in enumerate(btns) if v), 0)

                # ── Miroir LEDs ───────────────────────────────────────────
                for i in range(1, 6):
                    io.set_led(i, btns[i - 1])

                # ── Affichage terminal mis a jour en place ────────────────
                if not first:
                    print(f"\033[{_DISPLAY_LINES}A", end="", flush=True)
                first = False

                print("  ┌─────────────────────────────────────┐")
                print("  │         BOUTONS PRG (1..5)          │")
                print(f"  │  {_btn_bar(btns):<35}│")
                print(f"  │  Actif : {f'PRG{btn_pressed}':<28}│")
                print("  ├─────────────────────────────────────┤")
                print("  │         SELECTEUR VIC               │")
                print(f"  │  Pos : {vic_pos}  {_VIC_LABELS.get(vic_pos, '?'):<30}│")
                print("  ├─────────────────────────────────────┤")
                print("  │         SELECTEUR AIR               │")
                print(f"  │  Mode: {air_mode}  {_AIR_LABELS.get(air_mode, '?'):<30}│")
                print("  └─────────────────────────────────────┘")
                print(f"  [10 Hz — MCP1:0x{config.MCP1_ADDR:02X} MCP2:0x{config.MCP2_ADDR:02X}]  ", end="\n")
                print("  Ctrl+C pour quitter                    ", end="\n", flush=True)

                remaining = _LOOP_S - (time.monotonic() - t0)
                if remaining > 0:
                    time.sleep(remaining)

        except KeyboardInterrupt:
            print("\n  Arret (Ctrl+C)")
        finally:
            io.set_all_leds(0)

    print("=== FIN TEST ===")


if __name__ == "__main__":
    main()
