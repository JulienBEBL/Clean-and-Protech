# tests/test_motor_group_open_close.py
from __future__ import annotations

from hal.gpio_lgpio import GpioLgpio
from hal.i2c_bus import I2CBus, I2CConfig
from hw.mcp_hub import MCPHub, McpAddressing
from driver.motors import Motors, MotorsConfig


def main() -> None:
    step_pins = {
        "M1": 17, "M2": 27, "M3": 22, "M4": 5,
        "M5": 18, "M6": 23, "M7": 24, "M8": 25,
    }

    gpio = GpioLgpio(chip=0)
    bus = I2CBus(I2CConfig(bus=1))
    mcp = MCPHub(bus, McpAddressing(mcp1=0x24, mcp2=0x25, mcp3=0x26))
    mcp.init_all()

    motors = Motors(gpio=gpio, mcp=mcp, step_pins=step_pins, cfg=MotorsConfig(microsteps_per_rev=3200))

    print("OUVERTURE groupe: 10 tours, 50 rpm, accel 100 rpm/s")
    motors.open_all(turns=10.0, max_rpm=50.0, accel_rpm_s=100.0)
    motors.wait_all(timeout_s=120.0)

    print("FERMETURE groupe: 10 tours, 30 rpm, accel 60 rpm/s")
    motors.close_all(turns=10.0, max_rpm=30.0, accel_rpm_s=60.0)
    motors.wait_all(timeout_s=120.0)

    motors.disable_all()
    bus.close()
    gpio.close()
    print("OK")


if __name__ == "__main__":
    main()
