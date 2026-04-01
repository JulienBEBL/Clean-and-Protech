"""
lcd2004.py — Driver LCD HD44780 20x4 via backpack I2C (PCF8574).

Responsabilité : affichage texte sur écran LCD relié en I2C.
Indépendant des autres composants (ne connaît que I2CBus).

Mapping PCF8574 (standard) :
    P0 → RS     P1 → RW (maintenu bas)
    P2 → E      P3 → Backlight
    P4 → D4     P5 → D5
    P6 → D6     P7 → D7

Usage :
    from libs.i2c_bus import I2CBus
    from libs.lcd2004 import LCD2004

    with I2CBus() as bus:
        lcd = LCD2004(bus)
        lcd.init()
        lcd.write(1, "Hello World")
        lcd.write_centered(2, "V4")
"""

from __future__ import annotations

import time

import config
from libs.i2c_bus import I2CBus


# ============================================================
# Driver LCD2004
# ============================================================

class LCD2004:
    """
    Écran LCD HD44780 20x4 piloté en mode 4 bits via backpack PCF8574.
    """

    # Commandes HD44780
    _CMD_CLEAR         = 0x01
    _CMD_ENTRY_MODE    = 0x04
    _CMD_DISPLAY_CTRL  = 0x08
    _CMD_FUNCTION_SET  = 0x20
    _CMD_SET_DDRAM     = 0x80

    # Flags entry mode
    _ENTRY_LEFT            = 0x02
    _ENTRY_SHIFT_DECREMENT = 0x00

    # Flags display control
    _DISPLAY_ON  = 0x04
    _CURSOR_OFF  = 0x00
    _BLINK_OFF   = 0x00

    # Flags function set
    _4BIT_MODE = 0x00
    _2LINE     = 0x08
    _5x8_DOTS  = 0x00

    # Bits PCF8574
    _BIT_RS = 0x01
    _BIT_RW = 0x02
    _BIT_E  = 0x04
    _BIT_BL = 0x08

    # Offsets DDRAM des 4 lignes (20x4)
    _ROW_OFFSETS = [0x00, 0x40, 0x14, 0x54]

    def __init__(
        self,
        bus: I2CBus,
        address: int = config.LCD_ADDR,
        cols: int = config.LCD_COLS,
        rows: int = config.LCD_ROWS,
    ) -> None:
        self.bus = bus
        self.address = int(address) & 0x7F
        self.cols = int(cols)
        self.rows = int(rows)
        self._backlight: bool = True

    # ---- init ----

    def init(self) -> None:
        """
        Initialise le LCD en mode 4 bits.
        À appeler une fois après ouverture du bus I2C.
        """
        time.sleep(0.05)
        self._expander_write(0x00)
        time.sleep(0.01)

        # Séquence d'init HD44780 en 8 bits (nibbles hauts)
        self._write4bits(0x30, rs=False); time.sleep(0.005)
        self._write4bits(0x30, rs=False); time.sleep(0.005)
        self._write4bits(0x30, rs=False); time.sleep(0.001)

        # Passage en 4 bits
        self._write4bits(0x20, rs=False); time.sleep(0.001)

        # Configuration
        self._command(self._CMD_FUNCTION_SET | self._4BIT_MODE | self._2LINE | self._5x8_DOTS)
        self._command(self._CMD_DISPLAY_CTRL | self._DISPLAY_ON | self._CURSOR_OFF | self._BLINK_OFF)
        self._command(self._CMD_ENTRY_MODE | self._ENTRY_LEFT | self._ENTRY_SHIFT_DECREMENT)
        self.clear()

    # ---- API publique ----

    def clear(self) -> None:
        """Efface tout l'écran."""
        self._command(self._CMD_CLEAR)
        time.sleep(0.002)

    def clear_line(self, line: int) -> None:
        """Efface une ligne (remplie d'espaces)."""
        self.set_cursor(line, 0)
        self._write_text(" " * self.cols)

    def backlight(self, enabled: bool) -> None:
        """Active ou désactive le rétroéclairage."""
        self._backlight = bool(enabled)
        self._expander_write(0x00)

    def set_cursor(self, line: int, col: int) -> None:
        """Positionne le curseur (ligne 0-based ou 1-based acceptés, col 0-based)."""
        line0 = self._norm_line(line)
        c = max(0, min(self.cols - 1, int(col)))
        self._command(self._CMD_SET_DDRAM | (self._ROW_OFFSETS[line0] + c))

    def write(self, line: int, text: str) -> None:
        """Écrit du texte sur une ligne (tronqué + paddé à cols caractères)."""
        self.write_line(line, text, center=False)

    def write_centered(self, line: int, text: str) -> None:
        """Écrit du texte centré sur une ligne."""
        self.write_line(line, text, center=True)

    def write_line(self, line: int, text: str, center: bool = False) -> None:
        """Écrit du texte sur une ligne, avec centrage optionnel."""
        s = (text or "")
        s = self._center(s, self.cols) if center else s[: self.cols].ljust(self.cols)
        self.set_cursor(line, 0)
        self._write_text(s)

    # ---- internals ----

    def _norm_line(self, line: int) -> int:
        """Accepte 0..rows-1 ou 1..rows. Retourne index 0-based."""
        l = int(line)
        if 1 <= l <= self.rows:
            l -= 1
        if not (0 <= l < self.rows):
            raise ValueError(f"line doit être dans 0..{self.rows - 1} (ou 1..{self.rows})")
        return l

    @staticmethod
    def _center(s: str, width: int) -> str:
        s2 = s[:width]
        pad = max(0, width - len(s2))
        left = pad // 2
        return (" " * left) + s2 + (" " * (pad - left))

    def _expander_write(self, data: int) -> None:
        bl = self._BIT_BL if self._backlight else 0
        byte = (int(data) & 0xFF) | bl
        bus = self.bus._require_open()
        self.bus._run("lcd_write_byte", self.address, lambda: bus.write_byte(self.address, byte))

    def _pulse_enable(self, data: int) -> None:
        self._expander_write(data | self._BIT_E)
        time.sleep(0.0005)
        self._expander_write(data & ~self._BIT_E)
        time.sleep(0.0001)

    def _write4bits(self, nibble: int, rs: bool) -> None:
        data = int(nibble) & 0xF0
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
