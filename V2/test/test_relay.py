#!/usr/bin/env python3
# --------------------------------------
# test/test_relays_critical.py
# Test pour libs/relays_critical.py
#
# Arborescence:
# project/
#   libs/relays_critical.py
#   test/test_relays_critical.py
# --------------------------------------

import os
import sys
import time

# Ajout de ../libs au PYTHONPATH
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "libs"))
sys.path.append(LIB_DIR)

from relays_critical import CriticalRelays


def pause(s: float):
    time.sleep(s)


def main():
    # Si tes relais sont actifs à l'état bas:
    # r = CriticalRelays(active_high_air=False, active_high_pump=False)
    r = CriticalRelays()

    try:
        # ---- Etat sûr ----
        print("Init: all_off()")
        r.all_off()
        pause(1.0)

        # ---- AIR: pulses ----
        print("AIR: pulse 2.0s")
        r.air(2.0)
        pause(3.0)

        print("AIR: pulse 4.0s")
        r.air(4.0)
        pause(5.0)

        # ---- AIR: ON continu + OFF ----
        print("AIR: ON continu 3s (air_on)")
        r.air_on()
        pause(3.0)

        print("AIR: OFF (air_off)")
        r.air_off()
        pause(1.0)

        # Variante ON continu via air(None)
        print("AIR: ON continu 2s (air(None))")
        r.air(None)
        pause(2.0)
        print("AIR: OFF")
        r.air_off()
        pause(1.0)

        # ---- POMPE: pulses ----
        print("POMPE: pulse 0.5s")
        r.pump(0.5)
        pause(1.5)

        print("POMPE: pulse 0.5s x5 (1s interval)")
        for i in range(5):
            print(f"  pulse {i+1}/5")
            r.pump(0.5)
            pause(1.0)

        # ---- AIR + POMPE combiné ----
        print("AIR ON + POMPE pulse")
        r.air_on()
        pause(0.3)
        r.pump(0.5)
        pause(1.5)
        r.air_off()
        pause(1.0)

        # ---- Fin ----
        print("Fin: all_off()")
        r.all_off()
        pause(1.0)

    finally:
        print("cleanup()")
        r.cleanup()


if __name__ == "__main__":
    main()
