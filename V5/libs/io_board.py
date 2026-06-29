"""
io_board.py — Mapping applicatif des 2 MCP23017 du PCB V5.

Responsabilité : traduire les opérations métier (set_led, read_btn,
read_vic_active, read_air_mode) en accès registres MCP23017.

Différence V4→V5 : MCP3 (drivers moteurs ENA/DIR) retiré.
En V5, la VIC est pilotée directement via GPIO (voir libs/vic.py).
Les adresses hardware viennent de config.py.

Câblage PCB V5 :
    MCP1 (0x24) — Programmes
        Port B INPUT  : B0..B5 = PRG1..PRG6 (actif bas, pull-up interne)
        Port A OUTPUT : A2..A7 = LED1..LED6  (actif haut)
                        LED1→A2, LED2→A3, ..., LED6→A7

    MCP2 (0x26) — Sélecteurs
        Port A INPUT  : A7..A5 = AIR1..AIR3  (actif bas, pull-up interne)
                        AIR1 = faible, AIR2 = moyen, AIR3 = continu
                        Position 0 (aucun actif) → pas d'injection
        Port B INPUT  : B0..B1 = VIC1..VIC2  (actif bas, pull-up interne)
                        VIC3 non câblé (non connecté au sélecteur)
                        VIC1 actif (B0) → DEPART  ( 0 pas)
                        VIC2 actif (B1) → RETOUR  (100 pas)
                        rien actif      → NEUTRE  ( 50 pas) — position par défaut

Usage :
    from libs.i2c_bus import I2CBus
    from libs.io_board import IOBoard

    with I2CBus() as bus:
        io = IOBoard(bus)
        io.init()
        io.set_led(1, 1)
        pressed = io.read_btn_active(1)
        vic_pos = io.read_vic_selector()   # 1=DEPART, 2=RETOUR, 0=NEUTRE (défaut)
"""

from __future__ import annotations

import config
from libs.i2c_bus import I2CBus
from libs.mcp23017 import MCP23017


# ============================================================
# IOBoard
# ============================================================

class IOBoard:
    """
    Couche applicative au-dessus des 2 MCP23017 du PCB V5.

    Un seul IOBoard est instancié par application.
    Le bus I2C est passé en paramètre (injection de dépendance).
    """

    def __init__(self, bus: I2CBus) -> None:
        self.bus  = bus
        self.mcp1 = MCP23017(bus, config.MCP1_ADDR)  # Programmes
        self.mcp2 = MCP23017(bus, config.MCP2_ADDR)  # Sélecteurs VIC + AIR

        # Cache OLAT — évite un RMW I2C à chaque écriture de LED
        self._mcp1_olat_a: int = 0x00   # LEDs

    def init(self, force: bool = True) -> None:
        """
        Initialise les 2 MCP23017 :
        - Directions conformes au câblage PCB V5
        - Pull-ups activés sur toutes les entrées
        - Sorties en état sûr (LEDs OFF)
        """
        self.mcp1.init(force=force)
        self.mcp2.init(force=force)

        # --- directions ---
        self.mcp1.set_port_direction("B", 0xFF)  # B = entrées (boutons PRG)
        self.mcp1.set_port_direction("A", 0x00)  # A = sorties (LEDs)

        self.mcp2.set_port_direction("A", 0xFF)  # A = entrées (AIR)
        self.mcp2.set_port_direction("B", 0xFF)  # B = entrées (VIC 3 pos)

        # --- pull-ups sur les entrées ---
        self.mcp1.set_pullup("B", 0xFF)
        self.mcp2.set_pullup("A", 0xFF)
        self.mcp2.set_pullup("B", 0xFF)

        # --- état sûr en sortie ---
        self._mcp1_olat_a = 0x00
        self.mcp1.write_port("A", self._mcp1_olat_a)

    # ============================================================
    # LEDs — MCP1 Port A, pins A2..A7 (actif haut)
    # LED1 → A2, LED2 → A3, ..., LED6 → A7
    # ============================================================

    @staticmethod
    def _led_pin(led_index: int) -> int:
        i = int(led_index)
        if not (1 <= i <= 6):
            raise ValueError("led_index doit être dans 1..6")
        return 1 + i  # LED1→pin2, LED6→pin7

    def set_led(self, led_index: int, state: int) -> None:
        """Allume (state=1) ou éteint (state=0) une LED."""
        pin = self._led_pin(led_index)
        bit = 1 << pin
        if int(state):
            self._mcp1_olat_a |= bit
        else:
            self._mcp1_olat_a &= (~bit & 0xFF)
        self.mcp1.write_port("A", self._mcp1_olat_a)

    def set_all_leds(self, state: int) -> None:
        """Allume ou éteint toutes les LEDs d'un coup."""
        if int(state):
            # pins A2..A7 → masque 0b11111100 = 0xFC
            self._mcp1_olat_a |= 0xFC
        else:
            self._mcp1_olat_a &= 0x03
        self.mcp1.write_port("A", self._mcp1_olat_a)

    # ============================================================
    # Boutons PRG — MCP1 Port B, pins B0..B5 (actif bas)
    # PRG1 → B0, PRG2 → B1, ..., PRG6 → B5
    # ============================================================

    @staticmethod
    def _prg_pin(prg_index: int) -> int:
        i = int(prg_index)
        if not (1 <= i <= 6):
            raise ValueError("prg_index doit être dans 1..6")
        return i - 1  # PRG1→pin0, PRG6→pin5

    def read_btn(self, prg_index: int) -> int:
        """Niveau brut (1=haut, 0=bas)."""
        return self.mcp1.read_pin("B", self._prg_pin(prg_index))

    def read_btn_active(self, prg_index: int) -> int:
        """Sémantique active-low : retourne 1 si bouton enfoncé, 0 sinon."""
        return 1 if self.read_btn(prg_index) == 0 else 0

    # ============================================================
    # Sélecteur VIC — MCP2 Port B, pins B0..B1 (actif bas) — V5 : 3 positions
    # VIC1 (DEPART)  → B0
    # VIC2 (RETOUR)  → B1
    # VIC3            → non câblé (ignoré)
    # ============================================================

    @staticmethod
    def _vic_pin(vic_index: int) -> int:
        i = int(vic_index)
        if not (1 <= i <= 3):
            raise ValueError("vic_index doit être dans 1..3 (1=DEPART/B0, 2=RETOUR/B1, 3=non câblé)")
        return i - 1  # VIC1→pin0 (B0), VIC2→pin1 (B1), VIC3→pin2 (non câblé)

    def read_vic(self, vic_index: int) -> int:
        """Niveau brut de la position vic_index (1..3)."""
        return self.mcp2.read_pin("B", self._vic_pin(vic_index))

    def read_vic_active(self, vic_index: int) -> int:
        """Retourne 1 si la position vic_index est sélectionnée (actif bas)."""
        return 1 if self.read_vic(vic_index) == 0 else 0

    def read_vic_selector(self) -> int:
        """
        Retourne la position du sélecteur VIC.
            1 = DEPART  (  0 pas) — VIC1 actif (B0)
            2 = RETOUR  (100 pas) — VIC2 actif (B1)
            0 = NEUTRE  ( 50 pas) — rien détecté (position par défaut)
        VIC3 non câblé — ignoré.
        """
        if self.read_vic_active(1):
            return 1
        if self.read_vic_active(2):
            return 2
        return 0  # rien détecté → NEUTRE

    # ============================================================
    # Sélecteur AIR — MCP2 Port A, pins A7..A5 (actif bas)
    # AIR1 (faible)   → A7
    # AIR2 (moyen)    → A6
    # AIR3 (continu)  → A5
    # Position 0 = aucun actif → pas d'injection
    # ============================================================

    @staticmethod
    def _air_pin(air_index: int) -> int:
        i = int(air_index)
        if not (1 <= i <= 3):
            raise ValueError("air_index doit être dans 1..3 (1=faible, 2=moyen, 3=continu)")
        return 8 - i  # AIR1→pin7, AIR2→pin6, AIR3→pin5

    def read_air(self, air_index: int) -> int:
        """Niveau brut de la position air_index (1..3)."""
        return self.mcp2.read_pin("A", self._air_pin(air_index))

    def read_air_active(self, air_index: int) -> int:
        """Retourne 1 si la position air_index est sélectionnée."""
        return 1 if self.read_air(air_index) == 0 else 0

    def read_air_mode(self) -> int:
        """
        Retourne le mode d'injection actif (0..3).
            0 = pas d'injection (aucune position active)
            1 = faible
            2 = moyen
            3 = continu
        """
        for i in range(1, 4):
            if self.read_air_active(i):
                return i
        return 0
