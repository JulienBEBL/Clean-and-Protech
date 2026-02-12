"""
Petit module utilitaire pour l'I2C :
- gestion simple des MCP23017
- wrapper très basique pour LCD 20x4 I2C (PCF8574)

Objectif : rester lisible et facilement modifiable.
"""

import time

try:
    # smbus2 est plus moderne, on essaye d'abord.
    from smbus2 import SMBus
except ImportError:  # fallback sur smbus classique
    from smbus import SMBus  # type: ignore


class MCP23017:
    """
    Pilote minimal MCP23017.

    On ne gère ici que les registres dont on a besoin :
    - IODIRA / IODIRB : direction (1 = entrée, 0 = sortie)
    - GPPUA / GPPUB   : pull-up internes
    - GPIOA / GPIOB   : lecture/écriture des bits

    On reste en mode "bank=0" (registre consécutifs).
    """

    # Adresses de registres (bank=0)
    IODIRA = 0x00
    IODIRB = 0x01
    GPPUA = 0x0C
    GPPUB = 0x0D
    GPIOA = 0x12
    GPIOB = 0x13

    def __init__(self, bus: SMBus, address: int, name: str = ""):
        self.bus = bus
        self.address = address
        self.name = name or f"MCP@0x{address:02X}"

        # Au démarrage : tout en entrée, pull-up off.
        self._write_reg(self.IODIRA, 0xFF)
        self._write_reg(self.IODIRB, 0xFF)
        self._write_reg(self.GPPUA, 0x00)
        self._write_reg(self.GPPUB, 0x00)

    # --- bas niveau ---

    def _write_reg(self, reg: int, value: int) -> None:
        self.bus.write_byte_data(self.address, reg, value & 0xFF)

    def _read_reg(self, reg: int) -> int:
        return self.bus.read_byte_data(self.address, reg)

    # --- configuration direction / pull-up ---

    def configure_bank(
        self,
        bank: str,
        direction_mask: int,
        pullup_mask: int = 0x00,
    ) -> None:
        """
        Configure une banque :
        - bank : "A" ou "B"
        - direction_mask : 1 = entrée, 0 = sortie
        - pullup_mask : 1 = pull-up activée (uniquement sur entrées)
        """
        bank = bank.upper()
        if bank == "A":
            self._write_reg(self.IODIRA, direction_mask)
            self._write_reg(self.GPPUA, pullup_mask)
        elif bank == "B":
            self._write_reg(self.IODIRB, direction_mask)
            self._write_reg(self.GPPUB, pullup_mask)
        else:
            raise ValueError("bank doit être 'A' ou 'B'")

    # --- lecture / écriture GPIO ---

    def read_bank(self, bank: str) -> int:
        bank = bank.upper()
        if bank == "A":
            return self._read_reg(self.GPIOA)
        elif bank == "B":
            return self._read_reg(self.GPIOB)
        raise ValueError("bank doit être 'A' ou 'B'")

    def write_bank(self, bank: str, value: int) -> None:
        bank = bank.upper()
        if bank == "A":
            self._write_reg(self.GPIOA, value)
        elif bank == "B":
            self._write_reg(self.GPIOB, value)
        else:
            raise ValueError("bank doit être 'A' ou 'B'")

    def read_bit(self, bank: str, bit: int) -> int:
        """
        Retourne 0 ou 1 pour un bit d'une banque.
        """
        value = self.read_bank(bank)
        return 1 if (value & (1 << bit)) else 0

    def write_bit(self, bank: str, bit: int, level: int) -> None:
        """
        Met à jour un bit en laissant les autres inchangés.
        level = 0 ou 1.
        """
        value = self.read_bank(bank)
        if level:
            value |= (1 << bit)
        else:
            value &= ~(1 << bit)
        self.write_bank(bank, value)


class LCD20x4:
    """
    Wrapper très simple autour d'un LCD 20x4 via backpack I2C type PCF8574.
    Inspiré des exemples classiques "LCD I2C Python".

    BUT : afficher quelques lignes sans se perdre dans les détails.
    """

    # Commandes génériques
    LCD_CHR = 1
    LCD_CMD = 0

    LCD_LINE_1 = 0x80
    LCD_LINE_2 = 0xC0
    LCD_LINE_3 = 0x94
    LCD_LINE_4 = 0xD4

    ENABLE = 0b00000100
    BACKLIGHT = 0b00001000

    def __init__(self, bus: SMBus, address: int, width: int = 20):
        self.bus = bus
        self.address = address
        self.width = width

        time.sleep(0.05)
        # Initialisation standard 4 bits
        self._send_byte(0x33, self.LCD_CMD)
        self._send_byte(0x32, self.LCD_CMD)
        self._send_byte(0x06, self.LCD_CMD)
        self._send_byte(0x0C, self.LCD_CMD)
        self._send_byte(0x28, self.LCD_CMD)
        self.clear()

    # --- bas niveau ---

    def _write(self, data: int) -> None:
        self.bus.write_byte(self.address, data | self.BACKLIGHT)

    def _strobe(self, data: int) -> None:
        self._write(data | self.ENABLE)
        time.sleep(0.0005)
        self._write(data & ~self.ENABLE)
        time.sleep(0.0001)

    def _send_byte(self, bits: int, mode: int) -> None:
        high = mode | (bits & 0xF0)
        low = mode | ((bits << 4) & 0xF0)
        self._write(high)
        self._strobe(high)
        self._write(low)
        self._strobe(low)

    # --- API publique simple ---

    def clear(self) -> None:
        self._send_byte(0x01, self.LCD_CMD)
        time.sleep(0.002)

    def set_cursor(self, line_addr: int) -> None:
        self._send_byte(line_addr, self.LCD_CMD)

    def write_line(self, line: int, text: str) -> None:
        """
        Ecrit une ligne (1..4) avec auto-padding / tronquage.
        """
        addr_map = {
            1: self.LCD_LINE_1,
            2: self.LCD_LINE_2,
            3: self.LCD_LINE_3,
            4: self.LCD_LINE_4,
        }
        addr = addr_map.get(line, self.LCD_LINE_1)
        self.set_cursor(addr)
        text = str(text).ljust(self.width)[: self.width]
        for ch in text:
            self._send_byte(ord(ch), self.LCD_CHR)

