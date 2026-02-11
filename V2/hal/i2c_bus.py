# hal/i2c_bus.py
from __future__ import annotations

import time
from dataclasses import dataclass
from smbus2 import SMBus


@dataclass(frozen=True)
class I2CConfig:
    bus: int = 1
    retries: int = 3
    retry_delay_s: float = 0.01  # 10 ms


class I2CBus:
    def __init__(self, cfg: I2CConfig):
        self.cfg = cfg
        self.bus = SMBus(cfg.bus)

    def close(self) -> None:
        try:
            self.bus.close()
        except Exception:
            pass

    def read_byte_data(self, addr: int, reg: int) -> int:
        last_exc = None
        for _ in range(self.cfg.retries):
            try:
                return self.bus.read_byte_data(addr, reg)
            except OSError as e:
                last_exc = e
                time.sleep(self.cfg.retry_delay_s)
        raise OSError(f"I2C read_byte_data échoué addr=0x{addr:02X} reg=0x{reg:02X}") from last_exc

    def write_byte_data(self, addr: int, reg: int, value: int) -> None:
        last_exc = None
        for _ in range(self.cfg.retries):
            try:
                self.bus.write_byte_data(addr, reg, value & 0xFF)
                return
            except OSError as e:
                last_exc = e
                time.sleep(self.cfg.retry_delay_s)
        raise OSError(f"I2C write_byte_data échoué addr=0x{addr:02X} reg=0x{reg:02X}") from last_exc

    def write_quick(self, addr: int) -> None:
        last_exc = None
        for _ in range(self.cfg.retries):
            try:
                self.bus.write_quick(addr)
                return
            except OSError as e:
                last_exc = e
                time.sleep(self.cfg.retry_delay_s)
        raise OSError(f"I2C write_quick échoué addr=0x{addr:02X}") from last_exc


def scan_i2c(bus: I2CBus) -> list[int]:
    found: list[int] = []
    for addr in range(0x03, 0x78):
        try:
            bus.write_quick(addr)
            found.append(addr)
        except OSError:
            pass
    return found
