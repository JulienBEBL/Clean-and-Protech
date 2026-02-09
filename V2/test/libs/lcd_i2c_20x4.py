# lcd_i2c_20x4.py
# LCD HD44780 20x4 via backpack I2C (souvent PCF8574)
# Dépendances: pip3 install RPLCD smbus2

from __future__ import annotations
from typing import Optional

from RPLCD.i2c import CharLCD


class LCD20x4I2C:
    def __init__(
        self,
        i2c_address: int = 0x27,
        i2c_port: int = 1,
        cols: int = 20,
        rows: int = 4,
        charmap: str = "A00",
        auto_linebreaks: bool = False,
    ) -> None:
        self.cols = cols
        self.rows = rows
        self.lcd = CharLCD(
            i2c_expander="PCF8574",
            address=i2c_address,
            port=i2c_port,
            cols=cols,
            rows=rows,
            charmap=charmap,
            auto_linebreaks=auto_linebreaks,
        )

    # 1) Allumer la LED (backlight)
    def backlight_on(self) -> None:
        self.lcd.backlight_enabled = True

    # 2) Eteindre la LED (backlight)
    def backlight_off(self) -> None:
        self.lcd.backlight_enabled = False

    # 6) Clear l'écran entier
    def clear(self) -> None:
        self.lcd.clear()

    # 5) Effacer une ligne
    def clear_line(self, line: int) -> None:
        self._validate_line(line)
        self.write_line(line, " " * self.cols)

    # 3) Ecrire du texte sur une ligne specifique
    def write_line(self, line: int, text: str, col: int = 0) -> None:
        """
        line: 1..rows
        col : 0..cols-1
        """
        self._validate_line(line)
        if not (0 <= col < self.cols):
            raise ValueError(f"col doit être entre 0 et {self.cols - 1}")

        # tronque pour éviter débordement
        safe = (text or "")[: (self.cols - col)]
        # curseur: (row_index, col_index) en base 0
        self.lcd.cursor_pos = (line - 1, col)
        self.lcd.write_string(safe)

        # option: compléter avec des espaces si tu veux "écraser" l'ancien texte
        # fill = self.cols - col - len(safe)
        # if fill > 0:
        #     self.lcd.write_string(" " * fill)

    # 4) Centrer le texte
    def write_centered(self, line: int, text: str) -> None:
        self._validate_line(line)
        s = (text or "")[: self.cols]
        pad_total = self.cols - len(s)
        left = pad_total // 2
        out = (" " * left) + s
        out = out.ljust(self.cols)
        self.write_line(line, out, col=0)

    def _validate_line(self, line: int) -> None:
        if not (1 <= line <= self.rows):
            raise ValueError(f"line doit être entre 1 et {self.rows}")
