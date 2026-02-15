from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Optional, Sequence, List

# ----------------------------
# Constantes simples (main)
# ----------------------------
HIGH: int = 1
LOW: int = 0

ON: int = 1
OFF: int = 0

OUVERTURE = "OUVERTURE"
FERMETURE = "FERMETURE"

__all__ = [
    "HIGH",
    "LOW",
    "ON",
    "OFF",
    "OUVERTURE",
    "FERMETURE",
    "I2CBus",
    "MCP23017",
    "LCD2004",
    "IOBoard",
]

# ----------------------------
# Exceptions
# ----------------------------
class I2CError(Exception):
    """Base exception for I2C-related failures."""

class I2CNotOpenError(I2CError):
    """Raised when using the bus while not opened."""

class I2CNackError(I2CError):
    """Raised when a device does not ACK (no device / wrong address / wiring)."""

class I2CIOError(I2CError):
    """Raised on generic I/O errors after retries."""

class DeviceError(I2CError):
    """Raised when a device-level operation fails."""


# ----------------------------
# SMBus import (smbus2 -> smbus)
# ----------------------------
try:
    from smbus2 import SMBus  # type: ignore
except Exception:  # pragma: no cover
    try:
        from smbus import SMBus  # type: ignore
    except Exception as e:  # pragma: no cover
        raise ImportError(
            "Neither 'smbus2' nor 'smbus' is available. Install smbus2: pip install smbus2"
        ) from e


# ----------------------------
# I2C Bus layer
# ----------------------------
@dataclass(frozen=True)
class I2CBusConfig:
    bus_id: int = 1
    freq_hz: int = 100_000  # informational (Linux i2c-dev doesn't let us set it reliably here)
    retries: int = 2
    retry_delay_s: float = 0.01


class I2CBus:
    """
    Robust I2C bus wrapper.

    Notes:
    - freq_hz is stored for traceability but not enforced by smbus on Linux.
    - Retries are applied to each transaction.
    """

    def __init__(
        self,
        bus_id: int = 1,
        freq_hz: int = 100_000,
        retries: int = 2,
        retry_delay_s: float = 0.01,
    ):
        if retries < 0:
            raise ValueError("retries must be >= 0")
        if retry_delay_s < 0:
            raise ValueError("retry_delay_s must be >= 0")

        self.config = I2CBusConfig(
            bus_id=bus_id,
            freq_hz=freq_hz,
            retries=retries,
            retry_delay_s=retry_delay_s,
        )
        self._bus: Optional[SMBus] = None

    def open(self) -> None:
        """Open /dev/i2c-<bus_id>."""
        if self._bus is None:
            try:
                self._bus = SMBus(self.config.bus_id)
            except FileNotFoundError as e:
                raise I2CIOError(f"I2C bus /dev/i2c-{self.config.bus_id} not found") from e
            except PermissionError as e:
                raise I2CIOError(
                    f"Permission denied opening /dev/i2c-{self.config.bus_id} (try adding user to i2c group)"
                ) from e
            except Exception as e:
                raise I2CIOError(f"Failed to open I2C bus {self.config.bus_id}: {e}") from e

    def close(self) -> None:
        """Close bus if open."""
        if self._bus is not None:
            try:
                self._bus.close()
            finally:
                self._bus = None

    def __enter__(self) -> "I2CBus":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _require_open(self) -> SMBus:
        if self._bus is None:
            raise I2CNotOpenError(
                "I2C bus is not open. Call bus.open() or use 'with I2CBus(...) as bus:'"
            )
        return self._bus

    def _sleep_retry(self) -> None:
        if self.config.retry_delay_s > 0:
            time.sleep(self.config.retry_delay_s)

    def _run(self, op_name: str, addr: int, fn):
        last_exc: Optional[Exception] = None
        attempts = self.config.retries + 1
        for i in range(attempts):
            try:
                return fn()
            except OSError as e:
                last_exc = e
                if i < attempts - 1:
                    self._sleep_retry()
                    continue
                msg = (
                    f"I2C {op_name} failed (addr=0x{addr:02X}, bus={self.config.bus_id}) "
                    f"after {attempts} attempts: {e}"
                )
                if getattr(e, "errno", None) in (6, 121):  # ENXIO=6, EREMOTEIO=121 (common)
                    raise I2CNackError(msg) from e
                raise I2CIOError(msg) from e
            except Exception as e:
                last_exc = e
                break
        raise I2CIOError(
            f"I2C {op_name} failed (addr=0x{addr:02X}, bus={self.config.bus_id}): {last_exc}"
        ) from last_exc

    # ---- primitives ----
    def write_u8(self, addr: int, reg: int, value: int) -> None:
        """Write 1 byte to device register."""
        bus = self._require_open()
        value &= 0xFF
        reg &= 0xFF

        def _op():
            bus.write_byte_data(addr, reg, value)

        self._run("write_u8", addr, _op)

    def read_u8(self, addr: int, reg: int) -> int:
        """Read 1 byte from device register."""
        bus = self._require_open()
        reg &= 0xFF

        def _op():
            return int(bus.read_byte_data(addr, reg)) & 0xFF

        return int(self._run("read_u8", addr, _op))

    def write_block(self, addr: int, reg: int, data: Sequence[int]) -> None:
        """Write up to 32 bytes (SMBus limitation) to consecutive registers."""
        bus = self._require_open()
        reg &= 0xFF
        payload = [int(b) & 0xFF for b in data]

        def _op():
            bus.write_i2c_block_data(addr, reg, payload)

        self._run("write_block", addr, _op)

    def read_block(self, addr: int, reg: int, length: int) -> List[int]:
        """Read a block of bytes starting at register."""
        if length <= 0:
            return []
        bus = self._require_open()
        reg &= 0xFF

        def _op():
            return [int(b) & 0xFF for b in bus.read_i2c_block_data(addr, reg, length)]

        return list(self._run("read_block", addr, _op))

    def write_read(self, addr: int, write_bytes: Sequence[int], read_len: int) -> List[int]:
        """
        Generic 'write then read' (best-effort via SMBus ops).

        - If write_bytes is [reg], uses read_i2c_block_data.
        - If write_bytes is [reg, ...], uses write_i2c_block_data then read_i2c_block_data.
        """
        if read_len < 0:
            raise ValueError("read_len must be >= 0")
        if read_len == 0:
            return []
        if len(write_bytes) == 0:
            raise ValueError("write_bytes must contain at least one byte (typically the register)")

        reg = int(write_bytes[0]) & 0xFF
        tail = [int(b) & 0xFF for b in write_bytes[1:]]

        if len(tail) == 0:
            return self.read_block(addr, reg, read_len)

        self.write_block(addr, reg, tail)
        return self.read_block(addr, reg, read_len)

    def scan(self, start: int = 0x03, end: int = 0x77) -> List[int]:
        """
        Scan addresses by attempting read_byte.
        Returns list of addresses that ACK.
        """
        bus = self._require_open()
        found: List[int] = []
        for addr in range(start, end + 1):
            try:
                bus.read_byte(addr)
                found.append(addr)
            except OSError:
                continue
        return found


# ----------------------------
# MCP23017 driver (BANK=0)
# ----------------------------
class MCP23017:
    """
    MCP23017 I/O expander (I2C), register BANK=0.

    Minimal registers:
    - IODIRA/B, GPIOA/B, OLATA/B, GPPUA/B, IOCON
    """

    # BANK=0 addresses
    _REG_IODIRA = 0x00
    _REG_IODIRB = 0x01
    _REG_IOCON = 0x0A  # mirrored at 0x0B; we use 0x0A
    _REG_GPPUA = 0x0C
    _REG_GPPUB = 0x0D
    _REG_GPIOA = 0x12
    _REG_GPIOB = 0x13
    _REG_OLATA = 0x14
    _REG_OLATB = 0x15

    def __init__(self, bus: I2CBus, address: int):
        self.bus = bus
        self.address = int(address) & 0x7F

    @staticmethod
    def _norm_port(port: str) -> str:
        p = port.strip().upper()
        if p not in ("A", "B"):
            raise ValueError("port must be 'A' or 'B'")
        return p

    @staticmethod
    def _check_pin(pin: int) -> int:
        if not (0 <= pin <= 7):
            raise ValueError("pin must be in range 0..7")
        return int(pin)

    def init(self, force: bool = True) -> None:
        """
        Initialize device registers.

        If force=True:
        - write IOCON with BANK=0 (bit7=0). Others default (0x00).
        """
        try:
            if force:
                self.bus.write_u8(self.address, self._REG_IOCON, 0x00)
        except I2CError as e:
            raise DeviceError(f"MCP23017 init failed at 0x{self.address:02X}: {e}") from e

    def _reg_iodir(self, port: str) -> int:
        return self._REG_IODIRA if self._norm_port(port) == "A" else self._REG_IODIRB

    def _reg_gppu(self, port: str) -> int:
        return self._REG_GPPUA if self._norm_port(port) == "A" else self._REG_GPPUB

    def _reg_gpio(self, port: str) -> int:
        return self._REG_GPIOA if self._norm_port(port) == "A" else self._REG_GPIOB

    def _reg_olat(self, port: str) -> int:
        return self._REG_OLATA if self._norm_port(port) == "A" else self._REG_OLATB

    def set_port_direction(self, port: str, mask: int) -> None:
        """
        Set IODIR for a port.
        mask bit=1 => input, bit=0 => output.
        """
        reg = self._reg_iodir(port)
        self.bus.write_u8(self.address, reg, int(mask) & 0xFF)

    def set_pin_mode(self, port: str, pin: int, mode: str) -> None:
        """
        Set one pin direction.
        mode: 'INPUT' or 'OUTPUT'
        """
        p = self._norm_port(port)
        b = self._check_pin(pin)
        m = mode.strip().upper()
        if m not in ("INPUT", "OUTPUT"):
            raise ValueError("mode must be 'INPUT' or 'OUTPUT'")

        reg = self._reg_iodir(p)
        cur = self.bus.read_u8(self.address, reg)
        bit = 1 << b
        if m == "INPUT":
            new = cur | bit
        else:
            new = cur & (~bit & 0xFF)
        self.bus.write_u8(self.address, reg, new)

    def write_port(self, port: str, value: int) -> None:
        """
        Write output latch for a port (OLAT).
        """
        reg = self._reg_olat(port)
        self.bus.write_u8(self.address, reg, int(value) & 0xFF)

    def write_pin(self, port: str, pin: int, value: int) -> None:
        """Read-modify-write OLAT bit for one pin."""
        p = self._norm_port(port)
        b = self._check_pin(pin)
        v = 1 if int(value) else 0

        reg = self._reg_olat(p)
        cur = self.bus.read_u8(self.address, reg)
        bit = 1 << b
        new = (cur | bit) if v else (cur & (~bit & 0xFF))
        self.bus.write_u8(self.address, reg, new)

    def read_port(self, port: str) -> int:
        """Read GPIO register (actual pin levels)."""
        reg = self._reg_gpio(port)
        return self.bus.read_u8(self.address, reg)

    def read_pin(self, port: str, pin: int) -> int:
        """Read one pin from GPIO register."""
        p = self._norm_port(port)
        b = self._check_pin(pin)
        val = self.read_port(p)
        return 1 if (val & (1 << b)) else 0

    def set_pullup(self, port: str, mask: int) -> None:
        """
        Configure pull-ups for a port (GPPU).
        mask bit=1 => pull-up enabled (effective only if pin is INPUT).
        """
        reg = self._reg_gppu(port)
        self.bus.write_u8(self.address, reg, int(mask) & 0xFF)

    def set_pullup_pin(self, port: str, pin: int, enabled: bool) -> None:
        """Read-modify-write GPPU bit for one pin."""
        p = self._norm_port(port)
        b = self._check_pin(pin)

        reg = self._reg_gppu(p)
        cur = self.bus.read_u8(self.address, reg)
        bit = 1 << b
        new = (cur | bit) if enabled else (cur & (~bit & 0xFF))
        self.bus.write_u8(self.address, reg, new)


# ----------------------------
# LCD2004 (HD44780 over PCF8574)
# ----------------------------
class LCD2004:
    """
    HD44780 20x4 via I2C backpack (PCF8574-like).

    Assumed common mapping:
      P0 RS
      P1 RW
      P2 E
      P3 Backlight
      P4 D4
      P5 D5
      P6 D6
      P7 D7

    RW kept low (write-only).
    """

    # Commands
    _LCD_CLEARDISPLAY = 0x01
    _LCD_ENTRYMODESET = 0x04
    _LCD_DISPLAYCONTROL = 0x08
    _LCD_FUNCTIONSET = 0x20
    _LCD_SETDDRAMADDR = 0x80

    # Flags
    _LCD_ENTRYLEFT = 0x02
    _LCD_ENTRYSHIFTDECREMENT = 0x00

    _LCD_DISPLAYON = 0x04
    _LCD_CURSOROFF = 0x00
    _LCD_BLINKOFF = 0x00

    _LCD_4BITMODE = 0x00
    _LCD_2LINE = 0x08  # used also for 4-line modules
    _LCD_5x8DOTS = 0x00

    # PCF8574 bits
    _BIT_RS = 0x01
    _BIT_RW = 0x02
    _BIT_E = 0x04
    _BIT_BL = 0x08

    def __init__(self, bus: I2CBus, address: int, cols: int = 20, rows: int = 4):
        self.bus = bus
        self.address = int(address) & 0x7F
        self.cols = int(cols)
        self.rows = int(rows)

        self._backlight = True

        # Common DDRAM line offsets for 20x4:
        self._row_offsets = [0x00, 0x40, 0x14, 0x54]

    def init(self) -> None:
        """
        Initialize LCD in 4-bit mode via PCF8574.
        """
        time.sleep(0.05)
        self._expander_write(0x00)
        time.sleep(0.01)

        # 8-bit init sequence (high nibbles)
        self._write4bits(0x30, rs=False)
        time.sleep(0.005)
        self._write4bits(0x30, rs=False)
        time.sleep(0.005)
        self._write4bits(0x30, rs=False)
        time.sleep(0.001)

        # Switch to 4-bit
        self._write4bits(0x20, rs=False)
        time.sleep(0.001)

        function = self._LCD_FUNCTIONSET | self._LCD_4BITMODE | self._LCD_2LINE | self._LCD_5x8DOTS
        self._command(function)

        display = self._LCD_DISPLAYCONTROL | self._LCD_DISPLAYON | self._LCD_CURSOROFF | self._LCD_BLINKOFF
        self._command(display)

        entry = self._LCD_ENTRYMODESET | self._LCD_ENTRYLEFT | self._LCD_ENTRYSHIFTDECREMENT
        self._command(entry)

        self.clear()

    def backlight(self, enabled: bool) -> None:
        self._backlight = bool(enabled)
        self._expander_write(0x00)

    def clear(self) -> None:
        self._command(self._LCD_CLEARDISPLAY)
        time.sleep(0.002)

    def clear_line(self, line: int) -> None:
        line0 = self._norm_line(line)
        self.set_cursor(line0, 0)
        self._write_text(" " * self.cols)

    def set_cursor(self, line: int, col: int) -> None:
        line0 = self._norm_line(line)
        c = max(0, min(self.cols - 1, int(col)))
        addr = self._row_offsets[line0] + c
        self._command(self._LCD_SETDDRAMADDR | addr)

    def write_line(self, line: int, text: str, center: bool = False) -> None:
        line0 = self._norm_line(line)
        s = (text or "")
        if center:
            s = self._center(s, self.cols)
        else:
            s = s[: self.cols].ljust(self.cols)
        self.set_cursor(line0, 0)
        self._write_text(s)

    def write_centered(self, line: int, text: str) -> None:
        self.write_line(line, text, center=True)

    def write(self, line: int, text: str) -> None:
        """Alias: lcd.write(2, 'Hello')"""
        self.write_line(line, text, center=False)

    # ---- internals ----
    def _norm_line(self, line: int) -> int:
        """
        Accept 0..rows-1 OR 1..rows (tolerant).
        Returns 0-based line index.
        """
        l = int(line)
        if 1 <= l <= self.rows:
            l -= 1
        if not (0 <= l < self.rows):
            raise ValueError(f"line must be in range 0..{self.rows-1} (or 1..{self.rows})")
        return l

    @staticmethod
    def _center(s: str, width: int) -> str:
        s2 = s[:width]
        pad = max(0, width - len(s2))
        left = pad // 2
        right = pad - left
        return (" " * left) + s2 + (" " * right)

    def _expander_write(self, data: int) -> None:
        bl = self._BIT_BL if self._backlight else 0
        self.bus._require_open()

        def _op():
            self.bus._require_open().write_byte(self.address, (int(data) & 0xFF) | bl)

        self.bus._run("lcd_write_byte", self.address, _op)

    def _pulse_enable(self, data: int) -> None:
        self._expander_write(data | self._BIT_E)
        time.sleep(0.0005)
        self._expander_write(data & ~self._BIT_E)
        time.sleep(0.0001)

    def _write4bits(self, nibble_with_upper: int, rs: bool) -> None:
        data = int(nibble_with_upper) & 0xF0
        if rs:
            data |= self._BIT_RS
        self._expander_write(data)
        self._pulse_enable(data)

    def _send(self, value: int, rs: bool) -> None:
        v = int(value) & 0xFF
        self._write4bits(v & 0xF0, rs=rs)
        self._write4bits((v << 4) & 0xF0, rs=rs)

    def _command(self, cmd: int) -> None:
        self._send(cmd, rs=False)

    def _write_char(self, ch: str) -> None:
        self._send(ord(ch) & 0xFF, rs=True)

    def _write_text(self, s: str) -> None:
        for ch in s:
            self._write_char(ch)


# ----------------------------
# Mapping "board" (helpers)
# ----------------------------
class IOBoard:
    """
    Couche applicative au-dessus des 3 MCP23017, avec mapping fixe.

    Entrées câblées vers GND => actif bas (appui = 0):
    - read_btn_active / read_vic_active / read_air_active => 1 si actif, 0 sinon.

    mcp1: 0x24  # Programmes (LED + boutons)
      B=INPUT : B0..B5 = PRG1..PRG6
      A=OUTPUT: A2..A7 = LED1..LED6

    mcp2: 0x25  # Sélecteurs VIC / AIR
      A=INPUT : A7..A4 = AIR1..AIR4
      B=INPUT : B0..B4 = VIC1..VIC5

    mcp3: 0x26  # Drivers moteurs (ENA + DIR)
      B=OUTPUT: B0..B7 = ENA1..ENA8
      A=OUTPUT: A7..A0 = DIR1..DIR8 (inversé)
    """

    MCP1_ADDR = 0x24
    MCP2_ADDR = 0x25
    MCP3_ADDR = 0x26

    def __init__(self, bus: I2CBus):
        self.bus = bus
        self.mcp1 = MCP23017(bus, self.MCP1_ADDR)
        self.mcp2 = MCP23017(bus, self.MCP2_ADDR)
        self.mcp3 = MCP23017(bus, self.MCP3_ADDR)

        # caches OLAT (évite RMW I2C à chaque set)
        self._mcp1_olat_a: int = 0x00
        self._mcp3_olat_a: int = 0x00
        self._mcp3_olat_b: int = 0x00

    def init(self, force: bool = True) -> None:
        """
        Initialise les 3 MCP selon la politique:
        - Directions fixes
        - Pull-ups activés sur toutes les entrées (par défaut)
        - Sorties à 0 au départ (LED/ENA/DIR)
        """
        self.mcp1.init(force=force)
        self.mcp2.init(force=force)
        self.mcp3.init(force=force)

        # Directions
        self.mcp1.set_port_direction("B", 0xFF)  # inputs
        self.mcp1.set_port_direction("A", 0x00)  # outputs

        self.mcp2.set_port_direction("A", 0xFF)  # inputs
        self.mcp2.set_port_direction("B", 0xFF)  # inputs

        self.mcp3.set_port_direction("A", 0x00)  # outputs
        self.mcp3.set_port_direction("B", 0x00)  # outputs

        # Pull-ups
        self.mcp1.set_pullup("B", 0xFF)
        self.mcp2.set_pullup("A", 0xFF)
        self.mcp2.set_pullup("B", 0xFF)

        # Safe defaults
        self._mcp1_olat_a = 0x00
        self._mcp3_olat_a = 0x00
        self._mcp3_olat_b = 0x00

        self.mcp1.write_port("A", self._mcp1_olat_a)
        self.mcp3.write_port("A", self._mcp3_olat_a)
        self.mcp3.write_port("B", self._mcp3_olat_b)

    # ----------------------------
    # LED (mcp1 A2..A7) — active high
    # ----------------------------
    @staticmethod
    def _led_pin(led_index: int) -> int:
        i = int(led_index)
        if not (1 <= i <= 6):
            raise ValueError("led_index must be in range 1..6")
        return 1 + i  # 1->2, 6->7

    def set_led(self, led_index: int, state: int) -> None:
        pin = self._led_pin(led_index)
        bit = 1 << pin
        if int(state):
            self._mcp1_olat_a |= bit
        else:
            self._mcp1_olat_a &= (~bit & 0xFF)
        self.mcp1.write_port("A", self._mcp1_olat_a)

    # ----------------------------
    # Program buttons PRG (mcp1 B0..B5) — active low
    # ----------------------------
    @staticmethod
    def _prg_pin(prg_index: int) -> int:
        i = int(prg_index)
        if not (1 <= i <= 6):
            raise ValueError("prg_index must be in range 1..6")
        return i - 1

    def read_btn(self, prg_index: int) -> int:
        """Raw level (1=high, 0=low)."""
        pin = self._prg_pin(prg_index)
        return self.mcp1.read_pin("B", pin)

    def read_btn_active(self, prg_index: int) -> int:
        """Active-low semantic (1=pressed/active, 0=inactive)."""
        return 1 if self.read_btn(prg_index) == 0 else 0

    # ----------------------------
    # VIC (mcp2 B0..B4) — active low
    # ----------------------------
    @staticmethod
    def _vic_pin(vic_index: int) -> int:
        i = int(vic_index)
        if not (1 <= i <= 5):
            raise ValueError("vic_index must be in range 1..5")
        return i - 1

    def read_vic(self, vic_index: int) -> int:
        """Raw level."""
        pin = self._vic_pin(vic_index)
        return self.mcp2.read_pin("B", pin)

    def read_vic_active(self, vic_index: int) -> int:
        """Active-low semantic (1=selected/active)."""
        return 1 if self.read_vic(vic_index) == 0 else 0

    # ----------------------------
    # AIR (mcp2 A7..A4) — active low
    # ----------------------------
    @staticmethod
    def _air_pin(air_index: int) -> int:
        i = int(air_index)
        if not (1 <= i <= 4):
            raise ValueError("air_index must be in range 1..4")
        return 8 - i  # 1->7, 4->4

    def read_air(self, air_index: int) -> int:
        """Raw level."""
        pin = self._air_pin(air_index)
        return self.mcp2.read_pin("A", pin)

    def read_air_active(self, air_index: int) -> int:
        """Active-low semantic (1=selected/active)."""
        return 1 if self.read_air(air_index) == 0 else 0

    # ----------------------------
    # ENA (mcp3 B0..B7) — active high
    # ----------------------------
    @staticmethod
    def _ena_pin(motor_index: int) -> int:
        i = int(motor_index)
        if not (1 <= i <= 8):
            raise ValueError("motor_index must be in range 1..8")
        return i - 1

    def set_ena(self, motor_index: int, state: int) -> None:
        pin = self._ena_pin(motor_index)
        bit = 1 << pin
        if int(state):
            self._mcp3_olat_b |= bit
        else:
            self._mcp3_olat_b &= (~bit & 0xFF)
        self.mcp3.write_port("B", self._mcp3_olat_b)

    # ----------------------------
    # DIR (mcp3 A7..A0) — active high
    # Convention: OUVERTURE=1, FERMETURE=0
    # ----------------------------
    @staticmethod
    def _dir_pin(motor_index: int) -> int:
        i = int(motor_index)
        if not (1 <= i <= 8):
            raise ValueError("motor_index must be in range 1..8")
        return 8 - i  # 1->7, 8->0

    def set_dir(self, motor_index: int, direction: str) -> None:
        d = direction.strip().upper()
        if d in ("OUVERTURE", "OPEN", "O"):
            v = 1
        elif d in ("FERMETURE", "CLOSE", "F"):
            v = 0
        else:
            raise ValueError("direction must be 'ouverture' or 'fermeture' (or OPEN/CLOSE)")

        pin = self._dir_pin(motor_index)
        bit = 1 << pin
        if v:
            self._mcp3_olat_a |= bit
        else:
            self._mcp3_olat_a &= (~bit & 0xFF)
        self.mcp3.write_port("A", self._mcp3_olat_a)


# ----------------------------
# Exemple (manuel) si lancé en direct
# ----------------------------
if __name__ == "__main__":
    bus = I2CBus(bus_id=1, freq_hz=100000, retries=2, retry_delay_s=0.01)

    with bus:
        print("I2C scan:", [f"0x{x:02X}" for x in bus.scan()])

        io = IOBoard(bus)
        io.init(force=True)

        lcd = LCD2004(bus, address=0x27, cols=20, rows=4)
        lcd.init()
        lcd.clear()
        lcd.write(1, "I2C OK")
        lcd.write(2, f"BTN1={io.read_btn_active(1)}")
        io.set_led(1, ON)
