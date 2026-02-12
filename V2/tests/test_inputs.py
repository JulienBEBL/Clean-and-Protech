#!/usr/bin/env python3
# tests/test_inputs.py

import time

from core.logging_setup import setup_logging
from config.config_loader import load_config

from hal.i2c_bus import I2CBus, I2CConfig, scan_i2c
from hw.mcp_hub import MCPHub, McpAddressing
from hw.inputs import Inputs


def main():
    cfg = load_config("config/config.yaml")
    log = setup_logging(cfg.get_str("logging.dir", "/var/log/machine_ctrl"),
                        level=cfg.get_str("logging.level", "INFO"))

    bus = I2CBus(I2CConfig(bus=cfg.get_int("i2c.bus", 1), retries=3, retry_delay_s=0.01))
    found = scan_i2c(bus)
    log.info("I2C détectés: %s", [hex(a) for a in found])

    addrs = McpAddressing(
        mcp1=int(cfg.get("i2c.mcp1", 0x24)),
        mcp2=int(cfg.get("i2c.mcp2", 0x25)),
        mcp3=int(cfg.get("i2c.mcp3", 0x26)),
    )
    mcp = MCPHub(bus, addrs)
    mcp.init_all()
    log.info("MCPHub OK")

    inputs = Inputs(
        mcp=mcp,
        poll_hz=cfg.get_int("inputs.poll_hz", 100),
        debounce_ms=cfg.get_int("inputs.debounce_ms", 30),
        active_low_buttons=True,
        active_low_selectors=True,
    )
    inputs.start()
    log.info("Inputs démarré. Ctrl+C pour quitter.")

    try:
        while True:
            evs = inputs.get_events()
            for ev in evs:
                log.info("EVENT: %s value=%s", ev.type, ev.value)
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            inputs.stop()
        except Exception:
            pass
        try:
            bus.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
