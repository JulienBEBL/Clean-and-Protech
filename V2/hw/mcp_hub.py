# hw/mcp_hub.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from hal.i2c_bus import I2CBus


# Registres MCP23017 (BANK=0)
IODIRA = 0x00
IODIRB = 0x01
GPPUA = 0x0C
GPPUB = 0x0D
GPIOA = 0x12
GPIOB = 0x13
OLATA = 0x14
OLATB = 0x15


@dataclass(frozen=True)
class McpAddressing:
    mcp1: int = 0x24
    mcp2: int = 0x25
    mcp3: int = 0x26


@dataclass(frozen=True)
class McpPin:
    mcp: str   # "mcp1" / "mcp2" / "mcp3"
    port: str  # "A" ou "B"
    bit: int   # 0..7


class MCPHub:
    """
    Hub MCP23017:
      - init directions + pull-ups
      - lecture entrées (GPIOx)
      - écriture sorties (OLATx) avec cache

    Personne d'autre ne parle I2C.
    """

    def __init__(self, bus: I2CBus, addrs: McpAddressing):
        self.bus = bus
        self.addrs = addrs

        # Cache des sorties (latches) pour écrire seulement ce qui change
        # clé: ("mcp1","A") etc -> valeur 0..255
        self._olat: Dict[Tuple[str, str], int] = {}

    def _addr(self, mcp: str) -> int:
        return getattr(self.addrs, mcp)

    def init_all(self) -> None:
        """
        Configuration selon ton mapping:
        - MCP1 (0x24): B0..B5 entrées boutons, A2..A7 sorties LEDs (le reste: entrées pull-up)
        - MCP2 (0x25): entrées (VIC sur B, AIR sur A), pull-ups
        - MCP3 (0x26): sorties (DIR sur A, ENA sur B), ENA désactivé par défaut (1 car actif bas)
        """
        self._init_mcp1()
        self._init_mcp2()
        self._init_mcp3()

    def _init_mcp1(self) -> None:
        addr = self._addr("mcp1")

        # IODIR: 1=input, 0=output
        # MCP1 boutons: B0..B5 input => bits 0..5 = 1, le reste input aussi pour sécurité
        iodir_b = 0xFF
        # LEDs: A2..A7 output => bits 2..7 = 0, A0..A1 input => 1
        iodir_a = 0b00000011

        self.bus.write_byte_data(addr, IODIRA, iodir_a)
        self.bus.write_byte_data(addr, IODIRB, iodir_b)

        # Pull-ups sur entrées (A0..A1 + tous B)
        gppu_a = 0b00000011
        gppu_b = 0xFF
        self.bus.write_byte_data(addr, GPPUA, gppu_a)
        self.bus.write_byte_data(addr, GPPUB, gppu_b)

        # Init sorties LEDs à 0
        self._write_olat("mcp1", "A", 0x00)

    def _init_mcp2(self) -> None:
        addr = self._addr("mcp2")

        # Tout en entrée (selon ton mapping: B0..B4 VIC, A4..A7 AIR)
        self.bus.write_byte_data(addr, IODIRA, 0xFF)
        self.bus.write_byte_data(addr, IODIRB, 0xFF)

        # Pull-ups sur toutes entrées
        self.bus.write_byte_data(addr, GPPUA, 0xFF)
        self.bus.write_byte_data(addr, GPPUB, 0xFF)

    def _init_mcp3(self) -> None:
        addr = self._addr("mcp3")

        # Tout en sortie: DIR (A), ENA (B)
        self.bus.write_byte_data(addr, IODIRA, 0x00)
        self.bus.write_byte_data(addr, IODIRB, 0x00)

        # pas de pull-ups nécessaires sur sorties
        self.bus.write_byte_data(addr, GPPUA, 0x00)
        self.bus.write_byte_data(addr, GPPUB, 0x00)

        # Default: ENA désactivé (1) car actif bas -> tous à 1
        self._write_olat("mcp3", "B", 0xFF)
        # Default DIR = 0 (peu importe au repos)
        self._write_olat("mcp3", "A", 0x00)

    # ----------------------------
    # API haut niveau (sorties)
    # ----------------------------

    def write_pin(self, pin: McpPin, value: int) -> None:
        value = 1 if value else 0
        current = self._read_cached_olat(pin.mcp, pin.port)
        mask = 1 << pin.bit
        new_val = (current | mask) if value else (current & ~mask)
        self._write_olat(pin.mcp, pin.port, new_val)

    def write_port(self, mcp: str, port: str, value: int) -> None:
        self._write_olat(mcp, port, value & 0xFF)

    # ----------------------------
    # API haut niveau (entrées)
    # ----------------------------

    def read_pin(self, pin: McpPin) -> int:
        v = self.read_port(pin.mcp, pin.port)
        return 1 if (v & (1 << pin.bit)) else 0

    def read_port(self, mcp: str, port: str) -> int:
        addr = self._addr(mcp)
        reg = GPIOA if port.upper() == "A" else GPIOB
        return self.bus.read_byte_data(addr, reg) & 0xFF

    # ----------------------------
    # Helpers moteurs (MCP3)
    # ----------------------------

    def motor_set_enable(self, motor_index: int, enabled: bool) -> None:
        """
        motor_index: 1..8
        MCP3 ENA: B0..B7 = ENA1..ENA8
        ENA actif bas => enabled=True -> écrire 0
        """
        if not (1 <= motor_index <= 8):
            raise ValueError("motor_index doit être 1..8")
        bit = motor_index - 1
        pin = McpPin("mcp3", "B", bit)
        # actif bas
        self.write_pin(pin, 0 if enabled else 1)

    def motor_set_dir(self, motor_index: int, direction: int, invert: bool = False) -> None:
        """
        direction: 0/1 logique.
        MCP3 DIR: A0..A7 = DIR8..DIR1 (selon ton info)
        Donc:
          motor 1 -> A7
          motor 8 -> A0
        """
        if not (1 <= motor_index <= 8):
            raise ValueError("motor_index doit être 1..8")
        direction = 1 if direction else 0
        if invert:
            direction ^= 1

        bit = 8 - motor_index  # M1->7, M8->0
        pin = McpPin("mcp3", "A", bit)
        self.write_pin(pin, direction)

    # ----------------------------
    # Interne: cache OLAT
    # ----------------------------

    def _read_cached_olat(self, mcp: str, port: str) -> int:
        key = (mcp, port.upper())
        if key in self._olat:
            return self._olat[key]
        # si pas en cache, lire OLAT (pas GPIO) pour connaître le latch
        addr = self._addr(mcp)
        reg = OLATA if port.upper() == "A" else OLATB
        v = self.bus.read_byte_data(addr, reg) & 0xFF
        self._olat[key] = v
        return v

    def _write_olat(self, mcp: str, port: str, value: int) -> None:
        addr = self._addr(mcp)
        reg = OLATA if port.upper() == "A" else OLATB
        value &= 0xFF
        self.bus.write_byte_data(addr, reg, value)
        self._olat[(mcp, port.upper())] = value
