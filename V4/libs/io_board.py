"""
io_board.py — Mapping applicatif des 3 MCP23017 du PCB.

Responsabilité : traduire les opérations métier (set_led, read_btn,
set_ena, set_dir) en accès registres MCP23017.

Toutes les adresses I2C et la logique de câblage sont documentées ici.
Les adresses physiques viennent de config.py.

Câblage PCB :
    MCP1 (0x24) — Programmes
        Port B INPUT  : B0..B5 = PRG1..PRG6 (actif bas, pull-up interne)
        Port A OUTPUT : A2..A7 = LED1..LED6  (actif haut)

    MCP2 (0x26) — Sélecteurs
        Port A INPUT  : A7..A5 = AIR1..AIR3  (actif bas, pull-up interne)
                        AIR0 = position 0 (aucun actif → pas d'injection)
                        AIR1 = faible, AIR2 = moyen, AIR3 = continu
        Port B INPUT  : B0..B4 = VIC1..VIC5  (actif bas, pull-up interne)

    MCP3 (0x25) — Drivers moteurs
        Port B OUTPUT : B0..B7 = ENA1..ENA8  (actif bas  → ENA_ACTIVE_LEVEL=0)
        Port A OUTPUT : A7..A0 = DIR1..DIR8  (OUVERTURE=1, FERMETURE=0)

Usage :
    from libs.i2c_bus import I2CBus
    from libs.io_board import IOBoard

    with I2CBus() as bus:
        io = IOBoard(bus)
        io.init()
        io.set_led(1, 1)
        pressed = io.read_btn_active(1)
        io.set_ena(3, 0)       # active driver moteur 3
        io.set_dir(3, "ouverture")
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
    Couche applicative au-dessus des 3 MCP23017 du PCB.

    Un seul IOBoard est instancié par application.
    Le bus I2C est passé en paramètre (injection de dépendance).
    """

    def __init__(self, bus: I2CBus) -> None:
        self.bus = bus
        self.mcp1 = MCP23017(bus, config.MCP1_ADDR)  # Programmes
        self.mcp2 = MCP23017(bus, config.MCP2_ADDR)  # Sélecteurs
        self.mcp3 = MCP23017(bus, config.MCP3_ADDR)  # Drivers moteurs

        # Caches OLAT — évitent un RMW I2C à chaque écriture de pin
        self._mcp1_olat_a: int = 0x00   # LEDs
        self._mcp3_olat_a: int = 0x00   # DIR
        self._mcp3_olat_b: int = 0x00   # ENA

    def init(self, force: bool = True) -> None:
        """
        Initialise les 3 MCP23017 :
        - Directions conformes au câblage PCB
        - Pull-ups activés sur toutes les entrées
        - Sorties en état sûr (LEDs OFF, moteurs désactivés)
        """
        self.mcp1.init(force=force)
        self.mcp2.init(force=force)
        self.mcp3.init(force=force)

        # --- directions ---
        self.mcp1.set_port_direction("B", 0xFF)  # B = entrées (boutons PRG)
        self.mcp1.set_port_direction("A", 0x00)  # A = sorties (LEDs)

        self.mcp2.set_port_direction("A", 0xFF)  # A = entrées (AIR)
        self.mcp2.set_port_direction("B", 0xFF)  # B = entrées (VIC)

        self.mcp3.set_port_direction("A", 0x00)  # A = sorties (DIR)
        self.mcp3.set_port_direction("B", 0x00)  # B = sorties (ENA)

        # --- pull-ups sur les entrées ---
        self.mcp1.set_pullup("B", 0xFF)
        self.mcp2.set_pullup("A", 0xFF)
        self.mcp2.set_pullup("B", 0xFF)

        # --- état sûr en sortie ---
        self._mcp1_olat_a = 0x00
        self._mcp3_olat_a = 0x00
        self._mcp3_olat_b = 0x00

        self.mcp1.write_port("A", self._mcp1_olat_a)
        self.mcp3.write_port("A", self._mcp3_olat_a)
        self.mcp3.write_port("B", self._mcp3_olat_b)

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
    # Sélecteur VIC — MCP2 Port B, pins B0..B4 (actif bas)
    # VIC1 → B0, VIC5 → B4
    # ============================================================

    @staticmethod
    def _vic_pin(vic_index: int) -> int:
        i = int(vic_index)
        if not (1 <= i <= 5):
            raise ValueError("vic_index doit être dans 1..5")
        return i - 1

    def read_vic(self, vic_index: int) -> int:
        """Niveau brut."""
        return self.mcp2.read_pin("B", self._vic_pin(vic_index))

    def read_vic_active(self, vic_index: int) -> int:
        """Retourne 1 si position sélectionnée."""
        return 1 if self.read_vic(vic_index) == 0 else 0

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

    # ============================================================
    # ENA drivers — MCP3 Port B, pins B0..B7 (actif bas)
    # ENA1 → B0, ENA8 → B7
    # Utiliser config.ENA_ACTIVE_LEVEL / ENA_INACTIVE_LEVEL
    # ============================================================

    @staticmethod
    def _ena_pin(motor_index: int) -> int:
        i = int(motor_index)
        if not (1 <= i <= 8):
            raise ValueError("motor_index doit être dans 1..8")
        return i - 1  # moteur 1→pin0, moteur 8→pin7

    def set_ena(self, motor_index: int, state: int) -> None:
        """
        Écrit l'état ENA d'un driver.
        Passer config.ENA_ACTIVE_LEVEL pour activer, ENA_INACTIVE_LEVEL pour désactiver.
        """
        pin = self._ena_pin(motor_index)
        bit = 1 << pin
        if int(state):
            self._mcp3_olat_b |= bit
        else:
            self._mcp3_olat_b &= (~bit & 0xFF)
        self.mcp3.write_port("B", self._mcp3_olat_b)

    def disable_all_drivers(self) -> None:
        """Désactive tous les drivers moteurs (état sûr)."""
        self._mcp3_olat_b = 0x00 if config.ENA_INACTIVE_LEVEL == 0 else 0xFF
        self.mcp3.write_port("B", self._mcp3_olat_b)

    # ============================================================
    # DIR drivers — MCP3 Port A, pins A7..A0 (inversé)
    # Moteur 1 → A7, Moteur 8 → A0
    # OUVERTURE = niveau haut (1), FERMETURE = niveau bas (0)
    # ============================================================

    @staticmethod
    def _dir_pin(motor_index: int) -> int:
        i = int(motor_index)
        if not (1 <= i <= 8):
            raise ValueError("motor_index doit être dans 1..8")
        return 8 - i  # moteur 1→pin7, moteur 8→pin0

    def set_dir(self, motor_index: int, direction: str) -> None:
        """
        Définit la direction d'un driver.
        direction : 'ouverture' / 'OUVERTURE' / 'OPEN' / 'O'
                    'fermeture' / 'FERMETURE' / 'CLOSE' / 'F'
        """
        d = direction.strip().upper()
        if d in ("OUVERTURE", "OPEN", "O"):
            v = 1
        elif d in ("FERMETURE", "CLOSE", "F"):
            v = 0
        else:
            raise ValueError(
                f"direction inconnue '{direction}'. "
                "Valeurs acceptées : 'ouverture'/'fermeture' (ou OPEN/CLOSE)"
            )

        pin = self._dir_pin(motor_index)
        bit = 1 << pin
        if v:
            self._mcp3_olat_a |= bit
        else:
            self._mcp3_olat_a &= (~bit & 0xFF)
        self.mcp3.write_port("A", self._mcp3_olat_a)
