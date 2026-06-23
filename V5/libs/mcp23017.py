"""
mcp23017.py — Driver générique MCP23017 (expander I/O 16 bits via I2C).

Responsabilité : accès registres MCP23017, configuration direction,
pull-ups, lecture/écriture port et pin.

Ne contient aucune logique applicative (mapping physique → io_board.py).

Usage :
    from libs.i2c_bus import I2CBus
    from libs.mcp23017 import MCP23017, DeviceError

    with I2CBus() as bus:
        mcp = MCP23017(bus, address=0x24)
        mcp.init()
        mcp.set_port_direction("B", 0xFF)   # Port B = entrées
        mcp.set_port_direction("A", 0x00)   # Port A = sorties
        mcp.set_pullup("B", 0xFF)           # pull-ups sur Port B
        mcp.write_port("A", 0b00001100)     # écriture Port A
        val = mcp.read_port("B")            # lecture Port B
"""

from __future__ import annotations

from libs.i2c_bus import I2CBus, I2CError


# ============================================================
# Exceptions
# ============================================================

class DeviceError(I2CError):
    """Erreur de niveau composant (init, config MCP23017)."""


# ============================================================
# Driver MCP23017
# ============================================================

class MCP23017:
    """
    Driver MCP23017 — registres BANK=0 (défaut).

    Registres utilisés :
        IODIRA/B  (0x00/0x01) : direction (1=entrée, 0=sortie)
        IOCON     (0x0A)      : configuration (BANK=0 par défaut)
        GPPUA/B   (0x0C/0x0D) : pull-ups internes
        GPIOA/B   (0x12/0x13) : niveaux réels des pins
        OLATA/B   (0x14/0x15) : latch de sortie
    """

    # Adresses registres (BANK=0)
    _REG_IODIRA = 0x00
    _REG_IODIRB = 0x01
    _REG_IOCON  = 0x0A
    _REG_GPPUA  = 0x0C
    _REG_GPPUB  = 0x0D
    _REG_GPIOA  = 0x12
    _REG_GPIOB  = 0x13
    _REG_OLATA  = 0x14
    _REG_OLATB  = 0x15

    def __init__(self, bus: I2CBus, address: int) -> None:
        self.bus = bus
        self.address = int(address) & 0x7F

    # ---- init ----

    def init(self, force: bool = True) -> None:
        """
        Initialise le device.
        Si force=True : écrit IOCON=0x00 pour s'assurer que BANK=0.

        Raises:
            DeviceError si le device ne répond pas.
        """
        try:
            if force:
                self.bus.write_u8(self.address, self._REG_IOCON, 0x00)
        except I2CError as e:
            raise DeviceError(
                f"MCP23017 init échoué à l'adresse 0x{self.address:02X}: {e}"
            ) from e

    # ---- helpers internes ----

    @staticmethod
    def _norm_port(port: str) -> str:
        p = port.strip().upper()
        if p not in ("A", "B"):
            raise ValueError("port doit être 'A' ou 'B'")
        return p

    @staticmethod
    def _check_pin(pin: int) -> int:
        if not (0 <= int(pin) <= 7):
            raise ValueError("pin doit être dans la plage 0..7")
        return int(pin)

    def _reg_iodir(self, port: str) -> int:
        return self._REG_IODIRA if self._norm_port(port) == "A" else self._REG_IODIRB

    def _reg_gppu(self, port: str) -> int:
        return self._REG_GPPUA if self._norm_port(port) == "A" else self._REG_GPPUB

    def _reg_gpio(self, port: str) -> int:
        return self._REG_GPIOA if self._norm_port(port) == "A" else self._REG_GPIOB

    def _reg_olat(self, port: str) -> int:
        return self._REG_OLATA if self._norm_port(port) == "A" else self._REG_OLATB

    # ---- direction ----

    def set_port_direction(self, port: str, mask: int) -> None:
        """
        Configure la direction d'un port complet via IODIR.
        mask bit=1 → entrée, bit=0 → sortie.
        """
        self.bus.write_u8(self.address, self._reg_iodir(port), int(mask) & 0xFF)

    def set_pin_mode(self, port: str, pin: int, mode: str) -> None:
        """
        Configure la direction d'une seule pin.
        mode : 'INPUT' ou 'OUTPUT'
        """
        p = self._norm_port(port)
        b = self._check_pin(pin)
        m = mode.strip().upper()
        if m not in ("INPUT", "OUTPUT"):
            raise ValueError("mode doit être 'INPUT' ou 'OUTPUT'")

        reg = self._reg_iodir(p)
        cur = self.bus.read_u8(self.address, reg)
        bit = 1 << b
        new = (cur | bit) if m == "INPUT" else (cur & (~bit & 0xFF))
        self.bus.write_u8(self.address, reg, new)

    # ---- pull-ups ----

    def set_pullup(self, port: str, mask: int) -> None:
        """
        Configure les pull-ups d'un port via GPPU.
        mask bit=1 → pull-up activé (effectif uniquement si pin en entrée).
        """
        self.bus.write_u8(self.address, self._reg_gppu(port), int(mask) & 0xFF)

    def set_pullup_pin(self, port: str, pin: int, enabled: bool) -> None:
        """Configure le pull-up d'une seule pin (read-modify-write sur GPPU)."""
        p = self._norm_port(port)
        b = self._check_pin(pin)
        reg = self._reg_gppu(p)
        cur = self.bus.read_u8(self.address, reg)
        bit = 1 << b
        new = (cur | bit) if enabled else (cur & (~bit & 0xFF))
        self.bus.write_u8(self.address, reg, new)

    # ---- sorties ----

    def write_port(self, port: str, value: int) -> None:
        """Écrit le latch de sortie OLAT d'un port entier."""
        self.bus.write_u8(self.address, self._reg_olat(port), int(value) & 0xFF)

    def write_pin(self, port: str, pin: int, value: int) -> None:
        """Read-modify-write sur OLAT pour une seule pin."""
        p = self._norm_port(port)
        b = self._check_pin(pin)
        reg = self._reg_olat(p)
        cur = self.bus.read_u8(self.address, reg)
        bit = 1 << b
        new = (cur | bit) if int(value) else (cur & (~bit & 0xFF))
        self.bus.write_u8(self.address, reg, new)

    # ---- entrées ----

    def read_port(self, port: str) -> int:
        """Lit le registre GPIO (niveaux réels des pins)."""
        return self.bus.read_u8(self.address, self._reg_gpio(port))

    def read_pin(self, port: str, pin: int) -> int:
        """Lit le niveau d'une seule pin depuis GPIO."""
        b = self._check_pin(pin)
        val = self.read_port(port)
        return 1 if (val & (1 << b)) else 0
