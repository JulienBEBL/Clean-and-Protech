"""
test_buzzer.py — Test hardware buzzer (SEA-1295Y-0520-42Ω-38P6.5)

Séquence :
    1. Bips courts (10x) — vérifie la répétition et le gap
    2. Sonnerie de démarrage (~5s)
    3. Ton continu 2s
    4. Balayage fréquentiel (500 → 4500 Hz) — vérifie la plage utile
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import libs.gpio_handle as gpio_handle
from libs.buzzer import Buzzer


def main() -> None:
    gpio_handle.init()

    with Buzzer() as bz:

        # --- 1. Bips courts ---
        print("Test 1 : bips courts (10x)")
        bz.beep(time_ms=150, power_pct=90, repeat=10, freq_hz=2000, gap_ms=100)
        time.sleep(0.5)

        # --- 2. Sonnerie de démarrage ---
        print("Test 2 : sonnerie démarrage (~5s)")
        bz.ringtone_startup()
        time.sleep(0.5)

        # --- 3. Ton continu 2s ---
        print("Test 3 : ton continu 2s")
        bz.on(freq_hz=2000, power_pct=70)
        time.sleep(2.0)
        bz.off()
        time.sleep(0.5)

        # --- 4. Balayage fréquentiel ---
        print("Test 4 : balayage fréquentiel (500 → 4500 Hz)")
        steps = [500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500]
        for freq in steps:
            print(f"  {freq} Hz")
            bz.beep(time_ms=400, power_pct=70, repeat=1, freq_hz=freq, gap_ms=100)

    gpio_handle.close()
    print("Test buzzer terminé.")


if __name__ == "__main__":
    main()
