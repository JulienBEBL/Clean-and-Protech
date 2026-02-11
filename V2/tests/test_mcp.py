# tests/test_mcp.py
from __future__ import annotations

import time

from hal.i2c_bus import I2CBus, I2CConfig
from hw.mcp_hub import MCPHub, McpAddressing, McpPin


def main() -> None:
    bus = I2CBus(I2CConfig(bus=1))
    mcp = MCPHub(bus, McpAddressing(mcp1=0x24, mcp2=0x25, mcp3=0x26))

    print("Init MCP...")
    mcp.init_all()

    print("Test LED1 (MCP1 A2) blink 5 fois")
    led1 = McpPin("mcp1", "A", 2)
    for _ in range(5):
        mcp.write_pin(led1, 1)
        time.sleep(0.2)
        mcp.write_pin(led1, 0)
        time.sleep(0.2)

    print("Test motor1 ENA enable 1s puis disable")
    mcp.motor_set_enable(1, True)
    time.sleep(1.0)
    mcp.motor_set_enable(1, False)

    bus.close()
    print("OK")


if __name__ == "__main__":
    main()
