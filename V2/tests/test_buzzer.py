#!/usr/bin/env python3
# tests/test_buzzer.py

import time

from core.logging_setup import setup_logging
from config.config_loader import load_config

from hw.buzzer import Buzzer, BuzzerConfig


def main():
    cfg = load_config("config/config.yaml")
    log = setup_logging(cfg.get_str("logging.dir", "/var/log/machine_ctrl"),
                        level=cfg.get_str("logging.level", "INFO"))

    buz = Buzzer(BuzzerConfig(gpio_bcm=cfg.get_int("gpio.buzzer", 26)))
    log.info("Test buzzer GPIO%d", cfg.get_int("gpio.buzzer", 26))

    try:
        log.info("Bip court 2kHz")
        buz.beep(0.15, 2000.0)
        time.sleep(0.3)

        log.info("Pattern (3 bips)")
        buz.pattern([(0.08, 2000.0), (0.08, 2200.0), (0.08, 1800.0)], pause_s=0.08)
        time.sleep(0.5)

        log.info("Balayage fréquence 500->3000 Hz")
        for f in [500, 800, 1200, 1600, 2000, 2400, 2800, 3000]:
            log.info("freq=%d Hz", f)
            buz.beep(0.12, f)
            time.sleep(0.15)

    except KeyboardInterrupt:
        pass
    finally:
        try:
            buz.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    main()
