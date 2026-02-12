# hw/lcd_hd44780_i2c.py
# -*- coding: utf-8 -*-
"""
LCD HD44780 20x4 via backpack I2C PCF8574 (adresse typique 0x27).

Objectifs:
- API minimale: init(), clear(), home(), set_cursor(), print_line(), print()
- Pas de dépendance à config.yaml
- Basé sur hw/i2c.py (smbus2)

Note:
- Cette implémentation est volontairement simple et stable.
- Elle fonctionne avec la majorité des modules "1602/2004 I2C" (PCF8574).
- Si ton câblage du backpack est exotique, il faudra ajuster le mapping bits.
"""

from __future__ import annotations

import time
from typing import Optional

from hw.i2c import I2CBus


class LCD2004:
    # Flags PCF8574
    _BACKLIGHT = 0x08
    _EN = 0x04
    _RW = 0x02
    _RS = 0x01

    # Commandes HD44780
    _CLEARDISPLAY = 0x01
    _RETURNHOME = 0x02
    _ENTRYMODESET = 0x04
    _DISPLAYCONTROL = 0x08
    _CURSORSHIFT = 0x10
    _FUNCTIONSET = 0x20
    _SETCGRAMADDR = 0x40
    _SETDDRAMADDR = 0x80

    # Flags
    _ENTRYLEFT = 0x02
    _ENTRYSHIFTDECREMENT = 0x00

    _DISPLAYON = 0x04
    _CURSOROFF = 0x00
    _BLINKOFF = 0x00

    _4BITMODE = 0x00
    _2LINE = 0x08  # le 20x4 se configure comme 2 lignes (interne)
    _5x8DOTS = 0x00

    def __init__(self, bus: I2CBus, address: int = 0x27, cols: int = 20, rows: int = 4):
        self.bus = bus
        self.address = int(address) & 0x7F
        self.cols = int(cols)
        self.rows = int(rows)

        self._backlight = True
        self._display_control = self._DISPLAYON | self._CURSOROFF | self._BLINKOFF
        self._entry_mode = self._ENTRYLEFT | self._ENTRYSHIFTDECREMENT

        # offsets DDRAM typiques 20x4
        self._row_offsets = [0x00, 0x40, 0x14, 0x54]

    # -----------------------
    # Public API
    # -----------------------

    def init(self) -> None:
        """
        Initialise le LCD en mode 4-bit via PCF8574.
        """
        time.sleep(0.05)  # attente power-on

        # Séquence init 4-bit (datasheet standard)
        self._write4bits(0x03 << 4)
        time.sleep(0.005)
        self._write4bits(0x03 << 4)
        time.sleep(0.005)
        self._write4bits(0x03 << 4)
        time.sleep(0.001)
        self._write4bits(0x02 << 4)  # 4-bit mode

        # Function set
        self.command(self._FUNCTIONSET | self._4BITMODE | self._2LINE | self._5x8DOTS)

        # Display control
        self.command(self._DISPLAYCONTROL | self._display_control)

        # Clear
        self.clear()

        # Entry mode
        self.command(self._ENTRYMODESET | self._entry_mode)

        self.home()

    def clear(self) -> None:
        self.command(self._CLEARDISPLAY)
        time.sleep(0.002)

    def home(self) -> None:
        self.command(self._RETURNHOME)
        time.sleep(0.002)

    def backlight(self, on: bool) -> None:
        self._backlight = bool(on)
        # Réécrit un "noop" pour appliquer le backlight
        self._expander_write(0x00)

    def set_cursor(self, col: int, row: int) -> None:
        col = max(0, min(self.cols - 1, int(col)))
        row = max(0, min(self.rows - 1, int(row)))
        addr = col + self._row_offsets[row]
        self.command(self._SETDDRAMADDR | addr)

    def print(self, text: str) -> None:
        for ch in text:
            self.write_char(ord(ch))

    def print_line(self, row: int, text: str, *, clear_to_end: bool = True) -> None:
        """
        Ecrit une ligne (0..3). Optionnellement efface le reste de la ligne.
        """
        row = max(0, min(self.rows - 1, int(row)))
        self.set_cursor(0, row)

        s = text[: self.cols]
        self.print(s)

        if clear_to_end:
            remaining = self.cols - len(s)
            if remaining > 0:
                self.print(" " * remaining)

    # -----------------------
    # Low-level
    # -----------------------

    def command(self, value: int) -> None:
        self._send(value & 0xFF, rs=0)

    def write_char(self, value: int) -> None:
        self._send(value & 0xFF, rs=1)

    def _send(self, value: int, rs: int) -> None:
        high = value & 0xF0
        low = (value << 4) & 0xF0
        mode = self._RS if rs else 0

        self._write4bits(high | mode)
        self._write4bits(low | mode)

    def _write4bits(self, data: int) -> None:
        self._expander_write(data)
        self._pulse_enable(data)

    def _pulse_enable(self, data: int) -> None:
        self._expander_write(data | self._EN)
        time.sleep(0.0005)
        self._expander_write(data & ~self._EN)
        time.sleep(0.0001)

    def _expander_write(self, data: int) -> None:
        bl = self._BACKLIGHT if self._backlight else 0x00
        self.bus.write_byte_data(self.address, 0x00, (data | bl) & 0xFF)
