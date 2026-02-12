#!/usr/bin/env python3
# tests/test_flowmeter.py

import time

from core.logging_setup import setup_logging
from config.config_loader import load_config

from libs.flowmeter_yfdn50 import FlowMeterYFDN50, FlowMeterConfig


def main():
    cfg = load_config("config/config.yaml")
    log = setup_logging(cfg.get_str("logging.dir", "/var/log/machine_ctrl"),
                        level=cfg.get_str("logging.level", "INFO"))

    fm_cfg = FlowMeterConfig(
        gpio_bcm=cfg.get_int("gpio.flowmeter", 21),
        pulses_per_liter=cfg.get_float("flowmeter.pulses_per_liter", 12.0),
        sample_period_s=cfg.get_float("flowmeter.sample_period_s", 1.0),
        edge=cfg.get_str("flowmeter.edge", "FALLING"),
    )

    fm = FlowMeterYFDN50(cfg=fm_cfg)
    fm.start()
    log.info("Flowmeter start GPIO%d edge=%s K=%.3f pulses/L",
             fm_cfg.gpio_bcm, fm_cfg.edge, fm_cfg.pulses_per_liter)

    try:
        while True:
            flow_l_min = fm.get_flow_l_min()
            total_l = fm.get_total_liters()
            pulses = fm.get_total_pulses()
            log.info("Debit=%7.1f L/min | Total=%8.2f L | Pulses=%d", flow_l_min, total_l, pulses)
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            fm.stop()
        except Exception:
            pass
        try:
            fm.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    main()
