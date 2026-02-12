# drivers/mcp23017.py
"""
Ultra-simple MCP23017 (I2C) driver using BANK=0 register mapping.

- Designed to work with drivers/i2c.py (smbus2 wrapper).
- MCP powered at 3.3V.
- Outputs are considered "active HIGH" (this mainly matters in your higher-level usage).
- Mapping is fixed: you will configure each MCP with fixed pin lists at init.

Key idea:
- You pass the fixed mapping (which pins are inputs/outputs + default output states + pullups)
  when you instantiate the MCP23017 object.
- Driver applies a known state on startup (robust, predictable).

No IRQ support (INTA/INTB not wired).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal, Optional, Sequence

from drivers.i2c import I2C, I2cError

Port = Literal["A", "B"]


class MCPError(RuntimeError):
    """Raised for MCP23017-related errors."""


@dataclass(frozen=True)
class MCP23017FixedMap:
    """
    Fixed mapping/config for one MCP.

    inputs_a/inputs_b: pins configured as inputs (0..7)
    outputs_a/outputs_b: pins configured as outputs (0..7)
    pullups_a/pullups_b: pins with internal pull-ups enabled (inputs only)
    invert_a/invert_b: pins with polarity inversion enabled (inputs only)
    default_high_a/default_high_b: output pins forced HIGH at init
                                 (all other output pins forced LOW)
    """
    inputs_a: Sequence[int] = ()
    inputs_b: Sequence[int] = ()
    outputs_a: Sequence[int] = ()
    outputs_b: Sequence[int] = ()
    pullups_a: Sequence[int] = ()
    pullups_b: Sequence[int] = ()
    invert_a: Sequence[int] = ()
    invert_b: Sequence[int] = ()
    default_high_a: Sequence[int] = ()
    default_high_b: Sequence[int] = ()


@dataclass(frozen=True)
class MCP23017Config:
    address: int  # e.g. 0x24
    sequential: bool = True  # True => IOCON.SEQOP=0 (sequential enabled)
    fixed_map: Optional[MCP23017FixedMap] = None


class MCP23017:
    # BANK=0 register addresses
    IODIRA = 0x00
    IODIRB = 0x01
    IPOLA = 0x02
    IPOLB = 0x03
    IOCON_A = 0x0A
    IOCON_B = 0x0B
    GPPUA = 0x0C
    GPPUB = 0x0D
    GPIOA = 0x12
    GPIOB = 0x13
    OLATA = 0x14
    OLATB = 0x15

    # IOCON bits
    IOCON_SEQOP = 1 << 5  # 1 = sequential disabled, 0 = sequential enabled

    def __init__(self, i2c: I2C, cfg: MCP23017Config) -> None:
        self._i2c = i2c
        self.addr = cfg.address
        self._cfg = cfg

        # cached registers (so write_pin is fast and safe)
        self._iodir_a: int = 0xFF
        self._iodir_b: int = 0xFF
        self._gppu_a: int = 0x00
        self._gppu_b: int = 0x00
        self._ipol_a: int = 0x00
        self._ipol_b: int = 0x00
        self._olat_a: int = 0x00
        self._olat_b: int = 0x00

        self._init_device()

        # Apply fixed mapping if provided (your “mapping fixe”)
        if self._cfg.fixed_map is not None:
            self.apply_fixed_map(self._cfg.fixed_map)

    # ---------------- init ----------------

    def _init_device(self) -> None:
        # Force IOCON BANK=0 and set SEQOP
        iocon = 0x00
        if not self._cfg.sequential:
            iocon |= self.IOCON_SEQOP

        self._write_u8(self.IOCON_A, iocon)
        self._write_u8(self.IOCON_B, iocon)

        # Known safe defaults at boot:
        # - All pins inputs
        # - Pullups off
        # - Polarity normal
        # - Output latches low (if/when pins become outputs)
        self._iodir_a = 0xFF
        self._iodir_b = 0xFF
        self._gppu_a = 0x00
        self._gppu_b = 0x00
        self._ipol_a = 0x00
        self._ipol_b = 0x00
        self._olat_a = 0x00
        self._olat_b = 0x00

        self._write_u8(self.IODIRA, self._iodir_a)
        self._write_u8(self.IODIRB, self._iodir_b)
        self._write_u8(self.GPPUA, self._gppu_a)
        self._write_u8(self.GPPUB, self._gppu_b)
        self._write_u8(self.IPOLA, self._ipol_a)
        self._write_u8(self.IPOLB, self._ipol_b)
        self._write_u8(self.OLATA, self._olat_a)
        self._write_u8(self.OLATB, self._olat_b)

    # ---------------- fixed mapping ----------------

    def apply_fixed_map(self, m: MCP23017FixedMap) -> None:
        """
        Apply a fixed mapping (directions + pullups + input inversion + default outputs).

        This is what you want for "mapping fixe": you define once in config and the
        MCP starts in a known state every boot.
        """
        # Build register bytes from pin lists
        inputs_a = self._pins_to_mask(m.inputs_a)
        inputs_b = self._pins_to_mask(m.inputs_b)
        outputs_a = self._pins_to_mask(m.outputs_a)
        outputs_b = self._pins_to_mask(m.outputs_b)

        # Sanity: a pin should not be both input and output
        if (inputs_a & outputs_a) != 0:
            raise MCPError("PORTA: some pins are both input and output in fixed map")
        if (inputs_b & outputs_b) != 0:
            raise MCPError("PORTB: some pins are both input and output in fixed map")

        # Direction: 1=input, 0=output
        self._iodir_a = inputs_a | (~outputs_a & 0xFF)  # outputs bits -> 0
        self._iodir_b = inputs_b | (~outputs_b & 0xFF)

        # Pullups (only meaningful on inputs, but we don't hard-enforce)
        self._gppu_a = self._pins_to_mask(m.pullups_a)
        self._gppu_b = self._pins_to_mask(m.pullups_b)

        # Input polarity invert
        self._ipol_a = self._pins_to_mask(m.invert_a)
        self._ipol_b = self._pins_to_mask(m.invert_b)

        # Default output latch levels
        # - start from 0
        # - set requested default_high pins to 1
        self._olat_a = self._pins_to_mask(m.default_high_a)
        self._olat_b = self._pins_to_mask(m.default_high_b)

        # Apply in safe order:
        # 1) write latches first (so when switching to output, they drive the intended level)
        # 2) configure pullups/ipol
        # 3) set directions
        self._write_u8(self.OLATA, self._olat_a)
        self._write_u8(self.OLATB, self._olat_b)
        self._write_u8(self.GPPUA, self._gppu_a)
        self._write_u8(self.GPPUB, self._gppu_b)
        self._write_u8(self.IPOLA, self._ipol_a)
        self._write_u8(self.IPOLB, self._ipol_b)
        self._write_u8(self.IODIRA, self._iodir_a)
        self._write_u8(self.IODIRB, self._iodir_b)

    # ---------------- port API ----------------

    def read_port(self, port: Port) -> int:
        """Read current pin levels from GPIO register."""
        return self._read_u8(self.GPIOA if port == "A" else self.GPIOB)

    def write_port(self, port: Port, value: int) -> None:
        """Write full output latch (OLAT) for a port."""
        v = self._check_u8(value, "value")
        if port == "A":
            self._olat_a = v
            self._write_u8(self.OLATA, v)
        else:
            self._olat_b = v
            self._write_u8(self.OLATB, v)

    # ---------------- pin API ----------------

    def read_pin(self, port: Port, pin: int) -> int:
        mask = 1 << self._check_pin(pin)
        v = self.read_port(port)
        return 1 if (v & mask) else 0

    def write_pin(self, port: Port, pin: int, level: int) -> None:
        """
        Set one output pin level via OLAT (read-modify-write using cache).
        """
        lvl = self._check_level(level)
        mask = 1 << self._check_pin(pin)

        if port == "A":
            new = (self._olat_a | mask) if lvl else (self._olat_a & ~mask)
            if new != self._olat_a:
                self._olat_a = new
                self._write_u8(self.OLATA, self._olat_a)
        else:
            new = (self._olat_b | mask) if lvl else (self._olat_b & ~mask)
            if new != self._olat_b:
                self._olat_b = new
                self._write_u8(self.OLATB, self._olat_b)

    def set_pin_mode(self, port: Port, pin: int, is_input: bool) -> None:
        """
        Change direction of one pin.
        1=input, 0=output
        """
        mask = 1 << self._check_pin(pin)
        if port == "A":
            new = (self._iodir_a | mask) if is_input else (self._iodir_a & ~mask)
            if new != self._iodir_a:
                self._iodir_a = new
                self._write_u8(self.IODIRA, self._iodir_a)
        else:
            new = (self._iodir_b | mask) if is_input else (self._iodir_b & ~mask)
            if new != self._iodir_b:
                self._iodir_b = new
                self._write_u8(self.IODIRB, self._iodir_b)

    def set_pullup(self, port: Port, pin: int, enable: bool) -> None:
        mask = 1 << self._check_pin(pin)
        if port == "A":
            new = (self._gppu_a | mask) if enable else (self._gppu_a & ~mask)
            if new != self._gppu_a:
                self._gppu_a = new
                self._write_u8(self.GPPUA, self._gppu_a)
        else:
            new = (self._gppu_b | mask) if enable else (self._gppu_b & ~mask)
            if new != self._gppu_b:
                self._gppu_b = new
                self._write_u8(self.GPPUB, self._gppu_b)

    # ---------------- internal I2C helpers ----------------

    def _write_u8(self, reg: int, value: int) -> None:
        try:
            self._i2c.write_u8(self.addr, reg, value)
        except I2cError as e:
            raise MCPError(
                f"MCP23017 write failed addr=0x{self.addr:02X} reg=0x{reg:02X}: {e}"
            ) from e

    def _read_u8(self, reg: int) -> int:
        try:
            return self._i2c.read_u8(self.addr, reg)
        except I2cError as e:
            raise MCPError(
                f"MCP23017 read failed addr=0x{self.addr:02X} reg=0x{reg:02X}: {e}"
            ) from e

    # ---------------- validation helpers ----------------

    @staticmethod
    def _check_pin(pin: int) -> int:
        if not isinstance(pin, int):
            raise MCPError(f"pin must be int, got {type(pin)}")
        if pin < 0 or pin > 7:
            raise MCPError(f"pin out of range (0..7): {pin}")
        return pin

    @staticmethod
    def _check_level(level: int) -> int:
        if level in (0, 1):
            return level
        if isinstance(level, bool):
            return 1 if level else 0
        raise MCPError(f"Invalid level: {level} (expected 0/1)")

    @staticmethod
    def _check_u8(v: int, name: str) -> int:
        if not isinstance(v, int):
            raise MCPError(f"{name} must be int, got {type(v)}")
        if v < 0 or v > 0xFF:
            raise MCPError(f"{name} out of range (0..255): {v}")
        return v

    @staticmethod
    def _pins_to_mask(pins: Iterable[int]) -> int:
        mask = 0
        for p in pins:
            if not isinstance(p, int):
                raise MCPError(f"Pin must be int, got {type(p)}")
            if p < 0 or p > 7:
                raise MCPError(f"Pin out of range (0..7): {p}")
            mask |= 1 << p
        return mask & 0xFF
