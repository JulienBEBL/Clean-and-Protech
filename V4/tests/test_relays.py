"""
test_relays.py — Test hardware relais POMPE et AIR

Séquence :
    1. POMPE ON puis OFF
    2. AIR ON puis OFF (manuel, durée fixe)
    3. AIR ON avec timer automatique via tick()
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import libs.gpio_handle as gpio_handle
from libs.relays import Relays


def main() -> None:
    gpio_handle.init()

    with Relays() as r:

        # --- 1. POMPE ON / OFF ---
        print("Test 1 : POMPE ON")
        r.set_pompe_on()
        print(f"  pompe_is_on = {r.pompe_is_on}")
        time.sleep(1.0)

        r.set_pompe_off()
        print(f"  POMPE OFF — pompe_is_on = {r.pompe_is_on}")
        time.sleep(0.5)

        # --- 2. AIR ON / OFF manuel ---
        print("Test 2 : AIR ON (manuel) 1s puis OFF")
        r.set_air_on()
        print(f"  air_is_on = {r.air_is_on}")
        time.sleep(1.0)

        r.set_air_off()
        print(f"  AIR OFF — air_is_on = {r.air_is_on}")
        time.sleep(0.5)

        # --- 3. AIR ON avec timer automatique (tick) ---
        print("Test 3 : AIR ON timer 3s (auto-extinction via tick)")
        r.set_air_on(time_s=3.0)
        t0 = time.monotonic()
        while time.monotonic() - t0 < 4.0:
            r.tick()
            print(f"  t={time.monotonic()-t0:.1f}s | air_is_on={r.air_is_on}")
            time.sleep(0.5)

    gpio_handle.close()
    print("Test relays terminé.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nArrêté par l'utilisateur.")
        gpio_handle.close()
