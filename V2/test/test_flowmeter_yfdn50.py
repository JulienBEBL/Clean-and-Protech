#!/usr/bin/env python3
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "libs"))
sys.path.append(LIB_DIR)

from flowmeter_yfdn50 import FlowMeterYFDN50, FlowMeterConfig


def main():
    cfg = FlowMeterConfig(
        gpio_bcm=21,
        pulses_per_liter=12.0,   # valeur par défaut (f=0.2*Q => 12 pulses/L)
        sample_period_s=1.0,     # update débit toutes les 1s
        bouncetime_ms=2,
        # edge: si tu constates 0 pulses, essaye GPIO.RISING
        # edge=GPIO.FALLING,
    )

    fm = FlowMeterYFDN50(cfg=cfg, warnings=False)

    try:
        fm.start()
        fm.reset_total()

        print("Débitmètre: START. Appuie Ctrl+C pour arrêter.")
        print("Affichage: flow(L/min), total(L), pulses")

        t0 = time.time()
        while True:
            flow = fm.get_flow_l_min()
            total_l = fm.get_total_liters()
            pulses = fm.get_total_pulses()

            elapsed = time.time() - t0
            print(f"t={elapsed:6.1f}s | flow={flow:8.2f} L/min | total={total_l:8.3f} L | pulses={pulses}")
            time.sleep(1.0)

    except KeyboardInterrupt:
        pass
    finally:
        # stop() ne casse pas les autres libs GPIO
        fm.stop()
        print("Débitmètre: STOP.")


if __name__ == "__main__":
    main()
