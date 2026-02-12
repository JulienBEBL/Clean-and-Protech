#!/usr/bin/env python3
# tests/test_leds.py

import time

from core.logging_setup import setup_logging
from config.config_loader import load_config

from hal.i2c_bus import I2CBus, I2CConfig
from hw.mcp_hub import MCPHub, McpAddressing
from hw.leds import ProgramLeds


def main():
    cfg = load_config("config/config.yaml")
    log = setup_logging(cfg.get_str("logging.dir", "/var/log/machine_ctrl"),
                        level=cfg.get_str("logging.level", "INFO"))

    bus = I2CBus(I2CConfig(bus=cfg.get_int("i2c.bus", 1), retries=3, retry_delay_s=0.01))
    addrs = McpAddressing(
        mcp1=int(cfg.get("i2c.mcp1", 0x24)),
        mcp2=int(cfg.get("i2c.mcp2", 0x25)),
        mcp3=int(cfg.get("i2c.mcp3", 0x26)),
    )
    mcp = MCPHub(bus, addrs)
    mcp.init_all()

    leds = ProgramLeds(mcp, active_high=True)
    leds.all_off()

    log.info("Test LEDs: séquence LED1..LED6")
    try:
        for _ in range(3):
            for i in range(1, 7):
                leds.show_active_program(i)
                log.info("LED %d ON", i)
                time.sleep(0.3)
            leds.show_active_program(None)
            time.sleep(0.3)

        log.info("Toutes ON")
        for i in range(1, 7):
            leds.set_prog_led(i, True)
        time.sleep(1.0)

        log.info("Toutes OFF")
        leds.all_off()
        time.sleep(0.5)

    finally:
        try:
            leds.all_off()
        except Exception:
            pass
        try:
            bus.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
