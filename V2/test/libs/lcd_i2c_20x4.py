#!/usr/bin/python3
# --------------------------------------
# lcd_i2c_backpack.py
# Minimal HD44780 LCD over I2C backpack (PCF8574 style), using smbus only.
# Supports 16x2 and 20x4 via configurable width/rows.
# Adds:
# - backlight_on/off
# - write_line
# - write_centered
# - clear_line
# - clear (full screen)
# --------------------------------------

import time
import smbus


class LCDI2CBackpack:
    # Modes
    LCD_CHR = 1  # Sending data
    LCD_CMD = 0  # Sending command

    # Backlight masks
    _BL_ON = 0x08
    _BL_OFF = 0x00

    ENABLE = 0b00000100

    # Timing
    E_PULSE = 0.0005
    E_DELAY = 0.0005

    # Base addresses for lines (HD44780 common mapping)
    _LINE_ADDR_1 = 0x80
    _LINE_ADDR_2 = 0xC0
    _LINE_ADDR_3 = 0x94
    _LINE_ADDR_4 = 0xD4

    def __init__(self, i2c_addr: int = 0x27, width: int = 20, rows: int = 4, bus_id: int = 1):
        self.I2C_ADDR = i2c_addr
        self.LCD_WIDTH = width
        self.LCD_ROWS = rows
        if self.LCD_ROWS not in (1, 2, 4):
            raise ValueError("rows doit être 1, 2, ou 4")
        self.bus = smbus.SMBus(bus_id)

        self._backlight_mask = self._BL_ON  # default ON
        self.init()
        self.clear()

    # -----------------------
    # Public API (requested)
    # -----------------------

    def backlight_on(self) -> None:
        self._backlight_mask = self._BL_ON
        # force a write to apply immediately
        self._write_raw(0x00)

    def backlight_off(self) -> None:
        self._backlight_mask = self._BL_OFF
        self._write_raw(0x00)

    def write_line(self, line: int, text: str, col: int = 0, pad: bool = True) -> None:
        """
        Write text on a given line (1..rows). Optional column offset.
        pad=True fills the remaining space with spaces (overwrites previous content).
        """
        self._validate_line(line)
        if not (0 <= col < self.LCD_WIDTH):
            raise ValueError(f"col doit être entre 0 et {self.LCD_WIDTH - 1}")

        addr = self._line_addr(line) + col
        self.lcd_byte(addr, self.LCD_CMD)

        s = (text or "")
        if pad:
            s = s[: (self.LCD_WIDTH - col)].ljust(self.LCD_WIDTH - col, " ")
        else:
            s = s[: (self.LCD_WIDTH - col)]

        for ch in s:
            self.lcd_byte(ord(ch), self.LCD_CHR)

    def write_centered(self, line: int, text: str) -> None:
        self._validate_line(line)
        s = (text or "")[: self.LCD_WIDTH]
        left = max((self.LCD_WIDTH - len(s)) // 2, 0)
        out = (" " * left + s).ljust(self.LCD_WIDTH, " ")
        self.write_line(line, out, col=0, pad=False)  # already padded

    def clear_line(self, line: int) -> None:
        self._validate_line(line)
        self.write_line(line, " " * self.LCD_WIDTH, col=0, pad=False)

    def clear(self) -> None:
        self.lcd_byte(0x01, self.LCD_CMD)
        time.sleep(self.E_DELAY)

    # -----------------------
    # Existing-style helpers
    # -----------------------

    def init(self) -> None:
        # Initialise display (classic sequence)
        self.lcd_byte(0x33, self.LCD_CMD)
        self.lcd_byte(0x32, self.LCD_CMD)
        self.lcd_byte(0x06, self.LCD_CMD)  # Entry mode
        self.lcd_byte(0x0C, self.LCD_CMD)  # Display ON, cursor OFF
        # Function set: 4-bit, 2-line, 5x8 dots (works for 20x4 too)
        self.lcd_byte(0x28, self.LCD_CMD)
        self.lcd_byte(0x01, self.LCD_CMD)  # Clear
        time.sleep(self.E_DELAY)

    def message(self, text: str) -> None:
        # Keep compatibility with the snippet you pasted
        for char in text:
            if char == "\n":
                self.lcd_byte(self._LINE_ADDR_2, self.LCD_CMD)
            else:
                self.lcd_byte(ord(char), self.LCD_CHR)

    def lcd_string(self, message: str, line_addr: int) -> None:
        # Compatible signature with your original code
        msg = (message or "").ljust(self.LCD_WIDTH, " ")[: self.LCD_WIDTH]
        self.lcd_byte(line_addr, self.LCD_CMD)
        for ch in msg:
            self.lcd_byte(ord(ch), self.LCD_CHR)

    # -----------------------
    # Low-level I2C write
    # -----------------------

    def lcd_byte(self, bits: int, mode: int) -> None:
        high = mode | (bits & 0xF0) | self._backlight_mask
        low = mode | ((bits << 4) & 0xF0) | self._backlight_mask

        self.bus.write_byte(self.I2C_ADDR, high)
        self.lcd_toggle_enable(high)

        self.bus.write_byte(self.I2C_ADDR, low)
        self.lcd_toggle_enable(low)

    def lcd_toggle_enable(self, bits: int) -> None:
        time.sleep(self.E_DELAY)
        self.bus.write_byte(self.I2C_ADDR, (bits | self.ENABLE))
        time.sleep(self.E_PULSE)
        self.bus.write_byte(self.I2C_ADDR, (bits & ~self.ENABLE))
        time.sleep(self.E_DELAY)

    def _write_raw(self, data: int) -> None:
        # raw write mainly to apply backlight mask
        self.bus.write_byte(self.I2C_ADDR, (data & 0xF0) | self._backlight_mask)

    # -----------------------
    # Internals
    # -----------------------

    def _validate_line(self, line: int) -> None:
        if not (1 <= line <= self.LCD_ROWS):
            raise ValueError(f"line doit être entre 1 et {self.LCD_ROWS}")

    def _line_addr(self, line: int) -> int:
        if line == 1:
            return self._LINE_ADDR_1
        if line == 2:
            return self._LINE_ADDR_2
        if line == 3:
            return self._LINE_ADDR_3
        return self._LINE_ADDR_4


# -----------------------
# Quick standalone test
# -----------------------
if __name__ == "__main__":
    lcd = LCDI2CBackpack(i2c_addr=0x3F, width=20, rows=4, bus_id=1)

    lcd.backlight_on()
    lcd.clear()
    lcd.write_centered(1, "TEST LCD I2C")
    lcd.write_line(2, "Ligne 2: OK")
    lcd.write_line(3, "12345678901234567890")
    time.sleep(2)

    lcd.clear_line(2)
    lcd.write_centered(4, "FIN")
    time.sleep(2)

    lcd.backlight_off()
    lcd.clear()
