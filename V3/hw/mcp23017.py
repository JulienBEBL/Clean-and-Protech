# hw/mcp23017.py
# -*- coding: utf-8 -*-
"""
Driver MCP23017 (I2C) simple et robuste, basé sur hw/i2c.py.

Objectifs:
- API claire: init(), read_gpio(), write_gpio(), write_mask(), write_bit()
- Cache interne des sorties (OLAT) pour éviter les read-modify-write coûteux
- Pas de sur-architecture, pas de dépendance à config.yaml

Hypothèses:
- Mode registre "BANK=0" (par défaut) : adresses standards.
"""

from __future__ import annotations

from typing import Literal

from hw.i2c import I2CBus


Bank = Literal["A", "B"]

# Registres MCP23017 (BANK=0)
IODIRA = 0x00
IODIRB = 0x01
IPOLA  = 0x02
IPOLB  = 0x03
GPINTENA = 0x04
GPINTENB = 0x05
DEFVALA  = 0x06
DEFVALB  = 0x07
INTCONA  = 0x08
INTCONB  = 0x09
IOCON    = 0x0A  # (et 0x0B)
GPPUA    = 0x0C
GPPUB    = 0x0D
INTFA    = 0x0E
INTFB    = 0x0F
INTCAPA  = 0x10
INTCAPB  = 0x11
GPIOA    = 0x12
GPIOB    = 0x13
OLATA    = 0x14
OLATB    = 0x15


class MCP23017:
    def __init__(self, bus: I2CBus, address: int):
        self.bus = bus
        self.address = int(address) & 0x7F

        # Cache des sorties (OLAT)
        self._olat_a = 0x00
        self._olat_b = 0x00

    # -----------------------
    # Init / configuration
    # -----------------------

    def init(
        self,
        *,
        iodir_a: int = 0xFF,
        iodir_b: int = 0xFF,
        pullup_a: int = 0x00,
        pullup_b: int = 0x00,
        invert_a: int = 0x00,
        invert_b: int = 0x00,
        iocon: int = 0x00,
        reset_olat_to_zero: bool = False,
    ) -> None:
        """
        Configure directions + pullups + inversion.
        - iodir bit=1 => input, bit=0 => output
        - pullup bit=1 => pull-up activé (entrées)
        - invert bit=1 => inversion de lecture (IPOL)
        - iocon permet options avancées (laisser 0 si pas besoin)
        - reset_olat_to_zero: force toutes les sorties à 0 au démarrage
          (utile si tu veux un "safe state" côté MCP).
        """
        self.bus.write_byte_data(self.address, IOCON, iocon & 0xFF)

        self.bus.write_byte_data(self.address, IODIRA, iodir_a & 0xFF)
        self.bus.write_byte_data(self.address, IODIRB, iodir_b & 0xFF)

        self.bus.write_byte_data(self.address, GPPUA, pullup_a & 0xFF)
        self.bus.write_byte_data(self.address, GPPUB, pullup_b & 0xFF)

        self.bus.write_byte_data(self.address, IPOLA, invert_a & 0xFF)
        self.bus.write_byte_data(self.address, IPOLB, invert_b & 0xFF)

        if reset_olat_to_zero:
            self._olat_a = 0x00
            self._olat_b = 0x00
            self.bus.write_byte_data(self.address, OLATA, 0x00)
            self.bus.write_byte_data(self.address, OLATB, 0x00)
        else:
            # Synchronise le cache sur l'état courant
            self._olat_a = self.bus.read_byte_data(self.address, OLATA) & 0xFF
            self._olat_b = self.bus.read_byte_data(self.address, OLATB) & 0xFF

    # -----------------------
    # Read
    # -----------------------

    def read_gpio(self, bank: Bank) -> int:
        reg = GPIOA if bank == "A" else GPIOB
        return self.bus.read_byte_data(self.address, reg) & 0xFF

    # -----------------------
    # Write (sorties)
    # -----------------------

    def write_gpio(self, bank: Bank, value: int) -> None:
        """
        Ecrit toute une banque (8 bits).
        """
        v = value & 0xFF
        if bank == "A":
            self._olat_a = v
            self.bus.write_byte_data(self.address, OLATA, v)
        else:
            self._olat_b = v
            self.bus.write_byte_data(self.address, OLATB, v)

    def write_mask(self, bank: Bank, mask: int, values: int) -> None:
        """
        Met à jour uniquement les bits du mask.
        mask bit=1 -> bit modifié
        values contient les nouveaux bits (positionnés)
        """
        mask &= 0xFF
        values &= 0xFF

        if bank == "A":
            new_val = (self._olat_a & (~mask & 0xFF)) | (values & mask)
            if new_val != self._olat_a:
                self._olat_a = new_val
                self.bus.write_byte_data(self.address, OLATA, new_val)
        else:
            new_val = (self._olat_b & (~mask & 0xFF)) | (values & mask)
            if new_val != self._olat_b:
                self._olat_b = new_val
                self.bus.write_byte_data(self.address, OLATB, new_val)

    def write_bit(self, bank: Bank, bit: int, level: int) -> None:
        """
        Ecrit un bit de sortie en s'appuyant sur write_mask + cache OLAT.
        """
        if not (0 <= bit <= 7):
            raise ValueError("bit doit être entre 0 et 7")
        mask = 1 << bit
        values = mask if int(level) else 0
        self.write_mask(bank, mask, values)

    # -----------------------
    # Helpers de cache (optionnel)
    # -----------------------

    def get_cached_olat(self, bank: Bank) -> int:
        return self._olat_a if bank == "A" else self._olat_b
