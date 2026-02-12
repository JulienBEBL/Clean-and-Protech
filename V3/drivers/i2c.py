# drivers/i2c.py
"""
Ultra-simple, robust I2C helper based on smbus2.

- Bus: /dev/i2c-<bus>
- Retries on transient failures
- Minimal API: read/write u8 + read/write blocks
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable, List, Optional

from smbus2 import SMBus, i2c_msg


class I2cError(RuntimeError):
    """Raised for I2C-related errors."""


@dataclass(frozen=True)
class I2cConfig:
    bus: int = 1
    retries: int = 2
    retry_delay_s: float = 0.010  # 10ms


class I2C:
    """
    Simple I2C wrapper.

    Usage:
        i2c = I2C(I2cConfig(bus=1, retries=2, retry_delay_s=0.01))
        i2c.write_u8(0x24, 0x00, 0xFF)
        val = i2c.read_u8(0x24, 0x12)
        i2c.close()
    """

    def __init__(self, cfg: Optional[I2cConfig] = None) -> None:
        self.cfg = cfg or I2cConfig()
        self._bus: Optional[SMBus] = None

        try:
            self._bus = SMBus(self.cfg.bus)
        except Exception as e:
            raise I2cError(f"Failed to open /dev/i2c-{self.cfg.bus}: {e}") from e

    def close(self) -> None:
        if self._bus is None:
            return
        try:
            self._bus.close()
        finally:
            self._bus = None

    def __enter__(self) -> "I2C":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # --------- basic ops ---------

    def write_u8(self, addr: int, reg: int, value: int) -> None:
        """Write one byte to a device register."""
        self._check_byte(reg, "reg")
        self._check_byte(value, "value")
        self._with_retries(f"write_u8 addr=0x{addr:02X} reg=0x{reg:02X}")(
            lambda: self._bus_write_byte_data(addr, reg, value)
        )

    def read_u8(self, addr: int, reg: int) -> int:
        """Read one byte from a device register."""
        self._check_byte(reg, "reg")
        return int(
            self._with_retries(f"read_u8 addr=0x{addr:02X} reg=0x{reg:02X}")(
                lambda: self._bus_read_byte_data(addr, reg)
            )
        )

    def write_block(self, addr: int, reg: int, data: bytes | bytearray | Iterable[int]) -> None:
        """
        Write a block starting at register address.

        Note: smbus2's write_i2c_block_data uses a length prefix; for max compatibility
        we send raw bytes with i2c_msg (reg + data).
        """
        self._check_byte(reg, "reg")
        payload = bytes([reg]) + bytes(self._coerce_bytes(data))
        self._with_retries(f"write_block addr=0x{addr:02X} reg=0x{reg:02X} len={len(payload)-1}")(
            lambda: self._bus_i2c_rdwr_write(addr, payload)
        )

    def read_block(self, addr: int, reg: int, length: int) -> bytes:
        """
        Read a block from a starting register address.

        Implemented as: write reg pointer, then read N bytes.
        """
        self._check_byte(reg, "reg")
        if length <= 0:
            raise I2cError(f"Invalid length: {length} (must be > 0)")
        if length > 1024:
            raise I2cError(f"Invalid length: {length} (too large)")

        def op() -> bytes:
            self._bus_i2c_rdwr_write(addr, bytes([reg]))
            return self._bus_i2c_rdwr_read(addr, length)

        return bytes(self._with_retries(f"read_block addr=0x{addr:02X} reg=0x{reg:02X} len={length}")(op))

    # --------- internal helpers ---------

    def _ensure_open(self) -> SMBus:
        if self._bus is None:
            raise I2cError("I2C is closed")
        return self._bus

    def _bus_write_byte_data(self, addr: int, reg: int, value: int) -> None:
        bus = self._ensure_open()
        bus.write_byte_data(addr, reg, value)

    def _bus_read_byte_data(self, addr: int, reg: int) -> int:
        bus = self._ensure_open()
        return bus.read_byte_data(addr, reg)

    def _bus_i2c_rdwr_write(self, addr: int, payload: bytes) -> None:
        bus = self._ensure_open()
        msg = i2c_msg.write(addr, payload)
        bus.i2c_rdwr(msg)

    def _bus_i2c_rdwr_read(self, addr: int, length: int) -> bytes:
        bus = self._ensure_open()
        msg = i2c_msg.read(addr, length)
        bus.i2c_rdwr(msg)
        return bytes(msg)

    def _with_retries(self, label: str):
        """
        Decorator-like helper.

        Retries = cfg.retries (meaning: additional attempts after the first fail).
        Total attempts = 1 + retries.
        """
        attempts = 1 + max(0, int(self.cfg.retries))
        delay = float(self.cfg.retry_delay_s)

        def runner(fn):
            last_exc: Optional[Exception] = None
            for i in range(attempts):
                try:
                    return fn()
                except Exception as e:
                    last_exc = e
                    if i < attempts - 1:
                        time.sleep(delay)
                        continue
                    break
            raise I2cError(f"I2C operation failed ({label}) after {attempts} attempts: {last_exc}") from last_exc

        return runner

    @staticmethod
    def _check_byte(v: int, name: str) -> None:
        if not isinstance(v, int):
            raise I2cError(f"{name} must be int, got {type(v)}")
        if v < 0 or v > 0xFF:
            raise I2cError(f"{name} out of range (0..255): {v}")

    @staticmethod
    def _coerce_bytes(data: bytes | bytearray | Iterable[int]) -> List[int]:
        if isinstance(data, (bytes, bytearray)):
            return list(data)
        out: List[int] = []
        for b in data:
            if not isinstance(b, int):
                raise I2cError(f"Block data must contain ints, got {type(b)}")
            if b < 0 or b > 0xFF:
                raise I2cError(f"Block data byte out of range (0..255): {b}")
            out.append(b)
        return out
