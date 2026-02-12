#!/usr/bin/env python3
# tests/test_relays_critical.py

import time

from core.logging_setup import setup_logging
from config.config_loader import load_config

from libs.relays_critical import CriticalRelays


def main():
    cfg = load_config("config/config.yaml")
    log = setup_logging(cfg.get_str("logging.dir", "/var/log/machine_ctrl"),
                        level=cfg.get_str("logging.level", "INFO"))

    pin_air = cfg.get_int("gpio.relays.air", 16)
    pin_pump = cfg.get_int("gpio.relays.pump", 20)

    relays = CriticalRelays(
        pin_air=pin_air,
        pin_pump=pin_pump,
        active_high_air=True,
        active_high_pump=True,
    )

    log.info("Test relais critiques (air=%d, pump=%d). Ctrl+C pour quitter.", pin_air, pin_pump)

    try:
        relays.all_off()
        time.sleep(0.5)

        log.info("POMPE: pulse 0.5s")
        relays.pump(0.5)
        time.sleep(1.0)

        log.info("AIR: ON 2s")
        relays.air_on()
        time.sleep(2.0)

        log.info("AIR: OFF")
        relays.air_off()
        time.sleep(0.5)

        log.info("Séquence répétée x3: pump(0.3s) + air(0.5s)")
        for _ in range(3):
            relays.pump(0.3)
            time.sleep(0.6)
            relays.air(0.5)  # pulse 0.5s si ton API le supporte
            time.sleep(1.0)

    except KeyboardInterrupt:
        pass
    finally:
        try:
            relays.all_off()
        except Exception:
            pass
        try:
            relays.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    main()
