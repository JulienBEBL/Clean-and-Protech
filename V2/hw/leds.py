# hw/leds.py
from __future__ import annotations

from hw.mcp_hub import MCPHub, McpPin


class ProgramLeds:
    """
    Pilotage LEDs programmes via MCPHub.

    Mapping (selon ton info) :
      MCP1 LEDs : PORT A bits 2..7 = LED1..LED6
    Par défaut, LED active = 1 (active_high).
    """

    def __init__(self, mcp: MCPHub, active_high: bool = True):
        self.mcp = mcp
        self.active_high = active_high

    def set_prog_led(self, prog_index: int, on: bool) -> None:
        """
        prog_index: 1..6
        """
        if not (1 <= prog_index <= 6):
            raise ValueError("prog_index doit être 1..6")

        bit = prog_index + 1  # LED1->A2, LED6->A7
        pin = McpPin("mcp1", "A", bit)
        value = 1 if on else 0
        if not self.active_high:
            value ^= 1
        self.mcp.write_pin(pin, value)

    def all_off(self) -> None:
        for i in range(1, 7):
            self.set_prog_led(i, False)

    def show_active_program(self, prog_index: int | None) -> None:
        """
        Allume uniquement la LED du programme actif.
        Si prog_index est None => tout éteint.
        """
        for i in range(1, 7):
            self.set_prog_led(i, prog_index == i)
