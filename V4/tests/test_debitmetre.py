"""
test_debitmetre.py — Test hardware débitmètre à impulsions

Affiche en continu :
    - débit instantané (L/min) sur fenêtre glissante
    - volume cumulé (L)
    - nombre total d'impulsions

Ctrl+C pour arrêter.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import libs.gpio_handle as gpio_handle
from libs.debitmetre import FlowMeter

WINDOW_S = 1.0   # fenêtre débit instantané (secondes)
LOOP_S   = 1.0   # intervalle d'affichage (secondes)


def main() -> None:
    gpio_handle.init()

    fm = FlowMeter()
    fm.open()

    print(f"Débitmètre TEST — K={fm.pulses_per_liter} p/L | fenêtre={WINDOW_S}s (Ctrl+C pour arrêter)")
    t0 = time.monotonic()

    try:
        while True:
            flow   = fm.flow_lpm(WINDOW_S)
            total  = fm.total_liters()
            pulses = fm.total_pulses()
            dt     = time.monotonic() - t0

            print(f"t={dt:6.1f}s | débit={flow:7.2f} L/min | volume={total:8.3f} L | impulsions={pulses}")

            time.sleep(LOOP_S)

    except KeyboardInterrupt:
        print("\nArrêté par l'utilisateur.")
    finally:
        fm.close()
        gpio_handle.close()


if __name__ == "__main__":
    main()
